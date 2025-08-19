"""Export to bids format when using containerized dcm2bids (or versions >=3)
"""
import os
import logging
import json
import dataclasses
from pathlib import Path

import datman.config
from datman.exceptions import MetadataException
from datman.utils import locate_metadata, write_json, run
from .base import SessionExporter, read_sidecar

logger = logging.getLogger(__name__)

__all__ = ["BidsExporter", "BidsOptions"]


@dataclasses.dataclass
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
    extra_opts: list = dataclasses.field(default_factory=list)

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
    """Populates a study's bids folder.
    """

    type = "bids"

    def __init__(
            self,
            config: datman.config.config,
            session: 'datman.scan.Scan',
            importer: 'datman.importers.SessionImporter',
            bids_opts: BidsOptions = None,
            **kwargs
    ):
        self.dcm_dir = importer.dcm_subdir
        self.bids_sub = session._ident.get_bids_name()
        self.bids_ses = session._ident.timepoint
        self.repeat = session._ident.session
        self.bids_folder = session.bids_root
        self.bids_tmp = os.path.join(session.bids_root, "tmp_dcm2bids",
                                     f"{session.bids_sub}_{session.bids_ses}")
        self.output_dir = session.bids_path
        self.opts = bids_opts

        super().__init__(config, session, importer, **kwargs)

    def needs_raw_data(self) -> bool:
        return not self.outputs_exist() and not self.opts.refresh

    def outputs_exist(self) -> bool:
        if self.opts.refresh:
            logger.info(
                f"Re-comparing existing tmp folder for {self.output_dir}"
                "to dcm2bids config to pull missed series."
            )
            return False

        if self.opts.clobber:
            logger.info(
                f"{self.output_dir} will be overwritten due to clobber option."
            )
            return False

        if not os.path.exists(self.output_dir):
            return False

        if not self.session._bids_inventory:
            return False

        # Assume everything exists if anything does
        return True

    def export(self, raw_data_dir: str, **kwargs):
        if self.outputs_exist():
            return

        if self.dry_run:
            logger.info(f"Dry run: Skipping bids export to {self.output_dir}")
            return

        if int(self.repeat) > 1:
            # Must force dcm2niix if it's a repeat.
            force_dcm2niix = True
        else:
            force_dcm2niix = self.opts.force_dcm2niix

        self.make_output_dir()

        try:
            self.run_dcm2bids(raw_data_dir, force_dcm2niix=force_dcm2niix)
        except Exception as e:
            logger.error(f"Failed to extract to BIDs - {e}")

        if int(self.repeat) > 1:
            # Must run a second time to move the new niftis out of the tmp dir
            try:
                self.run_dcm2bids(
                    raw_data_dir, force_dcm2niix=False, refresh=True
                )
            except Exception as e:
                logger.error(f"Failed to extract data. {e}")

        try:
            self.add_repeat_num()
        except (PermissionError, json.JSONDecodeError):
            logger.error(
                "Failed to add repeat numbers to sidecars in "
                f"{self.output_dir}. If a repeat scan is added, scans may "
                "incorrectly be tagged as belonging to the later repeat."
            )

    def run_dcm2bids(self, raw_data_dir: str, force_dcm2niix: bool = False,
                     refresh: bool = False):
        input_dir = self._get_scan_dir(raw_data_dir, refresh)

        if refresh and not os.path.exists(input_dir):
            logger.error(
                f"Cannot refresh contents of {self.output_dir}, no "
                f"files found at {input_dir}.")
            return

        cmd = self.make_command(input_dir, force_dcm2niix)
        return_code, output = run(cmd)
        if return_code:
            logger.error(f"Failed when running dcm2bids - {output}")

    def _get_scan_dir(self, download_dir: str, refresh: bool = False) -> str:
        if refresh:
            # Use existing tmp_dir instead of raw dcms
            return self.bids_tmp
        return download_dir

    def make_command(
            self, raw_data_dir: str, force_dcm2niix: bool = False
    ) -> list[str]:
        """Construct the dcm2bids command based on on user configuration.
        """

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

        if force_dcm2niix:
            cmd.append("--force_dcm2bids")

        for item in self.opts.extra_opts:
            cmd.append(f"--{item}")

        return cmd

    def add_repeat_num(self):
        """Add the sessions 'repeat' number to all of its json sidecars.

        This is used to allow us to track which files belong to which session
        when there's more than one (i.e. if there's an 01_02 and so forth
        instead of just 01_01)
        """
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
