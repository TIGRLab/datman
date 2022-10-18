"""Top-level package for datman."""

from importlib.metadata import version, PackageNotFoundError
import logging

# If you remove this and dont manually import config before importing
# datman/dashboard.py you will get circular import errors. I am sooo sorry.
# We'd have to store hardcoded file paths in the dashboard database to
# otherwise fix this.
import datman.config

logging.getLogger('datman').setLevel(logging.WARN)

try:
    __version__ = version(__name__)
except PackageNotFoundError:
    # package is not installed
    pass
