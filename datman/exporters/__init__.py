import os
import importlib
import pkgutil
import logging

from .base import Exporter, SessionExporter, SeriesExporter

logger = logging.getLogger(__name__)

# Exclude bids from import until it's known which (if any) version of
# dcm2bids is in use
_exclude = {"bids", "bids_legacy"}

__all__ = []


def _load_contents(module_name):
    """Load the contents of a module file in the 'exporters' folder.
    """
    module = importlib.import_module(f".{module_name}", package=__name__)

    if hasattr(module, "__all__"):
        contents = module.__all__
    else:
        contents = [item for item in dir(module) if not item.startswith("_")]

    for item in contents:
        globals()[item] = getattr(module, item)

    __all__.extend(contents)


# Load everything from exporters folder (except bids exporters) so contents
# can be accessed as 'datman.exporters' instead of 'datman.exporters.xxx'
for _, module_name, _ in pkgutil.iter_modules([os.path.dirname(__file__)]):
    if module_name in _exclude:
        continue
    _load_contents(module_name)

# Load the appropriate version of the bids exporters (if any)
DCM2BIDS_FOUND = False

if os.getenv("BIDS_CONTAINER"):
    # Container is in use, load bids.py
    _load_contents("bids")
    DCM2BIDS_FOUND = True
else:
    try:
        from dcm2bids import dcm2bids, Dcm2bids
    except ImportError:
        # dcm2bids is either not installed or version >= 3
        try:
            import dcm2bids
        except ImportError:
            # No dcm2bids available at all
            DCM2BIDS_FOUND = False
        else:
            # dcm2bids is installed and version > 3, use bids.py
            _load_contents("bids")
            DCM2BIDS_FOUND = True
    else:
        # dcm2bids is installed and version < 3, use bids_legacy.py
        _load_contents("bids_legacy")
        DCM2BIDS_FOUND = True


def get_exporter(key: str, scope="series") -> Exporter:
    """Find an exporter class for a given key identifier.

    Args:
        key (:obj:`str`): The 'type' identifier of a defined exporter (e.g.
            'nii').
        scope (:obj:`str`, optional): Whether to search for a series or session
            exporter. Defaults to 'series'.

    Returns:
        :obj:`datman.exporters.base.Exporter`: The Exporter subclass
            if one is defined, or else None.
    """
    if scope == "series":
        exp_set = SERIES_EXPORTERS
    else:
        exp_set = SESSION_EXPORTERS

    try:
        exporter = exp_set[key]
    except KeyError:
        logger.error(
            f"Unrecognized format {key} for {scope}, no exporters found.")
        return None
    return exporter


SESSION_EXPORTERS = {
    exp.type: exp for exp in SessionExporter.__subclasses__()
}

SERIES_EXPORTERS = {
    exp.type: exp for exp in SeriesExporter.__subclasses__()
}

__all__.extend(["get_exporter", "SESSION_EXPORTERS", "SERIES_EXPORTERS"])
