"""Defines the exceptions used by datman sub-modules"""


class ParseException(Exception):
    """For participant ID parsing issues."""

    pass


class XnatException(Exception):
    """Default exception for XNAT errors"""

    study = None
    session = None

    def __repr__(self):
        return f"Study: {study} Session: {session} Error: {message}"


class DashboardException(Exception):
    """Default exception for dashboard errors"""

    pass


class MetadataException(Exception):
    pass


class ExportException(Exception):
    pass


class InputException(Exception):
    pass


class ConfigException(Exception):
    pass


class UndefinedSetting(Exception):
    pass
