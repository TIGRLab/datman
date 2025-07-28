"""Export to bids format when using containerized dcm2bids (or versions >=3)
"""
import os
import logging
from dataclasses import dataclass
from pathlib import Path

import datman.config
from .base import SessionExporter
from datman.exceptions import MetadataException
from datman.utils import locate_metadata

logger = logging.getLogger(__name__)

__all__ = ["BidsExporter", "BidsOptions"]


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
        return


class NiiLinkExporter(SessionExporter):

    type = "nii_link"
    ext = ".nii.gz"

    def __init__(self, config, session, experiment, **kwargs):
        return

    def get_dm_names(self):
        """Get the datman-style scan names for an entire XNAT experiment.

        Returns:
            :obj:`dict`: A dict of series numbers matched to a list of
                datman-style names for all scans found for the session on XNAT.
        """
        # Difference number 1: This will return every series, even
        #   the ones that don't get assigned a name in the traditional
        names = {}
        for scan in self.experiment.scans:
            try:
                series = int(scan.series)
            except ValueError:
                # XNAT sometimes adds a string when it finds duplicate series
                # numbers. This is an error that should be resolved on the
                # server so these instances are safe to ignore.
                continue
            names.setdefault(series, []).extend(scan.names)
        return names

    # def get_bids_names(self):
