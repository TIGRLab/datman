"""Defines the exceptions used by datman sub-modules"""


class ParseException(Exception):
    """For participant ID parsing issues.
    """
    pass


class XnatException(Exception):
    """Default exception for xnat errors"""
    study = None
    session = None

    def __repr__(self):
        if len(self.args) > 0:
            message = self.args[0]
        else:
            message = "No message given"
        return 'Study:{} Session:{} Error:{}'.format(self.study,
                                                     self.session,
                                                     message)


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
