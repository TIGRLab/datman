"""Export to bids format when using dcmbids versions below '3'.

For dcm2bids versions 3 and higher (or dcm2bids versions accessed via
container) 'dcm2bids', 'Dcm2bids' and 'Acquisition' are not accessible so these
exporters cannot be used.

When using versions below '3' though, this exporter has advantages over the
newer one. Namely, its outputs_exist() method can better check the actual
contents of the folder against what we expect to have been exported (reducing
manual intervention). It can also force dcm2bids to properly export repeat
sessions into the same folder, where newer versions will simply ignore them.
"""
from collections import OrderedDict
from glob import glob
from json import JSONDecodeError
import logging
import os
import re

from datman.scanid import make_filename
from datman.utils import (splitext, get_extension, write_json, read_json,
                          filter_niftis, read_blacklist, get_relative_source)

from dcm2bids import dcm2bids, Dcm2bids
from dcm2bids.sidecar import Acquisition

from .base import SessionExporter

logger = logging.getLogger(__name__)

__all__ = ["BidsExporter", "NiiLinkExporter"]


class BidsExporter(SessionExporter):
    """An exporter that runs dcm2bids.
    """

    type = "bids"

    def __init__(self, config, session, experiment, bids_opts=None, **kwargs):
        self.dcm_dir = experiment.dcm_subdir
        self.bids_sub = session._ident.get_bids_name()
        self.bids_ses = session._ident.timepoint
        self.repeat = session._ident.session
        self.bids_folder = session.bids_root
        self.bids_tmp = os.path.join(session.bids_root, "tmp_dcm2bids",
                                     f"{session.bids_sub}_{session.bids_ses}")
        self.output_dir = session.bids_path
        self.keep_dcm = bids_opts.keep_dcm if bids_opts else False
        self.force_dcm2niix = bids_opts.force_dcm2niix if bids_opts else False
        self.clobber = bids_opts.clobber if bids_opts else False
        self.log_level = bids_opts.log_level if bids_opts else "INFO"
        self.dcm2bids_config = bids_opts.dcm2bids_config if bids_opts else None
        self.refresh = bids_opts.refresh if bids_opts else False

        # Can be removed if dcm2bids patches the log issue
        self.set_log_level()

        super().__init__(config, session, experiment, **kwargs)

    def set_log_level(self):
        """Set the dcm2bids log level based on user input.

        dcm2bids doesnt properly adjust the log level based on user input,
        so adjust it here to make it less spammy.
        """
        if isinstance(self.log_level, str):
            try:
                level = getattr(logging, self.log_level)
            except AttributeError:
                logger.info(
                    f"Unrecognized log level {self.log_level}. "
                    "Log level set to 'warn'"
                )
                level = logging.WARNING
        else:
            level = self.log_level

        for logger_name in logging.root.manager.loggerDict:
            if not logger_name.startswith('dcm2bids'):
                continue
            # Get it this way instead of accessing the dict directly in
            # case the dict still contains a placeholder
            logging.getLogger(logger_name).setLevel(level)

    def get_expected_scans(self):
        return self.get_xnat_map()

    def get_actual_scans(self):
        return self.get_local_map()

    def check_contents(self, expected, actual):
        misnamed = {}
        missing = {}
        for scan in expected:
            if scan not in actual:
                # Ignore scans with error files from prev dcm2niix fails
                for out_name in expected[scan]:
                    err_file = os.path.join(
                        self.bids_folder, out_name + "_niix.err"
                    )
                    if os.path.exists(err_file):
                        continue

                    blacklisted_err = os.path.join(
                        self.output_dir, "blacklisted",
                        os.path.basename(out_name) + "_niix.err")
                    if os.path.exists(blacklisted_err):
                        continue

                    missing.setdefault(scan, []).append(out_name)
                continue

            # Handle split series
            if len(expected[scan]) > 1:
                xnat_parser = self.get_xnat_parser()
                dest_acqs = []
                for acq in xnat_parser.acquisitions:
                    try:
                        found_scan = acq.srcSidecar.scan
                    except AttributeError:
                        continue
                    if found_scan == scan:
                        dest_acqs.append(acq)

                local_parser = self.get_local_parser()
                src_acqs = []
                for acq in local_parser.acquisitions:
                    sidecar = acq.srcSidecar
                    if str(sidecar.data['SeriesNumber']) in [
                            scan.series, "10" + scan.series]:
                        src_acqs.append(acq)

                for src_acq in src_acqs:
                    found = None
                    suffix = re.sub(r'_run-\d+', '', src_acq.suffix)
                    for dst_acq in dest_acqs:
                        if suffix == re.sub(r'_run-\d+', '', dst_acq.suffix):
                            found = dst_acq
                    if not found:
                        continue
                    expected_name = found.dstRoot
                    actual_name = src_acq.srcRoot.replace(self.bids_folder, "")
                    misnamed[actual_name] = expected_name
                continue

            expected_name = expected[scan][0]
            actual_name = actual[scan][0]
            if expected_name == actual_name:
                continue
            misnamed[actual_name] = expected_name

        return misnamed, missing

    def handle_missing_scans(self, missing_scans, niix_log):
        # This should be refactored
        series_log = parse_niix_log(niix_log, self.experiment.scans)
        for scan in missing_scans:
            if scan.series not in series_log:
                error_msg = (
                    f"dcm2niix failed to create nifti for {scan}. "
                    "Data may require manual intervention or blacklisting.\n"
                )
            else:
                error_msg = "\n".join(series_log[scan.series])

            for fname in missing_scans[scan]:
                logger.error(error_msg)
                self.write_error_file(fname, error_msg)

    def write_error_file(self, fname, error_msg):
        out_name = os.path.join(self.bids_folder, fname + "_niix.err")

        root_dir, _ = os.path.split(out_name)
        try:
            os.makedirs(root_dir)
        except FileExistsError:
            pass

        try:
            with open(out_name, "w") as fh:
                fh.writelines(error_msg)
        except Exception as e:
            logger.error(f"Failed to write error log. {e}")
            logger.error(
                "Session may continuously redownload if log is not created."
            )

    def fix_run_numbers(self, misnamed_scans):
        # Rename files already in the subject dir first, to
        # avoid accidentally clobbering any existing misnamed files
        # with os.rename
        for orig_name in misnamed_scans:
            if not orig_name.startswith("sub-"):
                continue
            self.rename_scan(orig_name, misnamed_scans[orig_name])

        for orig_name in misnamed_scans:
            if not orig_name.startswith("tmp_dcm2bids"):
                continue
            self.rename_scan(orig_name, misnamed_scans[orig_name])

    def rename_scan(self, orig_name, dest_name):
        source_path = os.path.join(self.bids_folder, orig_name)
        dest_path = os.path.join(self.bids_folder, dest_name)

        if not os.path.exists(os.path.dirname(dest_path)):
            os.makedirs(os.path.dirname(dest_path))

        for found in glob(source_path + "*"):
            _, ext = splitext(found)
            os.rename(found, dest_path + ext)

    def get_xnat_parser(self):
        participant = dcm2bids.Participant(
            self.bids_sub, session=self.bids_ses
        )
        bids_conf = dcm2bids.load_json(self.dcm2bids_config)

        xnat_sidecars = []
        for scan in self.experiment.scans:
            xnat_sidecars.append(FakeSidecar(scan))

        if int(self.repeat) > 1:
            # Add repeat number to xnat side cars to avoid mistakenly
            # tagging them as repeat 01
            for sidecar in xnat_sidecars:
                sidecar.data['Repeat'] = self.repeat

            # This session is a repeat and files from previous scan(s) must
            # be included or run numbers will be wrong.
            for item in self.find_outputs(".json", start_dir=self.output_dir):
                sidecar = dcm2bids.Sidecar(item)
                if 'Repeat' not in sidecar.data:
                    # Assume repeat == 1 if not in json file
                    xnat_sidecars.append(sidecar)
                elif int(sidecar.data['Repeat']) < int(self.repeat):
                    # Include previous sessions' scans without duplicating
                    # the current sessions' entries.
                    xnat_sidecars.append(sidecar)

        # xnat_sidecars = sorted(
        #     xnat_sidecars, key=lambda x: int(x.data['SeriesNumber'])
        # )
        xnat_sidecars = sorted(
            xnat_sidecars,
            key=lambda x: (int(x.data['Repeat'] if 'Repeat' in x.data else 1),
                           int(x.data['SeriesNumber']))
        )

        xnat_parser = dcm2bids.SidecarPairing(
            xnat_sidecars, remove_criteria(bids_conf['descriptions'])
        )
        xnat_parser.build_graph()
        xnat_parser.build_acquisitions(participant)

        # Use this to find scans that have extra 'criteria' for single match
        extra_acqs = []
        for sidecar, descriptions in xnat_parser.graph.items():
            if len(descriptions) > 1:
                for descr in descriptions:
                    acq = Acquisition(participant, srcSidecar=sidecar, **descr)
                    extra_acqs.append(acq)

        xnat_parser.acquisitions.extend(extra_acqs)
        xnat_parser.find_runs()

        return xnat_parser

    def get_local_parser(self):
        participant = dcm2bids.Participant(
            self.bids_sub, session=self.bids_ses
        )

        bids_conf = dcm2bids.load_json(self.dcm2bids_config)

        local_sidecars = []
        for search_path in [self.output_dir, self.bids_tmp]:
            for item in self.find_outputs(".json", start_dir=search_path):
                sidecar = dcm2bids.Sidecar(item)
                if ('Repeat' in sidecar.data and
                        sidecar.data['Repeat'] == self.repeat):
                    local_sidecars.append(sidecar)
                elif ('Repeat' not in sidecar.data and self.repeat == '01'):
                    # Assume untagged sidecars all belong to the first session
                    local_sidecars.append(sidecar)

        local_sidecars = sorted(local_sidecars)

        parser = dcm2bids.SidecarPairing(
            local_sidecars, bids_conf["descriptions"]
        )
        parser.build_graph()
        parser.build_acquisitions(participant)
        parser.find_runs()

        return parser

    def _get_scan_dir(self, download_dir):
        if self.refresh:
            # Use existing tmp_dir instead of raw dcms
            return self.bids_tmp
        return os.path.join(download_dir, self.dcm_dir)

    def outputs_exist(self):
        if self.refresh:
            logger.info(
                f"Re-comparing existing tmp folder for {self.output_dir}"
                "to dcm2bids config to pull missed series."
            )
            return False

        if self.clobber:
            logger.info(
                f"{self.output_dir} will be overwritten due to clobber option."
            )
            return False

        expected_scans = self.get_expected_scans()
        actual_scans = self.get_actual_scans()
        _, missing = self.check_contents(expected_scans, actual_scans)
        if missing:
            return False

        return True

    def needs_raw_data(self):
        return not self.outputs_exist() and not self.refresh

    def export(self, raw_data_dir, **kwargs):
        if self.outputs_exist():
            return

        # Was this ever needed? The class should never have been made.
        # if not DCM2BIDS_FOUND:
        #     logger.info(f"Unable to export to {self.output_dir}, "
        #                 "Dcm2Bids not found.")
        #     return

        if self.dry_run:
            logger.info(f"Dry run: Skipping bids export to {self.output_dir}")
            return

        # Store user settings in case they change during export
        orig_force = self.force_dcm2niix
        orig_refresh = self.refresh

        if int(self.repeat) > 1:
            # Must force dcm2niix export if it's a repeat.
            self.force_dcm2niix = True

        self.make_output_dir()

        try:
            self.run_dcm2bids(raw_data_dir)
        except Exception as e:
            logger.error(f"Failed to extract data. {e}")

        try:
            self.add_repeat_num()
        except (PermissionError, JSONDecodeError):
            logger.error(
                "Failed to add repeat numbers to sidecars in "
                f"{self.output_dir}. If a repeat scan is added, scans may "
                "incorrectly be tagged as belonging to the later repeat."
            )

        if int(self.repeat) > 1:
            # Must run a second time to move the new niftis out of the tmp dir
            self.force_dcm2niix = False
            self.refresh = True
            try:
                self.run_dcm2bids(raw_data_dir)
            except Exception as e:
                logger.error(f"Failed to extract data. {e}")

        self.force_dcm2niix = orig_force
        self.refresh = orig_refresh

    def run_dcm2bids(self, raw_data_dir, tries=2):
        if tries == 0:
            logger.error(f"Dcm2bids failed to run for {self.output_dir}.")
            return

        input_dir = self._get_scan_dir(raw_data_dir)

        if self.refresh and not os.path.exists(input_dir):
            logger.error(
                f"Cannot refresh contents of {self.output_dir}, no "
                f"files found at {input_dir}.")
            return

        # Only run dcm2niix the first try, on the second just export the
        # tmp folder contents from the last run
        force_niix = False if tries == 1 else self.force_dcm2niix

        expected_scans = self.get_expected_scans()
        actual_scans = self.get_actual_scans()
        rename, missing = self.check_contents(expected_scans, actual_scans)

        if rename:
            self.fix_run_numbers(rename)

        niix_log = []
        try:
            dcm2bids_app = Dcm2bids(
                input_dir,
                self.bids_sub,
                self.dcm2bids_config,
                output_dir=self.bids_folder,
                session=self.bids_ses,
                clobber=self.clobber,
                forceDcm2niix=force_niix,
                log_level=self.log_level
            )
            dcm2bids_app.run()
        except Exception as exc:
            logger.error(
                f"Dcm2Bids error for {self.output_dir}. {type(exc)}: {exc}"
            )
            niix_log = exc.stdout
            self.run_dcm2bids(raw_data_dir, tries=tries - 1)

        if not niix_log:
            # No dcm2niix conversion errors to handle
            return

        expected_scans = self.get_expected_scans()
        actual_scans = self.get_actual_scans()
        rename, missing = self.check_contents(expected_scans, actual_scans)

        if missing:
            self.handle_missing_scans(missing, niix_log)

        if rename:
            self.fix_run_numbers(rename)

    def report_export_issues(self, xnat_map, local_map, series_log):
        rename = {}
        missing = {}
        for scan in xnat_map:
            if scan not in local_map:
                # Note the [0] should probably be dropped. kept for testing.
                missing[scan] = xnat_map[scan][0]
                continue
            if len(xnat_map[scan]) != 1:
                continue
            if len(local_map[scan]) != 1:
                continue
            if xnat_map[scan][0] == local_map[scan][0]:
                continue
            rename[local_map[scan][0]] = xnat_map[scan][0]

        for scan in missing:
            if scan.series not in series_log:
                print(f"{scan} -> {missing[scan]} failed dcm2niix export")
        for orig_name in rename:
            print(f"Renaming {orig_name} -> {rename[orig_name]}")

        return rename, missing

    def get_xnat_map(self):
        xnat_parser = self.get_xnat_parser()
        xnat_map = {}
        for acq in xnat_parser.acquisitions:
            try:
                xnat_map.setdefault(acq.srcSidecar.scan, []).append(
                    acq.dstRoot)
            except AttributeError:
                # acqs belonging to previous sessions don't have
                # srcSidecar.scan and should not be in xnat_map
                pass
        return xnat_map

    def get_local_map(self):
        local_parser = self.get_local_parser()
        # Map exported local scans to the xnat series
        local_map = {}
        xnat_series_nums = [scan.series for scan in self.experiment.scans]
        for acq in local_parser.acquisitions:
            sidecar = acq.srcSidecar
            if ('Repeat' in sidecar.data and
                    sidecar.data['Repeat'] != self.repeat):
                continue
            if 'SeriesNumber' not in sidecar.data:
                continue
            series = str(sidecar.data['SeriesNumber'])
            if series not in xnat_series_nums:
                if len(series) < 3:
                    continue
                # This may be one of the split series, which get '10' prefixed
                # strip it and check again
                # Convert to int to trim preceding zeries
                tmp_series = str(int(str(series)[2:]))
                if tmp_series not in xnat_series_nums:
                    # It's just not a recognized series
                    continue
                # It IS a prefixed one, so replace with orig num
                series = tmp_series
            found = None
            for scan in self.experiment.scans:
                if scan.series == str(series):
                    found = scan
            if not found:
                continue

            # Handle previously renamed series
            # This happens when there are multiple runs but an
            # early one has completely failed to extract.
            # (i.e. dcm2bids thinks the run number differs from what it
            # _should_ be if all had extracted)
            dst_path = os.path.join(self.bids_folder, acq.dstRoot)
            if dst_path != acq.srcRoot:
                dst_path = acq.srcRoot.replace(self.bids_folder, "")
            else:
                dst_path = acq.dstRoot

            local_map.setdefault(found, []).append(dst_path)
        return local_map

    def add_repeat_num(self):
        orig_contents = self.get_sidecars()

        for path in orig_contents:
            if orig_contents[path].get("Repeat"):
                continue

            logger.info(f"Adding repeat num {self.repeat} to sidecar {path}")
            orig_contents[path]["Repeat"] = self.repeat
            write_json(path, orig_contents[path])

    def find_outputs(self, ext, start_dir=None):
        """Find output files with the given extension.
        """
        if not ext.startswith("."):
            ext = "." + ext

        if not start_dir:
            start_dir = self.output_dir

        found = []
        for root, _, files in os.walk(start_dir):
            for item in files:
                if item.endswith(ext):
                    found.append(os.path.join(root, item))
        return found

    def get_sidecars(self):
        sidecars = self.find_outputs(".json")
        sidecars.extend(self.find_outputs(".json", start_dir=self.bids_tmp))
        contents = {path: read_json(path) for path in sidecars}
        return contents

    def find_missing_scans(self):
        """Find scans that exist on xnat but are missing from the bids folder.
        """
        class FakeSidecar(dcm2bids.Sidecar):
            """Turns XNAT series descriptions into pseudo-sidecars.
            """
            def __init__(self, xnat_scan):
                self.scan = xnat_scan
                self.data = xnat_scan
                self.compKeys = dcm2bids.DEFAULT.compKeys

                # Placeholders for compatibility with dcm2bids.Sidecar
                self.root = (
                    f"/tmp/{xnat_scan.series}"
                    + f"_{xnat_scan.description}"
                    + f"_{xnat_scan.subject}"
                )
                self.filename = f"{self.root}.json"
                self.data["SidecarFilename"] = self.filename

            @property
            def data(self):
                return self._data

            @data.setter
            def data(self, scan):
                self._data = OrderedDict()
                self._data['SeriesDescription'] = scan.description
                self._data['SeriesNumber'] = scan.series

            def __repr__(self):
                return f"<FakeSidecar {self.data['SeriesDescription']}>"

        def get_expected_names(participant, sidecars, bids_conf):
            parser = dcm2bids.SidecarPairing(
                sidecars, bids_conf["descriptions"]
            )
            parser.build_graph()
            parser.build_acquisitions(participant)
            parser.find_runs()
            return [acq.dstRoot for acq in parser.acquisitions]

        def remove_criteria(descriptions):
            trim_conf = []
            for descr in bids_conf['descriptions']:
                new_descr = descr.copy()
                if len(descr['criteria']) > 1:
                    new_descr['criteria'] = OrderedDict()
                    new_descr['criteria']['SeriesDescription'] = descr[
                        'criteria']['SeriesDescription']
                trim_conf.append(new_descr)
            return trim_conf

        participant = dcm2bids.Participant(
            self.bids_sub, session=self.bids_ses
        )

        bids_conf = dcm2bids.load_json(self.dcm2bids_config)

        local_sidecars = []
        for search_path in [self.output_dir, self.bids_tmp]:
            for item in self.find_outputs(".json", start_dir=search_path):
                sidecar = dcm2bids.Sidecar(item)
                if ('Repeat' in sidecar.data and
                        sidecar.data['Repeat'] != self.repeat):
                    continue
                local_sidecars.append(sidecar)
        local_sidecars = sorted(local_sidecars)

        xnat_sidecars = []
        for scan in self.experiment.scans:
            xnat_sidecars.append(FakeSidecar(scan))
        xnat_sidecars = sorted(xnat_sidecars)

        local_scans = get_expected_names(
            participant, local_sidecars, bids_conf
        )

        # Use a more permissive bids_conf when finding xnat acqs
        xnat_parser = dcm2bids.SidecarPairing(
            xnat_sidecars, remove_criteria(bids_conf['descriptions'])
        )
        xnat_parser.build_graph()
        xnat_parser.build_acquisitions(participant)
        # Use this to find scans that have extra 'criteria' for single match
        extra_acqs = []
        for sidecar, descriptions in xnat_parser.graph.items():
            if len(descriptions) > 1:
                for descr in descriptions:
                    acq = Acquisition(participant, srcSidecar=sidecar, **descr)
                    extra_acqs.append(acq)
        xnat_parser.acquisitions.extend(extra_acqs)
        xnat_parser.find_runs()
        xnat_scans = [acq.dstRoot for acq in xnat_parser.acquisitions]

        missing_scans = []
        for scan in xnat_scans:
            if scan not in local_scans:
                if "run-01" in scan:
                    norun_scan = scan.replace("_run-01", "")
                    if norun_scan not in local_scans:
                        missing_scans.append(scan)
                else:
                    missing_scans.append(scan)

        extra_scans = []
        for scan in local_scans:
            if scan not in xnat_scans:
                if "run-01" in scan:
                    norun_scan = scan.replace("_run-01", "")
                    if norun_scan not in xnat_scans:
                        extra_scans.append(scan)
                else:
                    extra_scans.append(scan)

        return missing_scans, extra_scans


class NiiLinkExporter(SessionExporter):
    """Populates a study's nii folder with symlinks pointing to the bids dir.
    """

    type = "nii_link"
    ext = ".nii.gz"

    def __init__(self, config, session, experiment, **kwargs):
        self.ident = session._ident
        self.output_dir = session.nii_path
        self.bids_path = session.bids_path
        self.config = config
        self.tags = config.get_tags(site=session.site)

        super().__init__(config, session, experiment, **kwargs)

        self.dm_names = self.get_dm_names()
        self.bids_names = self.get_bids_niftis()
        self.name_map = self.match_dm_to_bids(self.dm_names, self.bids_names)

    def get_dm_names(self):
        """Get the datman-style scan names for an entire XNAT experiment.

        Returns:
            :obj:`list`: A list of datman-style names for all scans found
                for the session on XNAT.
        """
        names = []
        for scan in self.experiment.scans:
            names.extend(scan.names)
        return names

    def get_bids_niftis(self):
        """Get all nifti files from a BIDS session.

        Returns:
            :obj:`list`: A list of full paths (minus the file extension) to
                each bids format nifti file in the session.
        """
        bids_niftis = []
        for path, _, files in os.walk(self.bids_path):
            niftis = filter_niftis(files)
            for item in niftis:
                basename = item.replace(get_extension(item), "")
                nii_path = os.path.join(path, basename)
                if self.belongs_to_session(nii_path):
                    bids_niftis.append(nii_path)
        return bids_niftis

    def belongs_to_session(self, nifti_path):
        """Check if a nifti belongs to this repeat or another for this session.

        Args:
            nifti_path (str): A nifti file name from the bids folder (minus
                extension).

        Returns:
            bool: True if the nifti file belongs to this particular
                repeat. False if it belongs to another repeat.
        """
        try:
            side_car = read_json(nifti_path + ".json")
        except FileNotFoundError:
            # Assume it belongs if a side car cant be read.
            return True

        repeat = side_car.get("Repeat")
        if not repeat:
            # No repeat is recorded in the json, assume its for this session.
            return True

        return repeat == self.ident.session

    def match_dm_to_bids(self, dm_names, bids_names):
        """Match each datman file name to its BIDS equivalent.

        Args:
            dm_names (:obj:`list`): A list of all valid datman scan names found
                for this session on XNAT.
            bids_names (:obj:`list`): A list of all bids files (minus
                extensions) that exist for this session.

        Returns:
            :obj:`dict`: A dictionary matching the intended datman file name to
                the full path (minus extension) of the same series in the bids
                folder. If no matching bids file was found, it will instead be
                matched to the string 'missing'.
        """
        name_map = {}
        for tag in self.tags:
            try:
                bids_conf = self.tags.get(tag)['Bids']
            except KeyError:
                logger.info(f"No bids config found for tag {tag}. Can't match "
                            "bids outputs to a datman-style name.")
                continue

            matches = self._find_matching_files(bids_names, bids_conf)

            for item in matches:
                try:
                    dm_name = self.make_datman_name(item, tag)
                except Exception as e:
                    logger.error(
                        f"Failed to assign datman style name to {item}. "
                        f"Reason - {e}")
                    continue
                name_map[dm_name] = item

        for scan in dm_names:
            output_file = os.path.join(self.output_dir, scan + self.ext)
            if scan not in name_map and not os.path.exists(output_file):
                # An expected scan is missing from the bids folder and
                # hasnt already been exported directly with dcm2niix
                name_map[scan] = "missing"

        return name_map

    def make_datman_name(self, bids_path, scan_tag):
        """Create a Datman-style file name for a bids file.

        Args:
            bids_path (str): The full path (+/- extension) of a bids file to
                create a datman name for.
            scan_tag (str): A datman style tag to apply to the bids scan.

        Returns:
            str: A valid datman style file name (minus extension).
        """
        side_car = read_json(bids_path + ".json")
        description = side_car['SeriesDescription']
        num = self.get_series_num(side_car)

        dm_name = make_filename(self.ident, scan_tag, num, description)
        return dm_name

    def get_series_num(self, side_car):
        """Find the correct series number for a scan.

        Most JSON side car files have the correct series number already.
        However, series that are split during nifti conversion (e.g.
        FMAP-AP/-PA) end up with one of the two JSON files having a modified
        series number. This function will default to the XNAT series number
        whenever possible, for accuracy.

        Args:
            side_car (:obj:`dict`): A dictionary containing the contents of a
                scan's JSON side car file.

        Returns:
            str: The most accurate series number found for the scan.
        """
        description = side_car['SeriesDescription']
        num = str(side_car['SeriesNumber'])
        xnat_scans = [item for item in self.experiment.scans
                      if item.description == description]

        if not xnat_scans:
            return num

        if len(xnat_scans) == 1:
            return xnat_scans[0].series

        # Catch split series (dcm2bids adds 1000 to the series number of
        # one of the two files)
        split_num = str(int(num) - 1000).zfill(2)
        if any([split_num == str(item.series).zfill(2)
                for item in xnat_scans]):
            return split_num

        return num

    def _find_matching_files(self, bids_names, bids_conf):
        """Search a list of bids files to find series that match a datman tag.

        Args:
            bids_names (:obj:`list`): A list of bids file names to search
                through.
            bids_conf (:obj:`dict`): The bids configuration for a single tag
                from datman's configuration files.

        Returns:
            :obj:`list`: A list of full paths (minus extension) of bids files
                that match the tag configuration. If none match, an empty
                list will be returned.
        """
        matches = self._filter_bids(
            bids_names, bids_conf.get('class'), par_dir=True)
        matches = self._filter_bids(
            matches, bids_conf.get(self._get_label_key(bids_conf)))
        matches = self._filter_bids(matches, bids_conf.get('task'))
        matches = self._filter_bids(matches, bids_conf.get('dir'))
        # The below is used to more accurately match FMAP tags
        matches = self._filter_bids(matches, bids_conf.get('match_acq'))
        return matches

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

    def _get_label_key(self, bids_conf):
        """Return the name for the configuration's label field.
        """
        for key in bids_conf:
            if 'label' in key:
                return key
        return ""

    @classmethod
    def get_output_dir(cls, session):
        return session.nii_path

    def get_error_file(self, dm_file):
        return os.path.join(self.output_dir, dm_file + ".err")

    def outputs_exist(self):
        for dm_name in self.name_map:
            if read_blacklist(scan=dm_name, config=self.config):
                continue

            if self.name_map[dm_name] == "missing":
                if not os.path.exists(self.get_error_file(dm_name)):
                    return False
                continue

            full_path = os.path.join(self.output_dir, dm_name + self.ext)
            if not os.path.exists(full_path):
                return False
        return True

    def needs_raw_data(self):
        return False

    def export(self, *args, **kwargs):
        # Re run this before exporting, in case new BIDS files exist.
        self.bids_names = self.get_bids_niftis()
        self.name_map = self.match_dm_to_bids(self.dm_names, self.bids_names)

        if self.dry_run:
            logger.info("Dry run: Skipping making nii folder links for "
                        f"mapping {self.name_map}")
            return

        if self.outputs_exist():
            return

        self.make_output_dir()
        for dm_name, bids_name in self.name_map.items():
            if bids_name == "missing":
                self.report_errors(dm_name)
            else:
                self.make_link(dm_name, bids_name)
                # Run in case of previous errors
                self.clear_errors(dm_name)

    def report_errors(self, dm_file):
        """Create an error file to report probable BIDS conversion issues.

        Args:
            dm_file (:obj:`str`): A valid datman file name.
        """
        err_file = self.get_error_file(dm_file)
        contents = (
            f"{dm_file} could not be made. This may be due to a dcm2bids "
            "conversion error or an issue with downloading the raw dicoms. "
            "Please contact an admin as soon as possible.\n"
        )
        try:
            with open(err_file, "w") as fh:
                fh.write(contents)
        except Exception as e:
            logger.error(
                f"Failed to write error file for {dm_file}. Reason - {e}"
            )

    def clear_errors(self, dm_file):
        """Remove an error file from a previous BIDs export issue.

        Args:
            dm_file (:obj:`str`): A valid datman file name.
        """
        err_file = self.get_error_file(dm_file)
        try:
            os.remove(err_file)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.error(f"Failed while removing {err_file}. Reason - {e}")

    def make_link(self, dm_file, bids_file):
        """Create a symlink in the datman style that points to a bids file.

        Args:
            dm_file (:obj:`str`): A valid datman file name.
            bids_file (:obj:`str`): The full path to a bids file (minus
                extension.)
        """
        base_target = os.path.join(self.output_dir, dm_file)
        if read_blacklist(scan=base_target, config=self.config):
            logger.debug(f"Ignoring blacklisted scan {dm_file}")
            return

        for source in glob(bids_file + '*'):
            ext = get_extension(source)
            target = base_target + ext

            if os.path.islink(target) and not os.path.exists(target):
                # Remove a broken symlink
                try:
                    os.unlink(target)
                except Exception as exc:
                    logger.error(
                        f"Failed to remove broken symlink {target} - {exc}")
                    continue

            rel_source = get_relative_source(source, target)
            try:
                os.symlink(rel_source, target)
            except FileExistsError:
                pass
            except Exception as exc:
                logger.error(f"Failed to create {target}. Reason - {exc}")


class FakeSidecar(dcm2bids.Sidecar):
    """Turns XNAT series descriptions into pseudo-sidecars.
    """
    def __init__(self, xnat_scan):
        self.scan = xnat_scan
        self.data = xnat_scan
        self.compKeys = dcm2bids.DEFAULT.compKeys

        # Placeholders for compatibility with dcm2bids.Sidecar
        self.root = (
            f"/tmp/{xnat_scan.series}"
            + f"_{xnat_scan.description}"
            + f"_{xnat_scan.subject}"
        )
        self.filename = f"{self.root}.json"
        self.data["SidecarFilename"] = self.filename

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, scan):
        self._data = OrderedDict()
        self._data['SeriesDescription'] = scan.description
        self._data['SeriesNumber'] = scan.series

    def __repr__(self):
        return f"<FakeSidecar {self.data['SeriesDescription']}>"


def get_expected_names(participant, sidecars, bids_conf):
    parser = dcm2bids.SidecarPairing(
        sidecars, bids_conf["descriptions"]
    )
    parser.build_graph()
    parser.build_acquisitions(participant)
    parser.find_runs()
    return [acq.dstRoot for acq in parser.acquisitions]


def remove_criteria(descriptions):
    trim_conf = []
    for descr in descriptions:
        new_descr = descr.copy()
        if len(descr['criteria']) > 1:
            new_descr['criteria'] = OrderedDict()
            new_descr['criteria']['SeriesDescription'] = descr[
                'criteria']['SeriesDescription']
        trim_conf.append(new_descr)
    return trim_conf


def parse_niix_log(niix_output, xnat_scans):
    log_lines = sort_log(niix_output.split(b"\n"))

    series_log = {}
    for entry in log_lines:
        for line in entry:
            if line.startswith("Compress:"):
                nii_path = line.split(" ")[-1]
                series = str(int(os.path.basename(nii_path).split("_")[0]))
                # Handle split series (they get '10' prepended to series num)
                if series not in [scan.series for scan in xnat_scans]:
                    # drop the '10' prefix:
                    series = str(int(series[2:]))
                series_log.setdefault(series, []).extend(entry)
    return series_log


def sort_log(log_lines):
    """Sort a dcm2nix stdout log by series that produced each entry.
    """
    sorted_lines = []
    cur_idx = -1
    cur_entry = None
    for idx, line in enumerate(log_lines):
        line = line.decode('utf-8')
        if line.startswith("Convert "):
            if cur_entry:
                sorted_lines.append(cur_entry)
            cur_idx = idx
            cur_entry = []
        if cur_idx >= 0:
            cur_entry.append(line)
    return sorted_lines
