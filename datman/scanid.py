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

SCANID_PHA_RE = '(?P<study>[^_]+)_' \
                '(?P<site>[^_]+)_' \
                '(?P<subject>PHA_[^_]+)' \
                '(?P<timepoint>)(?P<session>)'  # empty

FILENAME_RE = SCANID_RE + '_' + \
              r'(?P<tag>[^_]+)_' + \
              r'(?P<series>\d+)_' + \
              r'(?P<description>.*?)' + \
              r'(?P<ext>.nii.gz|.nii|.json|.bvec|.bval|.tar.gz|.tar|.dcm|' + \
              r'.IMA|.mnc|.nrrd|$)'

FILENAME_PHA_RE = SCANID_PHA_RE + '_' + \
              r'(?P<tag>[^_]+)_' + \
              r'(?P<series>\d+)_' + \
              r'(?P<description>.*?)' + \
              r'(?P<ext>.nii.gz|.nii|.json|.bvec|.bval|.tar.gz|.tar|.dcm|' + \
              r'.IMA|.mnc|.nrrd|$)'

BIDS_SCAN_RE = r'sub-(?P<subject>[A-Z0-9]+)_' + \
               r'ses-(?P<session>[0-9][0-9])_' + \
               r'(run-(?P<run>[0-9])_){0,1}' + \
               r'(?P<suffix>(?!run-)[^_.]+)' + \
               r'.*$'

SCANID_PATTERN = re.compile('^' + SCANID_RE+'$')
SCANID_PHA_PATTERN = re.compile('^' + SCANID_PHA_RE+'$')
FILENAME_PATTERN = re.compile('^' + FILENAME_RE)
FILENAME_PHA_PATTERN = re.compile('^' + FILENAME_PHA_RE)
BIDS_SCAN_PATTERN = re.compile(BIDS_SCAN_RE)

# python 2 - 3 compatibility hack
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
        # Bug fix: spaces were being left after the session number leading to
        # broken file names
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
        return self.site + self.subject

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


class BIDSFile(object):

    def __init__(self, subject, session, suffix, run=None):
        self.subject = subject
        self.session = session
        if not run:
            run = '1'
        self.run = run
        self.suffix = suffix

    def __eq__(self, bids_file):
        if not isinstance(bids_file, BIDSFile):
            try:
                bids_file = parse_bids_filename(bids_file)
            except ParseException:
                return False

        if (self.subject == bids_file.subject and
                self.session == bids_file.session and
                str(self.run) == str(bids_file.run) and
                self.suffix == bids_file.suffix):
            return True

        return False

    def __str__(self):
        return "sub-{}_ses-{}_run-{}_{}".format(self.subject, self.session,
                                                self.run, self.suffix)

    def __repr__(self):
        return "<datman.scanid.BIDSFile {}>".format(self.__str__())


def parse(identifier):
    if not isinstance(identifier, basestring):
        raise ParseException

    match = SCANID_PATTERN.match(identifier)
    if not match:
        match = SCANID_PHA_PATTERN.match(identifier)
    # work around for matching scanid's when session not supplied
    if not match:
        match = SCANID_PATTERN.match(identifier + '_XX')
    if not match:
        raise ParseException("Invalid ID {}".format(identifier))

    ident = Identifier(study=match.group("study"),
                       site=match.group("site"),
                       subject=match.group("subject"),
                       timepoint=match.group("timepoint"),
                       session=match.group("session"))

    return ident


def parse_filename(path):
    fname = os.path.basename(path)
    match = FILENAME_PHA_PATTERN.match(fname)  # check PHA first
    if not match:
        match = FILENAME_PATTERN.match(fname)
    if not match:
        raise ParseException()

    ident = Identifier(study=match.group("study"),
                       site=match.group("site"),
                       subject=match.group("subject"),
                       timepoint=match.group("timepoint"),
                       session=match.group("session"))

    tag = match.group("tag")
    series = match.group("series")
    description = match.group("description")
    return ident, tag, series, description


def parse_bids_filename(path):
    fname = os.path.basename(path)
    match = BIDS_SCAN_PATTERN.match(fname)
    if not match:
        raise ParseException("Invalid BIDS file name {}".format(path))
    ident = BIDSFile(subject=match.group("subject"),
                     session=match.group("session"),
                     run=match.group("run"),
                     suffix=match.group("suffix"))
    return ident


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


def get_session_num(ident):
    """
    For those times when you always want a numeric session (including
    for phantoms who are technically always session '1')
    """
    if ident.session:
        try:
            num = int(ident.session)
        except ValueError:
            raise ParseException("ID {} has non-numeric session number".format(
                    ident))
    elif is_phantom(ident):
        num = 1
    else:
        raise ParseException("ID {} is missing a session number".format(ident))
    return num
