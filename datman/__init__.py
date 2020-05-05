"""Top-level package for datman."""

# If you remove this and dont manually import config before importing
# datman/dashboard.py you will get circular import errors. I am sooo sorry.
# We'd have to store hardcoded file paths in the dashboard database to
# otherwise fix this.
import datman.config

from .__about__ import __copyright__, __credits__, __packagename__, __version__

__all__ = [
    "__version__",
    "__copyright__",
    "__credits__",
    "__packagename__",
]
