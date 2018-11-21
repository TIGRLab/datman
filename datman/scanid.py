"""
Represents scan identifiers that conform to the TIGRLab naming scheme
"""
import os.path
import re

SCANID_RE = '(?P<study>[^_]+)_' \
            '(?P<site>[^_]+)_' \
            '(?P<subject>[^_]+)_' \
            '(?P<timepoint>[^_]+)_' \
            '(?P<session>[^_]+)'

# SCANID_RE = '(?P<study>[^_]+)_' \
#             '(?P<site>[^_]+)_' \
#             '(?P<subject>[^_]+)_' \
#             '(?P<timepoint>[^_]+)(_*)' \
#             '(?P<session>[^_]*)'

# SCANID_RE = '(?P<study>[^_]+)_' \
#             '(?P<site>[^_]+)_' \
#             '(?P<subject>[^_]+)_' \
#             '(?P<timepoint>[^_]+)(_?)' \
#             '(?P<session>[^_].*)'

SCANID_PHA_RE = '(?P<study>[^_]+)_' \
                '(?P<site>[^_]+)_' \
                '(?P<subject>PHA_[^_]+)' \
                '(?P<timepoint>)(?P<session>)'  # empty

FILENAME_RE = SCANID_RE + '_' + \
              r'(?P<tag>[^_]+)_' + \
              r'(?P<series>\d+)_' + \
              r'(?P<description>[^\.]*)' + \
              r'(?P<ext>\..*)?'

FILENAME_PHA_RE = SCANID_PHA_RE + '_' + \
              r'(?P<tag>[^_]+)_' + \
              r'(?P<series>\d+)_' + \
              r'(?P<description>[^\.]*)' + \
              r'(?P<ext>\..*)?'

SCANID_PATTERN       = re.compile('^'+SCANID_RE+'$')
SCANID_PHA_PATTERN   = re.compile('^'+SCANID_PHA_RE+'$')
FILENAME_PATTERN     = re.compile('^'+FILENAME_RE+'$')
FILENAME_PHA_PATTERN = re.compile('^'+FILENAME_PHA_RE+'$')

#python 2 - 3 compatibility hack
try:
    basestring
except NameError:
    basestring = str

class ParseException(Exception):
    pass

class Identifier:
    def __init__(self, study, site, subject, timepoint, session):
        self.study = study
        self.site = site
        self.subject = subject
        self.timepoint = timepoint
        # Bug fix: spaces were being left after the session number leading to broken file names
        self._session = session.strip()

    @property
    def session(self):
        if self._session == 'XX':
            return ''
        return self._session

    @session.setter
    def session(self, value):
        self._x = value


    def get_full_subjectid(self):
        return "_".join([self.study, self.site, self.subject])

    def get_bids_name(self):

        return 'sub-' + self.site + self.subject

    def get_full_subjectid_with_timepoint(self):
        ident = self.get_full_subjectid()
        if self.timepoint:
            ident += "_" + self.timepoint
        return ident

    def get_full_subjectid_with_timepoint_session(self):
        ident = self.get_full_subjectid_with_timepoint()
        if self.session:
            ident += "_" + self.session
        return ident

    def __str__(self):
        if self.session:
            return self.get_full_subjectid_with_timepoint_session()
        else:
            return self.get_full_subjectid_with_timepoint()


def parse(identifier):
    if not isinstance(identifier, basestring):
        raise ParseException

    match = SCANID_PATTERN.match(identifier)
    if not match: match = SCANID_PHA_PATTERN.match(identifier)
    # work around for matching scanid's when session not supplied
    if not match: match = SCANID_PATTERN.match(identifier + '_XX')
    if not match: raise ParseException()

    ident = Identifier(study    = match.group("study"),
                       site     = match.group("site"),
                       subject  = match.group("subject"),
                       timepoint= match.group("timepoint"),
                       session  = match.group("session"))

    return ident

def parse_filename(path):
    fname = os.path.basename(path)
    match = FILENAME_PHA_PATTERN.match(fname)  # check PHA first
    if not match: match = FILENAME_PATTERN.match(fname)
    if not match: raise ParseException()

    ident = Identifier(study    = match.group("study"),
                       site     = match.group("site"),
                       subject  = match.group("subject"),
                       timepoint= match.group("timepoint"),
                       session  = match.group("session"))

    tag = match.group("tag")
    series = match.group("series")
    description = match.group("description")
    return ident, tag, series, description

def make_filename(ident, tag, series, description, ext=None):
    filename = "_".join([str(ident), tag, series, description])
    if ext:
        filename += ext
    return filename

def is_scanid(identifier):
    try:
        parse(identifier)
        return True
    except ParseException:
        return False

def is_scanid_with_session(identifier):
    try:
        i = parse(identifier)
        if i.session:
            return True
    except ParseException:
        pass
    return False

def is_phantom(identifier):
    if not isinstance(identifier, Identifier):
        try:
            identifier = parse(identifier)
        except ParseException:
            return False
    return identifier.subject[0:3] == 'PHA'
