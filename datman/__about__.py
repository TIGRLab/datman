# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
"""Base module variables."""
from ._version import get_versions

__version__ = get_versions()["version"]
del get_versions

__packagename__ = "datman"
__copyright__ = "Copyright 2019, The TIGRLab"
__credits__ = (
    "Contributors: please check the ``.zenodo.json`` file at the "
    "top-level folder of the repository"
)
__url__ = "https://github.com/tigrlab/datman"

DOWNLOAD_URL = (
    f"https://github.com/tigrlab/{__packagename__}/archive/{__version__}.tar.gz"
)
