"""Defines the exceptions used by datman sub-modules"""


class ParseException(Exception):
<<<<<<< HEAD
    """For participant ID parsing issues.
    """

=======
    """For participant ID parsing issues."""
>>>>>>> 1dd4b64a0b4f414b8070cf5a8cb1bf00aea77ecc
    pass


class XnatException(Exception):
<<<<<<< HEAD
    """Default exception for xnat errors"""

=======
    """Default exception for XNAT errors"""
>>>>>>> 1dd4b64a0b4f414b8070cf5a8cb1bf00aea77ecc
    study = None
    session = None

    def __repr__(self):
        return "Study:{} Session:{} Error:{}".format(
            self.study, self.session, self.message
        )


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
