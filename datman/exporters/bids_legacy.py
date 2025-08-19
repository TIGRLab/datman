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
import logging
import os
import re
from collections import OrderedDict
from glob import glob
from json import JSONDecodeError

from dcm2bids import dcm2bids, Dcm2bids
from dcm2bids.sidecar import Acquisition

from datman.exceptions import MetadataException
from datman.utils import (splitext, write_json, read_json, locate_metadata)
from .base import SessionExporter

logger = logging.getLogger(__name__)

__all__ = ["BidsExporter", "BidsOptions"]


class BidsOptions:
    """Helper class for options related to exporting to BIDS format.
    """

    def __init__(self, config, keep_dcm=False, bids_out=None,
                 force_dcm2niix=False, clobber=False, dcm2bids_config=None,
                 log_level="INFO", refresh=False, **kwargs):
        self.keep_dcm = keep_dcm
        self.force_dcm2niix = force_dcm2niix
        self.clobber = clobber
        self.refresh = refresh
        self.bids_out = bids_out
        self.log_level = log_level
        self.dcm2bids_config = self.get_bids_config(
            config, bids_conf=dcm2bids_config)

    def get_bids_config(self, config, bids_conf=None):
        """Find the path to a valid dcm2bids config file.

        Args:
            config (:obj:`datman.config.config`): The datman configuration.
            bids_conf (:obj:`str`, optional): The user provided path to
                the config file. Defaults to None.

        Raises:
            datman.exceptions.MetadataException if a valid file cannot
                be found.

        Returns:
            str: The full path to a dcm2bids config file.
        """
        if bids_conf:
            path = bids_conf
        else:
            try:
                path = locate_metadata("dcm2bids.json", config=config)
            except FileNotFoundError as exc:
                raise MetadataException(
                    "No dcm2bids.json config file available for "
                    f"{config.study_name}") from exc

        if not os.path.exists(path):
            raise MetadataException("No dcm2bids.json settings provided.")

        return path


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
