"""Functions to export data into different file formats and organizations.

To allow datman to export to a new format add a new Exporter subclass and
add it to the EXPORTERS dict.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from glob import glob
import logging
import os
import re

import pydicom as dicom

import datman.dashboard
from datman.exceptions import UndefinedSetting
from datman.scanid import (parse_filename, parse_bids_filename, ParseException,
                           KCNIIdentifier)
from datman.utils import (run, make_temp_directory, get_extension,
                          filter_niftis, locate_metadata, find_tech_notes,
                          read_blacklist, get_relative_source)

try:
    from dcm2bids import Dcm2bids
except ImportError:
    DCM2BIDS_FOUND = False
else:
    DCM2BIDS_FOUND = True

logger = logging.getLogger(__name__)


def get_exporter(key, scope):
    if scope == "series":
        exp_set = SERIES_EXPORTERS
    else:
        exp_set = SESSION_EXPORTERS

    try:
        Exporter = exp_set[key]
    except KeyError:
        logger.error(
            f"Unrecognized format {key} for {scope}, no exporters found.")
        return
    return Exporter


class Exporter(ABC):

    # Subclasses must define this
    type = None

    @classmethod
    def get_output_dir(cls, session):
        return getattr(session, f"{cls.type}_path")

    @abstractmethod
    def export(self, *args, **kwargs):
        """Implement to convert input data to this exporter's output type.
        """
        pass

    def __repr__(self):
        fq_name = str(self.__class__).replace("<class '", "").replace("'>", "")
        name = fq_name.split(".")[-1]
        return f"<{name}>"


class SessionExporter(Exporter):
    """A base class for exporters that take an entire session as input.
    """

    def __init__(self, config, session, experiment, download_dir,
                 dry_run=False, ignore_db=False, **kwargs):
        self.tmp_dir = download_dir
        self.dry_run = dry_run
        self.ignore_db = ignore_db


class SeriesExporter(Exporter):
    """A base class for exporters that take a single series as input.
    """

    # Subclasses should set this
    ext = None

    def __init__(self, input_dir, output_dir, fname_root, echo_dict=None,
                 dry_run=False):
        self.input = input_dir
        self.output_dir = output_dir
        self.fname_root = fname_root
        self.echo_dict = echo_dict
        self.dry_run = dry_run


class BidsExporter(SessionExporter):

    type = "bids"

    def __init__(self, config, session, experiment, download_dir,
                 keep_dcm=False, clobber=False, force_dcm2niix=False,
                 log_level="INFO", dcm2bids_config=None, **kwargs):

        if not dcm2bids_config:
            try:
                dcm2bids_config = locate_metadata(
                    "dcm2bids.json", config=config)
            except FileNotFoundError:
                logger.error("No dcm2bids.json config file available for "
                             f"{config.study_name}")

        self.input = self._get_scan_dir(experiment.name, download_dir)
        self.keep_dcm = keep_dcm
        self.force_dcm2niix = force_dcm2niix
        self.clobber = clobber
        self.log_level = log_level
        self.dcm2bids_config = dcm2bids_config
        self.bids_sub = session._ident.get_bids_name()
        self.bids_ses = session._ident.timepoint
        self.bids_folder = session.bids_root
        self.output_dir = session.bids_path
        super().__init__(config, session, experiment, download_dir, **kwargs)

    def _get_scan_dir(self, exp_label, download_dir):
        return os.path.join(download_dir, exp_label, "scans")

    # @property
    # def outputs_exist(self):
    #     # Update function name. Propery is not good (looks weird).
    #     # Maybe rename it
    #
    #     # Can't get more granular than this at the moment
    #     exists = os.path.exists(self.output_dir)
    #     if exists:
    #         if self.clobber:
    #             logger.info("Overwriting because of --clobber")
    #             return False
    #         else:
    #             logger.info("(Use --clobber to overwrite)")
    #     return exists

    def export(self):
        if not DCM2BIDS_FOUND:
            logger.error(f"Unable to export to {self.output_dir}, "
                         "Dcm2Bids not found.")
            return

        try:
            dcm2bids_app = Dcm2bids(
                self.input,
                self.bids_sub,
                self.dcm2bids_config,
                output_dir=self.bids_folder,
                session=self.bids_ses,
                clobber=self.clobber,
                forceDcm2niix=self.force_dcm2niix,
                log_level=self.log_level
            )
            dcm2bids_app.run()
        except Exception as e:
            logger.error(
                f"Dcm2Bids failed to run for {self.output_dir}. "
                f"{type(e)}: {e}"
            )


class NiiLinkExporter(SessionExporter):

    type = "nii_link"

    def __init__(self, config, session, experiment, download_dir,
                 **kwargs):
        # Update this to save the experiment, to call assign_names if
        #   they dont already exist (always? is it idempotent?)
        #   Update export nii to also do this
        #   Move the function calls for getting names to export
        #       So they're updated in real life
        self.nii_path = session.nii_path
        self.config = config
        self.tags = config.get_tags(site=session.site)
        self.experiment = experiment
        # self.dm_names = self._get_dm_names(experiment)
        self.bids_path = session.bids_path
        # self.bids_names = self._get_bids_niftis(session.bids_path)
        super().__init__(config, session, experiment, download_dir, **kwargs)

    def export(self):
        dm_names = self.get_dm_names()
        bids_names = self.get_bids_niftis()

        name_map = self.match_dm_to_bids(dm_names, bids_names)
        for dm_name in name_map:
            self.make_link(dm_name, name_map[dm_name])

    def make_link(self, dm_file, bids_file):
        base_target = os.path.join(self.nii_path, dm_file)
        if read_blacklist(scan=base_target, config=self.config):
            logger.debug(f"Ignoring blacklisted scan {dm_file}")
            return

        for source in glob(bids_file + '*'):
            ext = get_extension(source)
            target = base_target + ext
            rel_source = get_relative_source(source, target)
            try:
                os.symlink(rel_source, target)
            except FileExistsError:
                pass
            except Exception as e:
                logger.error(f"Failed to create {target}. Reason - {e}")

    def get_dm_names(self):
        name_map = {}
        for scan in self.experiment.scans:
            for idx, name in enumerate(scan.names):
                name_map.setdefault(scan.tags[idx], []).append(name)
        return name_map

    def get_bids_niftis(self):
        """Get all nifti files from a session.

        Returns:
            list: A list of full paths (minus the file extension) to each
                nifti file in the session.
        """
        bids_niftis = []
        for path, dirs, files in os.walk(self.bids_path):
            niftis = filter_niftis(files)
            for item in niftis:
                basename = item.replace(get_extension(item), "")
                bids_niftis.append(os.path.join(path, basename))
        return bids_niftis

    def match_dm_to_bids(self, dm_names, bids_names):
        """Match each datman file name to its BIDS equivalent.
        """
        name_map = {}
        for tag in dm_names:
            try:
                bids_conf = self.tags.get(tag)['Bids']
            except KeyError:
                logger.info(f"No bids config found for tag {tag}. Can't match "
                            "bids outputs to a datman-style name.")
                continue

            matches = self._find_matching_files(bids_names, bids_conf)

            if bids_conf.get('class') == 'fmap' and bids_conf.get('match_str'):
                self._add_fmap_names(dm_names[tag], matches,
                    bids_conf.get('match_str'), name_map)
                continue

            # Probably no longer needed
            # matches = self._organize_bids(matches)

            # If organize_bids is used, delete this line
            bids_files = sorted(
                matches,
                key=lambda x: int(parse_bids_filename(x).run)
            )

            dm_files = sorted(
                dm_names[tag],
                key=lambda x: int(parse_filename(x)[2])
            )

            for idx, item in enumerate(dm_files):
                if idx >= len(matches):
                    continue
                # Uncomment if organize_bids still needed
                # if matches[idx] == "N/A":
                #     continue
                name_map[item] = matches[idx]

        return name_map

    def _find_matching_files(self, bids_names, bids_conf):
        # """Find all BIDS file names that match the settings for a tag.
        #
        # Args:
        #     bids_conf (:obj:`dict`): A dictionary of BIDS configuration settings
        #         associated with a datman tag.
        #
        # Returns:
        #     list: A list of BIDS filenames that match the given config.
        # """
        matches = self._filter_bids(
            bids_names, bids_conf.get('class'), par_dir=True)
        matches = self._filter_bids(matches, bids_conf.get(
            self._get_label_key(bids_conf)))
        matches = self._filter_bids(matches, bids_conf.get('task'))
        return matches

    def _get_label_key(self, bids_conf):
        for key in bids_conf:
            if 'label' in key:
                return key

    def _filter_bids(self, niftis, search_term, par_dir=False):
        """Find the subset of file names that matches a search string.

        Args:
            niftis (:obj:`list`): A list of nifti file names to search through.
            search_term (:obj:`str`): The search term nifti files must match.
            par_dir (bool, optional): Restricts the search to the nifti file's
                parent directory, if full paths were given.

        Returns:
            list: A list of all files that match the search term.
        """
        if not search_term:
            return niftis.copy()

        if not isinstance(search_term, list):
            search_term = [search_term]

        result = set()
        for item in niftis:
            if par_dir:
                fname = os.path.split(os.path.dirname(item))[1]
            else:
                fname = os.path.basename(item)

            for term in search_term:
                if term in fname:
                    result.add(item)
        return list(result)

    def _add_fmap_names(self, dm_fmaps, bids_fmaps, match_map, name_map):
        matches = self._get_matching_fmaps(dm_fmaps, bids_fmaps, match_map)

        for dm_root in matches:
            for found_bids in matches[dm_root]:
                dm_name = self._modify_dm_name(dm_root, found_bids)
                name_map[dm_name] = found_bids
        # mangled_dm = self._split_fmap_description(dm_fmaps)
        # temp_matches = {}
        # for fmap in bids_fmaps:
        #     ident = parse_bids_filename(fmap)
        #     if ident.acq not in match_map:
        #         logger.debug(
        #             "Tag settings can't match bids acquisition to datman "
        #             f"name for: {ident}")
        #         continue
        #     for search_str in match_map[ident.acq]:
        #         for nii_file in mangled_dm:
        #             if search_str in mangled_dm[nii_file]:
        #                 temp_matches.setdefault(nii_file, []).append(fmap)
        #
        # for nii_root in temp_matches:
        #     for found_bids in temp_matches[nii_root]:
        #         ident = parse_bids_filename(found_bids)
        #         new_nii_root = [nii_root]
        #         if ident.dir:
        #             new_nii_root.append(f"dir-{ident.dir}")
        #         if ident.run:
        #             new_nii_root.append(f"run-{ident.run}")
        #         if ident.suffix:
        #             new_nii_root.append(ident.suffix)
        #         new_fname = "_".join(new_nii_root)
        #         name_map[new_fname] = found_bids

    def _get_matching_fmaps(self, dm_fmaps, bids_fmaps, match_map):
        matches = {}
        for fmap in bids_fmaps:
            bids_file = parse_bids_filename(fmap)
            if bids_file.acq not in match_map:
                logger.debug(
                    "Tag settings can't match bids acquisition to datman "
                    f"name for: {bids_file}")
                continue

            for nii_file in dm_fmaps:
                _, _, _, description = parse_filename(nii_file)
                terms_match = [search_term in description
                               for search_term in match_map[bids_file.acq]]

                if any(terms_match):
                    matches.setdefault(nii_file, []).append(fmap)

        return matches

    def _modify_dm_name(self, dm_name, bids_name):
        ident = parse_bids_filename(bids_name)
        new_descr = []
        if ident.dir:
            new_descr.append(f"dir-{ident.dir}")
        if ident.run:
            new_descr.append(f"run-{ident.run}")
        if ident.suffix:
            new_descr.append(ident.suffix)
        return dm_name + "_".join(new_descr)

    # def _split_fmap_description(self, fmaps):
    #     no_descr = {}
    #     for fmap in fmaps:
    #         ident, tag, series, descr = parse_filename(fmap)
    #         truncated_name = "_".join([str(ident), tag, series])
    #         no_descr[truncated_name] = descr
    #     return no_descr

    # def _organize_bids(bids_names):
    #     This shouldnt be needed for newly generated bids sessions.
    #     and pre-existing arent meant to be linked.
    #
    #     """Sort and pad the list of bids names so datman names match correct runs.
    #     """
    #     by_run = sorted(
    #         bids_names,
    #         key=lambda x: int(parse_bids_filename(x).run)
    #     )
    #
    #     cur_run = 1
    #     padded = []
    #     for scan in by_run:
    #         fname = parse_bids_filename(scan)
    #         while cur_run < int(fname.run):
    #             padded.append("N/A")
    #             cur_run += 1
    #         padded.append(scan)
    #         cur_run += 1
    #     return padded


class DBExporter(SessionExporter):

    type = "db"

    def __init__(self, config, session, experiment, download_dir, **kwargs):
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
        self.ident = session._ident
        self.study_resource_path = study_resource_dir
        self.resources_path = resources_dir
        self.date = experiment.date
        self.names = self._get_scan_names(session, experiment)
        super().__init__(config, session, experiment, download_dir, **kwargs)

    def _get_scan_names(self, session, experiment):
        names = {}
        for scan in experiment.scans:
            for name in scan.names:
                names[name] = self._get_bids_name(name, session)
        return names

    def _get_bids_name(self, dm_name, session):
        found = [item for item in session.find_files(dm_name)
                 if ".nii.gz" in item]
        if not found or not os.path.islink(found[0]):
            return ""
        bids_src = os.readlink(found[0])
        bids_name = os.path.basename(bids_src)
        return bids_name.replace(get_extension(bids_name), "")

    def export(self):
        if self.dry_run or self.ignore_db:
            logger.debug(f"Skipping database update for {str(self.ident)}")
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

    def make_session(self):
        logger.debug(f"Adding session {str(self.ident)} to dashboard.")
        try:
            session = datman.dashboard.get_session(self.ident, create=True)
        except datman.dashboard.DashboardException as e:
            logger.error(f"Failed adding session {str(self.ident)} to "
                         f"database. Reason: {e}")
            return

        self._set_alt_ids(session)
        self._set_date(session)

        return session

    def _set_alt_ids(self, session):
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
        notes = find_tech_notes(self.resources_path)
        if not notes:
            logger.debug(f"No tech notes found in {self.resources_path}")
            return

        # Store only the path relative to the resources dir
        session.tech_notes = notes.replace(
            self.study_resource_path, "").lstrip("/")
        session.save()

    def make_scan(self, file_stem):
        logger.debug(f"Adding scan {file_stem} to dashboard.")
        try:
            scan = datman.dashboard.get_scan(file_stem, create=True)
        except datman.dashboard.DashboardException as e:
            logger.error(f"Failed adding scan {file_stem} to dashboard "
                         f"with error: {e}")
            return

        self._add_bids_scan_name(scan, file_stem)
        self._add_side_car(scan, file_stem)
        self._add_conversion_errors(scan, file_stem)

    def _add_bids_scan_name(self, scan, dm_stem):
        bids_stem = self.names[dm_stem]
        if not bids_stem:
            return

        try:
            bids_ident = parse_bids_filename(bids_stem)
        except ParseException as e:
            logger.debug(f"Failed to parse bids file name {bids_stem}")
            return
        scan.add_bids(str(bids_ident))

    def _add_side_car(self, scan, file_stem):
        side_car = self._get_file(file_stem, ".json")
        if not side_car:
            logger.error(f"Missing json side car for {file_stem}")
            return

        try:
            scan.add_json(side_car)
        except Exception as e:
            logger.error("Failed to add JSON side car to dashboard "
                         f"record for {side_car}. Reason - {e}")

    def _add_conversion_errors(self, scan, file_stem):
         convert_errors = self._get_file(file_stem, ".err")
         if not convert_errors:
             return
         message = self._read_file(convert_errors)
         scan.add_error(message)

    def _get_file(self, fname, ext):
        found = os.path.join(self.nii_path, fname + ext)
        if not os.path.exists(found):
            logger.debug(f"File not found {found}")
            return
        return found

    def _read_file(self, fpath):
        try:
            with open(fpath, "r") as fh:
                message = fh.readlines()
        except Exception as e:
            logger.debug(f"Can't read file {fh}")
            return
        return message


class NiiExporter(SeriesExporter):

    ext = ".nii.gz"

    type = "nii"

    def export(self):
        with make_temp_directory(prefix="export_nifti_") as tmp:
            _, log_msgs = run(f'dcm2niix -z y -b y -o {tmp} {self.input}',
                              self.dry_run)
            for tmp_file in glob(f"{tmp}/*"):
                self.move_nifti(tmp_file)
                stem = self._get_fname(tmp_file)
                self.report_issues(stem, str(log_msgs))

    def move_nifti(self, gen_file):
        fname = self._get_fname(gen_file)

        if not fname:
            return

        out_file = os.path.join(self.output_dir, fname)
        if os.path.exists(out_file):
            logger.error(f"Output {out_file} already exists. Skipping.")
            return

        return_code, _ = run(f"mv {gen_file} {out_file}", self.dry_run)
        if return_code:
            logger.debug(f"Moving dcm2niix output {gen_file} to {out_file} "
                         "has failed.")

    def _get_fname(self, gen_file):
        ext = get_extension(gen_file)
        bname = os.path.basename(gen_file)

        if self.echo_dict:
            stem = self._get_echo_fname(bname, ext)
        else:
            stem = self.fname_root
        return stem + ext

    def _get_echo_fname(self, fname, ext):
        # Match a 14 digit timestamp and 1-3 digit series num
        regex = "files_(.*)_([0-9]{14})_([0-9]{1,3})(.*)?" + ext
        match = re.search(regex, fname)

        if not match:
            logger.error(f"Can't parse valid echo number from {fname}.")
            return ""

        try:
            echo = int(m.group(4).split('e')[-1][0])
            stem = self.echo_dict[echo]
        except Exception:
            logger.error(f"Can't parse valid echo number from {fname}")
            return ""

        return stem

    def report_issues(self, stem, messages):
        if self.dry_run:
            logger.info(f"DRYRUN - Skipping write of error log for {stem}")
            return

        if 'missing images' not in messages:
            # The only issue we care about currently is if files are missing
            return

        dest = os.path.join(self.output_dir, stem) + ".err"
        self._write_error_log(dest, messages)

    def _write_error_log(self, dest, messages):
        try:
            with open(dest, "w") as output:
                output.write(messages)
        except Exception as e:
            logger.error(f"Failed writing dcm2niix errors to {dest}. "
                         f"Reason - {type(e).__name__} {e} ")


class NrrdExporter(SeriesExporter):

    type = "nrrd"
    ext = ".nrrd"

    def export(self, dry_run=False):
        nrrd_script = self._locate_script()
        run(f"{nrrd_script} {self.input} {self.fname_root} {self.output_dir}",
            dry_run)

    def _locate_script(self):
        datman_dir = os.path.split(os.path.dirname(__file__))[0]
        return os.path.join(datman_dir, "bin", "dcm_to_nrrd.sh")


class DcmExporter(SeriesExporter):

    type = "dcm"
    ext = ".dcm"

    def output_exists(self):
        # Need to override the default because otherwise multiechos will
        # always return False and reportedly export.
        return False

    def export(self, dry_run=False):
        if self.echo_dict:
            _export_multi_echo(dry_run)
            return

        dcm_file = self._find_dcm()
        if not dcm_file:
            logger.error(f"No dicom files found in {self.input}")
            return

        logger.debug(f"Exporting a dcm file from {self.input} to "
                     f"{self.output_dir}")
        for output in self.output_files:
            run(f"cp {dcm_file} {output}", dry_run)

    def _find_dcm(self):
        for path in glob(f"{self.input}/*"):
            try:
                dicom.read_file(path)
            except dicom.filereader.InvalidDicomError:
                pass
            else:
                return path

    def _export_multi_echo(self):
        dcm_dict = {}
        for path in glob(f"{self.input}/*"):
            try:
                dcm_file = dicom.read_file(path)
            except dicom.filereader.InvalidDicomError:
                continue
            dcm_echo_num = dcm_file.EchoNumbers
            if dcm_echo_num not in dcm_dict.keys():
                dcm_dict[int(dcm_echo_num)] = path
            if len(dcm_dict) == len(self.echo_dict):
                break

        for echo_num, dcm_echo_num in zip(echo_dict.keys(), dcm_dict.keys()):
            output_file = os.path.join(self.output_dir,
                                       self.echo_dict[echo_num] + self.ext)
            logger.debug(f"Exporting a dcm file from {self.input} to "
                         f"{output_file}")
            cmd = f"cp {dcm_dict[dcm_echo_num]} {output_file}"
            run(cmd, self.dry_run)


class MncExporter(SeriesExporter):

    type = "mnc"
    ext = ".mnc"

    def export(self, dry_run=False):
        cmd = (f"dcm2mnc -fname {self.fname_root} -dname '' {self.input}/* "
               f"{self.output_dir}")
        run(cmd, dry_run)


SESSION_EXPORTERS = {
    exp.type: exp for exp in SessionExporter.__subclasses__()
}

SERIES_EXPORTERS = {
    exp.type: exp for exp in SeriesExporter.__subclasses__()
}
