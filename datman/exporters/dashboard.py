"""An exporter to push raw datman files into the QC dashboard.
"""
from datetime import datetime
import logging
import os

from .base import SessionExporter
import datman.config
import datman.dashboard
from datman.exceptions import (ConfigException, DashboardException,
                               UndefinedSetting)
from datman.scanid import (KCNIIdentifier, parse, parse_bids_filename,
                           ParseException)
from datman.utils import find_tech_notes, get_extension

logger = logging.getLogger(__name__)

__all__ = ["DBExporter"]


class DBExporter(SessionExporter):
    """Add a datman-style session and its contents to datman's QC dashboard.
    """

    type = "db"

    def __init__(self, config, session, experiment, **kwargs):
        try:
            study_resource_dir = config.get_path("resources")
        except UndefinedSetting:
            study_resource_dir = ""

        try:
            resources_dir = os.path.join(
                config.get_path("resources"),
                session._ident.get_full_subjectid_with_timepoint_session()
            )
        except UndefinedSetting:
            resources_dir = ""

        self.nii_path = session.nii_path
        self.output_dir = None
        self.ident = session._ident
        self.study_resource_path = study_resource_dir
        self.resources_path = resources_dir
        self.date = experiment.date
        super().__init__(config, session, experiment, **kwargs)

    @property
    def names(self):
        """Gets list of valid datman-style scan names for a session.

        Returns:
            :obj:`dict`: A dictionary of datman style scan names mapped to
                the bids style name if one can be found, otherwise, an
                empty string.
        """
        names = {}
        # use experiment.scans, so dashboard can report scans that didnt export
        for scan in self.experiment.scans:
            for name in scan.names:
                names[name] = self.get_bids_name(name, self.session)

        # Check the actual folder contents as well, in case symlinked scans
        # exist that werent named on XNAT
        for nii in self.session.niftis:
            fname = nii.file_name.replace(nii.ext, "")
            if fname in names:
                continue
            names[fname] = self.get_bids_name(fname, self.session)

        return names

    def get_bids_name(self, dm_name, session):
        """Get BIDS style scan name from a datman style nifti.

        Returns:
            str: A valid bids style file name or an empty string if one
                cannot be found.
        """
        found = [item for item in session.find_files(dm_name)
                 if ".nii.gz" in item]
        if not found or not os.path.islink(found[0]):
            return ""
        bids_src = os.readlink(found[0])
        bids_name = os.path.basename(bids_src)
        return bids_name.replace(get_extension(bids_name), "")

    def export(self, *args, **kwargs):
        if self.dry_run:
            logger.info("Dry run: Skipping database update for "
                        f"{str(self.ident)}")
            return

        if not datman.dashboard.dash_found:
            logger.warning("Dashboard database not found, unable to add "
                           f"{str(self.ident)} and its contents.")
            return

        session = self.make_session()

        if not session.tech_notes and session.expects_notes():
            self.add_tech_notes(session)

        for file_stem in self.names:
            self.make_scan(file_stem)

    def outputs_exist(self):
        try:
            session = datman.dashboard.get_session(self.ident)
        except DashboardException:
            return False
        except ParseException:
            logger.error(
                f"Session name {self.ident} is not datman format. Ignoring.")
            return True

        if not session:
            return False

        if not session.tech_notes and session.expects_notes():
            return False

        for name in self.names:
            try:
                scan = datman.dashboard.get_scan(name)
            except DashboardException:
                return False
            except ParseException:
                logger.error(
                    f"Scan name {name} is not datman format. Ignoring.")
                continue

            if not scan:
                return False

            if self.errors_outdated(scan, name):
                return False

        return True

    @classmethod
    def get_output_dir(cls, session):
        return None

    def needs_raw_data(self):
        return False

    def make_session(self):
        """Add the current session to datman's QC database.

        Returns:
            :obj:`dashboard.models.Session`: The created scan session or None.
        """
        logger.debug(f"Adding session {str(self.ident)} to dashboard.")
        try:
            session = datman.dashboard.get_session(self.ident, create=True)
        except datman.dashboard.DashboardException as exc:
            logger.error(f"Failed adding session {str(self.ident)} to "
                         f"database. Reason: {exc}")
            return None

        self._set_alt_ids(session)
        self._set_date(session)

        return session

    def _set_alt_ids(self, session):
        """Add alternate ID formats for the scan session to the database.

        Args:
            session (:obj:`dashboard.models.Session`): A valid QC dashboard
                scan session.
        """
        session.timepoint.bids_name = self.ident.get_bids_name()
        session.timepoint.bids_session = self.ident.timepoint
        session.save()

        if not isinstance(self.ident, KCNIIdentifier):
            return

        session.timepoint.kcni_name = self.ident.get_xnat_subject_id()
        session.kcni_name = self.ident.get_xnat_experiment_id()
        session.save()
        return

    def _set_date(self, session):
        """Add the scan date for a scan session to the QC database.

        Args:
            session (:obj:`dashboard.models.Session`): A valid QC dashboard
                scan session.
        """
        if not self.date:
            logger.debug(f"No scan date found for {str(self.ident)}, "
                         "leaving blank.")
            return

        try:
            date = datetime.strptime(self.date, '%Y-%m-%d')
        except ValueError:
            logger.error(f"Invalid scan date {self.date} for session "
                         f"{str(self.ident)}")
            return

        if date == session.date:
            return

        session.date = date
        session.save()

    def add_tech_notes(self, session):
        """Add the path to a scan session's tech notes to the database.

        Args:
            session (:obj:`dashboard.models.Session`): A valid QC dashboard
                scan session.
        """
        notes = find_tech_notes(self.resources_path)
        if not notes:
            logger.debug(f"No tech notes found in {self.resources_path}")
            return

        # Store only the path relative to the resources dir
        session.tech_notes = notes.replace(
            self.study_resource_path, "").lstrip("/")
        session.save()

    def make_scan(self, file_stem):
        """Add a single scan to datman's QC dashboard.

        Args:
            file_stem (:obj:`str`): A valid datman-style file name.
        """
        logger.debug(f"Adding scan {file_stem} to dashboard.")
        try:
            scan = datman.dashboard.get_scan(file_stem, create=True)
        except datman.dashboard.DashboardException as exc:
            logger.error(f"Failed adding scan {file_stem} to dashboard "
                         f"with error: {exc}")
            return
        if self.experiment.is_shared():
            source_session = self._get_source_session()
            self._make_linked(scan, source_session)
        self._add_bids_scan_name(scan, file_stem)
        self._add_side_car(scan, file_stem)
        self._update_conversion_errors(scan, file_stem)

    def _make_linked(self, scan, source_session):
        try:
            source_session = datman.dashboard.get_session(source_session)
        except datman.dashboard.DashboardException as exc:
            logger.error(
                f"Failed to link shared scan {scan} to source "
                f"{source_session}. Reason - {exc}"
            )
            return
        matches = [
            source_scan for source_scan in source_session.scans
            if (source_scan.series == scan.series and
                source_scan.tag == scan.tag)
        ]
        if not matches or len(matches) > 1:
            logger.error(
                f"Failed to link shared scan {scan} to {source_session}."
                " Reason - Unable to find source scan database record."
            )
            return

        scan.source_id = matches[0].id
        scan.save()

    def _get_source_session(self):
        """Get the ID of the source experiment for a shared XNATExperiment."""
        try:
            config = datman.config.config(study=self.experiment.source_name)
        except ConfigException:
            return self.experiment.source_name

        try:
            id_map = config.get_key('IdMap')
        except UndefinedSetting:
            return self.experiment.source_name

        return str(parse(self.experiment.source_name, id_map))

    def _add_bids_scan_name(self, scan, dm_stem):
        """Add a bids format file name to a series in the QC database.

        Args:
            scan (:obj:`dashboard.models.Scan`): A QC dashboard scan.
            dm_stem (:obj:`str`): A valid bids format scan name, or an
                empty string if the update should be skipped.
        """
        bids_stem = self.names[dm_stem]
        if not bids_stem:
            return

        try:
            bids_ident = parse_bids_filename(bids_stem)
        except ParseException:
            logger.debug(f"Failed to parse bids file name {bids_stem}")
            return
        scan.add_bids(str(bids_ident))

    def _add_side_car(self, scan, file_stem):
        """Add the JSON side car contents to the QC database.

        Args:
            scan (:obj:`dashboard.models.Scan`): A QC dashboard scan.
            file_stem (:obj:`str`): A valid datman-style file name. Used to
                find the json side car file.
        """
        nii_file = self._get_file(file_stem, ".nii.gz")
        if not nii_file:
            # File exists on xnat but hasnt been generated.
            return

        side_car = self._get_file(file_stem, ".json")
        if not side_car:
            logger.error(f"Missing json side car for {file_stem}")
            return

        try:
            scan.add_json(side_car)
        except Exception as exc:
            logger.error("Failed to add JSON side car to dashboard "
                         f"record for {side_car}. Reason - {exc}")

    def _update_conversion_errors(self, scan, file_stem):
        """Add any dcm2niix conversion errors to the QC database.

        Args:
            scan (:obj:`dashboard.models.Scan`): A QC dashboard scan.
            file_stem (:obj:`str`): A valid datman style file name. Used to
                find the conversion error file (if one exists).
        """
        convert_errors = self._get_file(file_stem, ".err")
        if not convert_errors:
            if scan.conv_errors:
                # Erase the error message from the DB, because it
                # has been resolved.
                scan.add_error(None)
            return
        message = self._read_file(convert_errors)
        scan.add_error(message)

    def _get_file(self, fname, ext):
        """Find a file on the file system.

        Args:
            fname (:obj:`str`): A file name (minus extension).
            ext (:obj:`str`): A file extension.

        Returns:
            str: The full path to the file matching the given name and
                extension, otherwise None.
        """
        found = os.path.join(self.nii_path, fname + ext)
        if not os.path.exists(found):
            bl_found = os.path.join(self.nii_path, 'blacklisted', fname + ext)
            if os.path.exists(bl_found):
                return bl_found
            logger.debug(f"File not found {found}")
            return None
        return found

    def _read_file(self, fpath):
        """Read the contents of a file.

        Args:
            fpath (:obj:`str`): The full path to a file.

        Returns:
            str: The contents of the file or None if the file cannot be read.
        """
        try:
            with open(fpath, "r") as file_handle:
                message = file_handle.readlines()
        except Exception as exc:
            logger.debug(f"Can't read file {fpath} - {exc}")
            return None
        return message

    def errors_outdated(self, scan, fname):
        err_file = self._get_file(fname, ".err")
        if not err_file and scan.conv_errors:
            # Error is resolved, but still appears in database
            return True
        if err_file and not scan.conv_errors:
            # Error has appeared, but isnt recorded in database
            return True
        if err_file and scan.conv_errors:
            # Error exists in both locations, but may have changed
            message = self._read_file(err_file)
            if isinstance(message, list):
                message = "\n".join(message)
            return message != scan.conv_errors
        return False
