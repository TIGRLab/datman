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
        return 'Study:{} Session:{} Error:{}'.format(self.study,
                                                     self.session,
                                                     self.message)


class DashboardException(Exception):
    """Default exception for dashboard errors"""
    pass


class MetadataException(Exception):
    pass


class ExportException(Exception):
    pass


class InputException(Exception):
    pass
