"""Export to bids format when using containerized dcm2bids (or versions >=3)
"""
import os
import logging
import json
import re
from glob import glob
from dataclasses import dataclass
from pathlib import Path

import datman.config
from .base import SessionExporter
from datman.exceptions import MetadataException
from datman.utils import (locate_metadata, read_blacklist, get_relative_source,
                          get_extension, write_json, run)
from datman.scanid import make_filename

logger = logging.getLogger(__name__)

__all__ = ["BidsExporter", "NiiLinkExporter", "BidsOptions"]


@dataclass
class BidsOptions:
    """Helper class for options related to exporting to BIDS format.
    """
    dm_config: datman.config.config
    keep_dcm: bool = False
    bids_out: str | None = None
    force_dcm2niix: bool = False
    clobber: bool = False
    dcm2bids_config: str | None = None
    log_level: str = "INFO"
    refresh: bool = False
    extra_opts: list = None

    def __post_init__(self):
        self.dcm2bids_config = self.get_bids_config(
            self.dm_config,
            bids_conf=self.dcm2bids_config
        )

    def get_bids_config(self, config: datman.config.config,
                        bids_conf: str | None = None) -> str:
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

    type = "bids"

    def __init__(self, config, session, importer, bids_opts=None, **kwargs):
        self.dcm_dir = importer.dcm_subdir
        self.bids_sub = session._ident.get_bids_name()
        self.bids_ses = session._ident.timepoint
        self.repeat = session._ident.session
        self.bids_folder = session.bids_root
        self.bids_tmp = os.path.join(session.bids_root, "tmp_dcm2bids",
                                     f"{session.bids_sub}_{session.bids_ses}")
        self.output_dir = session.bids_path
        self.refresh = bids_opts.refresh
        self.clobber = bids_opts.clobber
        self.opts = bids_opts

        super().__init__(config, session, importer, **kwargs)

    def needs_raw_data(self):
        return not self.outputs_exist() and not self.refresh

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

        if not os.path.exists(self.output_dir):
            return False

        if not self.session._bids_inventory:
            return False

        # Assume everything exists if anything does :(
        return True

    def export(self, raw_data_dir, **kwargs):
        if self.outputs_exist():
            return

        if self.dry_run:
            logger.info(f"Dry run: Skipping bids export to {self.output_dir}")
            return

        # Store user settings in case they change during export
        orig_force = self.opts.force_dcm2niix
        orig_refresh = self.refresh

        # Does this still work for repeats?
        if int(self.repeat) > 1:
            # Must force dcm2niix export if it's a repeat.
            self.force_dcm2niix = True

        self.make_output_dir()

        try:
            self.run_dcm2bids(raw_data_dir)
        except Exception as e:
            logger.error(f"Failed to extract to BIDs - {e}")

        # For CLM CHO / basic format. Gotta make sure apptainer exists
        # apptainer run \
        # -B ${outputdir} \
        # /scratch/edickie/CLM01_pilots/containers/dcm2bids-3.2.0.sif \
        # -d ${outputdir}/dicoms/CLM01_CHO_00000003_01_SE01_MR/ \
        # -p "sub-CHO00000004" \
        # -s "ses-01" \
        # -c ${outputdir}/dcm2bids_3chorom.json \
        # -o ${outputdir}/bids \
        # --auto_extract_entities

        # Test command. Exporter may need to 'hang on to' the metadata folder
        # path and the file name for the dcm2bids.json (since the file given
        # can be named anything and shouldn't be assumed)
        # Note also: all bound paths must exist before running
        # apptainer run -B /scratch/dawn/temp_stuff/new_bids/test_archive/tmp_extract/:/input -B /scratch/dawn/temp_stuff/new_bids/test_archive/CLM01_CHO/metadata:/metadata -B /scratch/dawn/temp_stuff/new_bids/test_archive/CLM01_CHO/data/bids:/output ${BIDS_CONTAINER} -d /input -p "sub-CHO00000003" -s "ses-01" -c /metadata/dcm2bids.json -o /output --auto_extract_entities

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

        try:
            self.add_repeat_num()
        except (PermissionError, JSONDecodeError):
            logger.error(
                "Failed to add repeat numbers to sidecars in "
                f"{self.output_dir}. If a repeat scan is added, scans may "
                "incorrectly be tagged as belonging to the later repeat."
            )

    def run_dcm2bids(self, raw_data_dir):
        input_dir = self._get_scan_dir(raw_data_dir)

        if self.refresh and not os.path.exists(input_dir):
            logger.error(
                f"Cannot refresh contents of {self.output_dir}, no "
                f"files found at {input_dir}.")
            return

        cmd = self.make_command(input_dir)
        return_code, output = run(cmd)
        print(return_code)
        print(output)

    def _get_scan_dir(self, download_dir):
        if self.refresh:
            # Use existing tmp_dir instead of raw dcms
            return self.bids_tmp
        return download_dir

    def make_command(self, raw_data_dir):
        # CLM01_CHO_00000003_01_01

        # ???? is this an issue because I downloaded them?
        # dcm_dic = 'scans/9_DTI_HCP_b2400_AP_ADC'

        # bids_sub = 'CHO00000003'
        # bids_ses = '01'
        # repeat = '01'
        # bids_folder = '/scratch/dawn/temp_stuff/new_bids/test_archive/CLM01_CHO/data/bids/'
        # bids_tmp = '/scratch/dawn/temp_stuff/new_bids/test_archive/CLM01_CHO/data/bids/tmp_dcm2bids/sub-CHO00000003_ses-01'
        # output_dir = '/scratch/dawn/temp_stuff/new_bids/test_archive/CLM01_CHO/data/bids/sub-CHO00000003/ses-01'

        # raw_data_dir = "/scratch/dawn/temp_stuff/new_bids/test_archive/tmp_extract/"

        conf_dir, conf_file = os.path.split(self.opts.dcm2bids_config)

        container_path = os.getenv("BIDS_CONTAINER")
        if container_path:
            cmd = [
                "apptainer run",
                f"-B {raw_data_dir}:/input",
                f"-B {conf_dir}:/config",
                f"-B {self.bids_folder}:/output",
                f"{container_path}",
                "-d /input",
                f"-c /config/{conf_file}",
                "-o /output"
            ]
        else:
            cmd = [
                "dcm2bids",
                f"-d {raw_data_dir}",
                f"-c {self.opts.dcm2bids_config}",
                f"-o {self.bids_folder}"
            ]

        cmd.extend([
            f"-p '{self.bids_sub}'",
            f"-s '{self.bids_ses}'",
            f"-l {self.opts.log_level}"
        ])

        if self.opts.clobber:
            cmd.append("--clobber")

        if self.opts.force_dcm2niix:
            cmd.append("--forceDcm2niix")

        for item in self.opts.extra_opts:
            cmd.append(f"--{item}")

        return cmd

    def add_repeat_num(self):
        for sidecar in Path(self.output_dir).rglob("*.json"):

            contents = read_sidecar(sidecar)
            if not contents:
                continue

            if "Repeat" in contents:
                continue

            contents["Repeat"] = self.repeat
            # Remove "Path" so it doesnt get written to the output file
            del contents["Path"]
            write_json(sidecar, contents)


class NiiLinkExporter(SessionExporter):
    """Populates a study's nii folder with symlinks pointing to the bids dir.
    """

    type = "nii_link"
    ext = ".nii.gz"

    def __init__(self, config, session, importer, **kwargs):
        self.ident = session._ident
        self.output_dir = session.nii_path
        self.bids_path = session.bids_path
        self.repeat = session.session
        self.config = config
        self.tags = config.get_tags(site=session.site)

        super().__init__(config, session, importer, **kwargs)

    @classmethod
    def get_output_dir(cls, session):
        return session.nii_path

    def needs_raw_data(self):
        return False

    def outputs_exist(self):
        sidecars = self.get_bids_sidecars()
        name_map = self.make_dm_names(sidecars)

        for dm_name in name_map:

            if read_blacklist(scan=dm_name, config=self.config):
                continue

            full_path = os.path.join(self.output_dir, dm_name + self.ext)
            if not os.path.exists(full_path):
                return False

        return True

    def export(self, *args, **kwargs):
        sidecars = self.get_bids_sidecars()
        name_map = self.make_dm_names(sidecars)

        if self.dry_run:
            logger.info("Dry run: Skipping making nii folder links for "
                        f"mapping {name_map}")
            return

        if self.outputs_exist():
            return

        self.make_output_dir()

        for dm_name, bids_name in name_map.items():
            self.link_scan(dm_name, bids_name)

    def link_scan(self, dm_name: str, bids_root: Path | str):
        """Create a symlink in the datman style that points to a bids file.

        Args:
            dm_name (:obj:`str`): A valid datman file name.
            bids_root (:obj:`pathlib.Path`): The full path to a bids file
                (without an extension).
        """

        if read_blacklist(scan=dm_name, config=self.config):
            logger.debug(f"Ignoring blacklisted scan {dm_name}")
            return

        base_target = os.path.join(self.output_dir, dm_name)
        for source in glob(str(bids_root) + "*"):
            ext = get_extension(source)
            target = base_target + ext

            if is_broken_link(target):
                remove_broken_link(target)

            rel_source = get_relative_source(source, target)
            make_link(rel_source, target)

    def get_bids_sidecars(self) -> dict[int, list]:
        """Get all sidecars from the session's BIDS folder.

        Returns:
            :obj:`dict`: A map from the series number to a list of the JSON
                sidecar contents that result from that series.
        """
        sidecars = {}
        bids_folder = Path(self.bids_path)
        for sidecar in bids_folder.rglob("*.json"):

            contents = read_sidecar(sidecar)
            if not contents:
                continue

            if not self.matches_repeat(contents):
                continue

            if "SeriesNumber" not in contents:
                logger.debug(
                    "Ignoring malformed sidecar file (missing SeriesNumber): "
                    f"{sidecar}"
                )
                continue

            try:
                series_num = int(contents["SeriesNumber"])
            except ValueError:
                logger.debug(
                    f"Ignoring non-numeric series number in {sidecar}"
                )
                continue

            sidecars.setdefault(series_num, []).append(contents)

        self.fix_split_series_nums(sidecars)

        return sidecars

    def matches_repeat(self, sidecar: dict) -> bool:
        """Check if a sidecar matches the current session's 'repeat'.

        The 'repeat' number is used to track when a scan session was stopped
        and restarted during a visit. Most of the time it will be '01'.
        """
        if "Repeat" not in sidecar:
            # If this session is the first 'repeat' it's safe to assume an
            # untagged sidecar belongs to it, since usually there's only one
            # 'repeat' anyway.
            return self.repeat == "01"
        return sidecar["Repeat"] == self.repeat

    def fix_split_series_nums(self, sidecars: dict[int, list]
            ) -> dict[int, list]:
        """Attempt to correct series nums that have been prefixed with '10'.

        Some older versions of dcm2niix/dcm2bids liked to prefix half of a
        split series' number with '10' rather than allowing all sidecars
        to share the original series num. This attempts to identify when
        that has happened and find the original series number for these
        files.
        """
        all_series = [str(series).zfill(2) for series in sidecars]
        must_delete = []

        for series in sidecars:
            str_series = str(series)

            if not str_series.startswith("10"):
                continue

            if len(str_series) < 4:
                continue

            trimmed_series = str_series[2:]
            if trimmed_series not in all_series:
                # False alarm, probably not a mutated series number
                continue

            sidecars[int(trimmed_series)].extend(sidecars[series])
            must_delete.append(series)

        for series in must_delete:
            del sidecars[series]

        return sidecars

    def make_dm_names(self, sidecars: dict[int, list]) -> dict[str, Path]:
        """Create a datman-style name for each identifiable sidecar.

        Args:
            sidecars (`dict`): A dictionary mapping series numbers to a list
                of bids sidecar files generated by that series.

        Returns:
            dict: a dictionary mapping a datman-style filename to the bids
                sidecar path (minus extension) it belongs to.
        """
        found_names = {}
        reqs = self.get_tag_requirements()
        for series in sidecars:

            temp_names = {}
            for item in sidecars[series]:

                found = self.find_tag(item, reqs)

                if not found:
                    logger.debug(f"No tag matches {item['Path']}, ignoring.")
                    continue

                if len(found) > 1:
                    logger.debug(
                        f"Multiple tags ({found}) match sidecar "
                        f"{item['Path']}. Ignoring it. Please update "
                        "configuration so at most one tag matches."
                    )
                    continue

                dm_name = make_filename(
                    self.ident,
                    found[0],
                    series,
                    item["SeriesDescription"]
                )

                temp_names.setdefault(dm_name, []).append(item)

            found_names = self.handle_duplicate_names(found_names, temp_names)

        return found_names

    def get_tag_requirements(self) -> dict[str, dict]:
        """Read and reformat user configuration for all tags.

        As described in datman's configuration documentation, at a minimum each
        tag must define a 'SeriesDescription' regular expression. Tags
        may optionally include a 'Bids' section, alongside datman's
        'Pattern' and 'Count' fields for a tag to make it more restrictive or
        accurate.

        If included, the 'Bids' section should contain a list of sidecar field
        names to check when determining if a tag can by applied. These must
        match the sidecars fields verbatim (case-sensitive). Each field name
        may then point to either:

            - a literal string to be matched
            - a dictionary of settings

        The dictionary of settings may include the following keys:

        - **Pattern** (`str` or list, optional): May be a literal string or a
          regular expression in Python format (e.g., use `.*` not `*`), or a
          list of literal strings. Optional if `Exclude` is given. If omitted
          and `Exclude` is used, the presence of the field name alone
          excludes a sidecar from taking the tag.
        - **Regex** (`bool`, optional): Indicates whether `Pattern` is a regex
          or a string literal. Default is `False`.
        - **Exclude** (`bool`, optional): Indicates whether to exclude sidecars
          that match the pattern (i.e., take the inverse). Default is `False`.

        Examples:
            Below are some YAML examples of commonly used configuration.

            Prevent any sidecar with an 'IntendedFor' field from matching
            a tag:

                Bids:
                    IntendedFor:
                        Exclude: True

            Match a sidecar only if the PhaseEncodingDirection is exactly 'j':

                Bids:
                    PhaseEncodingDirection: 'j'

            Match a sidecar only if the ImageType contains 'DERIVED':

                Bids:
                    ImageType:
                        Pattern: 'DERIVED'
                        Regex: True

        Returns:
            A dictionary mapping each tag name to the requirements that
                must be met for a tag to be applied to a BIDs sidecar.
        """
        reqs = {}
        for tag in self.tags:

            conf = self.tags.get(tag)

            if is_malformed_conf(conf):
                logger.error(
                    f"Ignoring tag {tag} - Incorrectly configured. Each tag "
                    "must contain a 'Pattern' section and each 'Pattern', at "
                    "a minimum, must contain a 'SeriesDescription'. Consult "
                    "the docs for more info.")
                continue

            regex = conf["Pattern"]["SeriesDescription"]
            if isinstance(regex, list):
                regex = "|".join(regex)

            tag_reqs = {
                "SeriesDescription": {
                    "Pattern": regex,
                    "Regex": True,
                    "Exclude": False
                }
            }

            bids_conf = conf.get("Bids", {})
            for field in bids_conf:
                # Ensure consistent formatting for settings
                if isinstance(bids_conf[field], (str, int)):
                    pattern = str(bids_conf[field])
                    regex = False
                    exclude = False
                else:
                    pattern = bids_conf[field].get("Pattern", "")
                    if not isinstance(pattern, str):
                        pattern = str(pattern)
                    regex = bids_conf[field].get("Regex", False)
                    exclude = bids_conf[field].get("Exclude", False)

                tag_reqs[field] = {
                    "Pattern": pattern,
                    "Regex": regex,
                    "Exclude": exclude
                }

            reqs[tag] = tag_reqs
        return reqs

    def find_tag(self,
                 sidecar: dict,
                 requirements: dict | None = None) -> list:
        """Find which configured tags, if any, can be applied to a sidecar.

        Args:
            sidecar (`dict`): The contents of a json sidecar.
            requirements (`dict`, optional): The requirements to match
                each accepted tag. Default is 'None', in which case the
                default datman configuration will be consulted.

        Returns:
            A list of tag names that the sidecar matches.
        """
        if not requirements:
            requirements = self.get_tag_requirements()

        found = []
        for tag in requirements:

            match = True
            for field in requirements[tag]:
                pattern = requirements[tag][field].get("Pattern", "")
                is_regex = requirements[tag][field].get("Regex", False)
                exclude = requirements[tag][field].get("Exclude", False)

                if field not in sidecar:
                    if not exclude:
                        # Absence of an expected field fails tag match
                        match = False
                    continue

                if exclude and not pattern:
                    # Excluded field is in sidecar, so doesnt match tag
                    match = False
                    continue

                actual = sidecar[field]
                if not isinstance(actual, str):
                    actual = str(actual)

                if is_regex:
                    comparator = re.search
                else:
                    comparator = re.fullmatch

                if not comparator(pattern, actual, re.IGNORECASE):
                    match = False
                elif exclude:
                    # Tag does match, but settings indicate to take inverse
                    match = False
            if match:
                found.append(tag)

        return found

    def handle_duplicate_names(self,
                               existing_names: dict[str, str],
                               new_entries: dict[str, dict]
        ) -> dict[str, str]:
        """Make duplicated names unique.

        Sometimes, as with multi-echo scans, multiple BIDs files will create
        the same datman name. This ensures a unique name exists for each.

        Args:
            existing_names (`dict`): The dictionary to add the fixed name
                entries to.
            new_entries (`dict`): New entries that may contain duplicated
                datman-style names.

        Returns:
            dict[str, str]: The existing_names dictionary with all
                new entries merged in with unique names.
        """
        for name in new_entries:

            if len(new_entries[name]) == 1:
                existing_names[name] = remove_extension(
                    new_entries[name][0]["Path"]
                )
                continue

            for sidecar in new_entries[name]:
                if "EchoNumber" not in sidecar:
                    logger.error(
                        "Multiple BIDs files result in same file name "
                        f"'{name}'. Please update configuration to help "
                        f"identify file: {sidecar['Path']}"
                    )
                    continue
                new_name = name + f"_ECHO-{sidecar['EchoNumber']}"
                existing_names[new_name] = remove_extension(sidecar['Path'])

        return existing_names


def is_malformed_conf(config: dict) -> bool:
    """Check if a tag's configuration is unusably malformed.
    """
    if "Pattern" not in config:
        return True
    if "SeriesDescription" not in config["Pattern"]:
        return True
    return False

def remove_extension(path: Path) -> Path:
    """Remove all extensions from a path.
    """
    while path.suffix:
        path = path.with_suffix("")
    return path

def is_broken_link(symlink: str) -> bool:
    return os.path.islink(symlink) and not os.path.exists(symlink)

def remove_broken_link(target: str):
    try:
        os.unlink(target)
    except OSError as e:
        logger.error(f"Failed to remove broken symlink {target} - {e}")
    return

def make_link(source: str, target: str):
    try:
        os.symlink(source, target)
    except FileExistsError:
        pass
    except OSError as e:
        logger.error(f"Failed to create {target} - {e}")

def read_sidecar(sidecar: str | Path) -> dict:
    """Read the contents of a JSON sidecar file.

    NOTE: This adds the path of the file itself under the key 'Path'
    """
    if not isinstance(sidecar, Path):
        sidecar = Path(sidecar)

    try:
        contents = sidecar.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        logger.debug(
            f"Sidecar file is unreadable {sidecar} - {e}"
        )
        return {}

    try:
        data = json.loads(contents)
    except (json.JSONDecodeError, TypeError) as e:
        logger.debug(f"Invalid json sidecar {sidecar} - {e}")
        return {}

    data["Path"] = sidecar

    return data