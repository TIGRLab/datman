"""Top-level package for datman."""
import warnings as _warnings
from .__about__ import (
    __version__,
    __copyright__,
    __credits__,
    __packagename__,
)

import datman.scanid
# If you remove this and dont manually import config before importing
# datman/dashboard.py you will get circular import errors. I am sooo sorry.
# We'd have to store hardcoded file paths in the dashboard database to
# otherwise fix this.
import datman.config


__all__ = [
    '__version__',
    '__copyright__',
    '__credits__',
    '__packagename__',
]

# cmp is not used by dmriprep, so ignore nipype-generated warnings
_warnings.filterwarnings('ignore', r'cmp not installed')
_warnings.filterwarnings('ignore', r'This has not been fully tested. Please report any failures.')
_warnings.filterwarnings('ignore', r"can't resolve package from __spec__ or __package__")
_warnings.simplefilter('ignore', DeprecationWarning)
_warnings.simplefilter('ignore', ResourceWarning)
