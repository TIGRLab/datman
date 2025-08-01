"""Export to bids format when using containerized dcm2bids (or versions >=3)
"""
import os
import logging
import json
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

    def __init__(self, config, session, importer, bids_opts=None, **kwargs):
        self.dcm_dir = importer.dcm_subdir
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

        super().__init__(config, session, importer, **kwargs)
        return

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

        out_dir = Path(self.output_dir)
        if not out_dir.exists():
            return False

        json_files = out_dir.rglob("*.json")


        expected_scans = self.get_expected_scans()
        actual_scans = self.get_actual_scans()
        _, missing = self.check_contents(expected_scans, actual_scans)
        if missing:
            return False

        return True

    def get_contents(self):
        outputs = {}




class NiiLinkExporter(SessionExporter):
    """Populates a study's nii folder with symlinks pointing to the bids dir.
    """

    type = "nii_link"
    ext = ".nii.gz"

    def __init__(self, config, session, importer, **kwargs):
        self.ident = session._ident
        self.output_dir = session.nii_path
        self.bids_path = session.bids_path
        self.config = config
        self.tags = config.get_tags(site=session.site)

        super().__init__(config, session, importer, **kwargs)

        self.dm_names = self.get_dm_names()

    @classmethod
    def get_output_dir(cls, session):
        return session.nii_path

    def needs_raw_data(self):
        return False

    def get_dm_names(self):
        """Get the datman-style scan names for an entire XNAT experiment.

        This is used to
            1) Ensure the contents of the nii folder matches what may have
               been produced with an old-style NiiExporter
            2) To predict if an expected scan didn't extract correctly into
               the bids folder.

        Returns:
            dict: A map of each series number to the name (or
                names) the series would be exported under.
        """
        names = {}
        for scan in self.experiment.scans:
            try:
                series_num = int(scan.series)
            except ValueError:
                # Ignore xnat scans with non-numeric series numbers.
                # These are often of the form MR-XX and result from duplicated
                # uploads / errors when merging on xnat.
                continue
            names[series_num] = scan.names
        return names

    def get_bids_sidecars(self):
        """Get all sidecars from a BIDS session.

        Returns:
            :obj:`dict`: A map from the series number to the sidecar(s) that
                belong to that series.
        """
        sidecars = {}
        bids_folder = Path(self.bids_path)
        for sidecar in bids_folder.rglob("*.json"):
            try:
                contents = sidecar.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as e:
                logger.debug(
                    f"Ignoring unreadable json sidecar {sidecar} - {e}"
                )
                continue

            try:
                data = json.loads(contents)
            except (json.JSONDecodeError, TypeError) as e:
                logger.debug(f"Ignoring invalid json sidecar {sidecar} - {e}")
                continue

            data["path"] = sidecar

            if "SeriesNumber" not in data:
                continue

            # Need code later to handle split series (do they always
            # prefix series number with "10"?)
            # -> For new CALM sessions it doesnt, it just allows them to
            #   retain the original series number (and duplicates it)
            #   not sure if this is because of CALM or a change in dcm2niix
            #   or a change in dcm2bids
            try:
                series_num = int(data["SeriesNumber"])
            except ValueError:
                continue

            sidecars.setdefault(series_num, []).append(data)

        fix_split_series(sidecars)

        return sidecars


def get_bids_sidecars(bids_path, repeat):
    """Get all sidecars from a BIDS session.

    Returns:
        :obj:`dict`: A map from the series number to the sidecar(s) that
            belong to that series.
    """
    bids_folder = Path(bids_path)
    sidecars = {}

    for sidecar in bids_folder.rglob("*.json"):
        try:
            contents = sidecar.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            logger.debug(
                f"Ignoring unreadable json sidecar {sidecar} - {e}"
            )
            continue

        try:
            data = json.loads(contents)
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug(f"Ignoring invalid json sidecar {sidecar} - {e}")
            continue

        data["path"] = sidecar

        if "SeriesNumber" not in data:
            continue

        if "Repeat" not in data:
            if repeat == "01":
                # Assume sidecar belongs to this session, as there's
                # usually only 1 'repeat' anyway
                data["Repeat"] = "01"
            else:
                continue

        if data["Repeat"] != repeat:
            continue

        try:
            series_num = int(data["SeriesNumber"])
        except ValueError:
            continue

        sidecars.setdefault(series_num, []).append(data)

    fix_split_series(sidecars)

    return sidecars


def fix_split_series(sidecars):
    # Handle legacy dcm2bids/dcm2niix split sessions which recieved a
    # "10" prefix to their series numbers (e.g. '05' would become '1005'
    # for one half of a split fmap)
    all_str_series = [str(series).zfill(2) for series in sidecars]
    delete = []
    for series in sidecars:
        str_series = str(series)
        if not str_series.startswith("10"):
            continue
        if len(str_series) < 4:
            continue
        trimmed_series = str_series[2:]
        if trimmed_series not in all_str_series:
            # False alarm, just a weird custom series
            continue
        sidecars[int(trimmed_series)].extend(sidecars[series])
        delete.append(series)
    for series in delete:
        del sidecars[series]
    return sidecars