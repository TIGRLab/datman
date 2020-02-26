"""
Represents scan identifiers that conform to the TIGRLab naming scheme
"""
import os.path
import re
from abc import ABC


class ParseException(Exception):
    pass


class Identifier(ABC):

    def match(self, identifier):
        if not isinstance(identifier, str):
            raise ParseException("Must be given a string to verify ID matches")

        match = self.scan_pattern.match(identifier)
        if not match:
            match = self.pha_pattern.match(identifier)
        return match

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


class DatmanIdentifier(Identifier):
    scan_re = '(?P<id>(?P<study>[^_]+)_' \
              '(?P<site>[^_]+)_' \
              '(?!.+PHA)(?P<subject>[^_]+)_' \
              '(?P<timepoint>[^_]+)_' \
              '(?!MR)(?!SE)(?P<session>[^_]+))'

    pha_re = '(?P<id>(?P<study>[^_]+)_' \
             '(?P<site>[^_]+)_' \
             '(?P<subject>PHA_[^_]+)' \
             '(?P<timepoint>)(?P<session>))'  # empty tp + session

    scan_pattern = re.compile('^' + scan_re + '$')
    pha_pattern = re.compile('^' + pha_re + '$')

    def __init__(self, identifier, settings=None):
        match = self.match(identifier)

        if not match:
            # work around for matching scanids when session not supplied
            match = self.scan_pattern.match(identifier + '_XX')

        if not match:
            raise ParseException('Invalid Datman ID {}'.format(identifier))

        self.study = match.group('study')
        self.site = match.group('site')
        self.subject = match.group('subject')
        self.timepoint = match.group('timepoint')
        # Bug fix: spaces were being left after the session number leading to
        # broken file name
        self._session = match.group('session').strip()

    @property
    def session(self):
        if self._session == 'XX':
            return ''
        return self._session

    @session.setter
    def session(self, value):
        self._session = value

    def __repr__(self):
        return '<datman.scanid.DatmanIdentifier {}>'.format(self.__str__())


class KCNIIdentifier(Identifier):
    scan_re = '(?P<id>(?P<study>[A-Z]{3}[0-9]{2})_' \
              '(?P<site>[A-Z]{3})_' \
              '(?P<subject>[A-Z0-9]{4,8})_' \
              '(?P<timepoint>[0-9]{2})_' \
              'SE(?P<session>[0-9]{2})_MR)'

    pha_re = '(?P<id>(?P<study>[A-Z]{3}[0-9]{2})_' \
             '(?P<site>[A-Z]{3})_' \
             '(?P<pha_type>[A-Z]{3})PHA_' \
             '(?P<subject>[0-9]{4})_MR' \
             '(?P<timepoint>)(?P<session>))'  # empty

    scan_pattern = re.compile('^' + scan_re + '$')
    pha_pattern = re.compile('^' + pha_re + '$')

    def __init__(self, identifier, settings=None):
        match = self.match(identifier)
        if not match:
            raise ParseException("Invalid KCNI ID {}".format(identifier))

        # What about if a field has to be translated between conventions?
        self.study = match.group("study")
        self.site = match.group("site")

        self.subject = match.group("subject")
        try:
            self.pha_type = match.group("pha_type")
        except IndexError:
            # Not a phantom
            self.pha_type = None
        else:
            self.subject = "PHA_{}{}".format(self.pha_type, self.subject)

        self.timepoint = match.group("timepoint")
        self.session = match.group("session")

    def __repr__(self):
        return '<datman.scanid.KCNIIdentifier {}>'.format(self.__str__())


class BIDSFile(object):

    def __init__(self, subject, session, suffix, task=None, acq=None, ce=None,
                 dir=None, rec=None, run=None, echo=None, mod=None):
        self.subject = subject
        self.session = session
        if not run:
            run = '1'
        self.run = run
        self.suffix = suffix

        if echo or task:
            if any([ce, dir, mod]):
                raise ParseException("Invalid entity found for task data")
        if ce or mod:
            if any([task, echo, dir]):
                raise ParseException("Invalid entity found for anat data")
        if dir:
            if any([ce, rec, mod, task, echo]):
                raise ParseException("Invalid entity found for multiphase "
                                     "fmap")
        self.task = task
        self.acq = acq
        self.ce = ce
        self.dir = dir
        self.rec = rec
        self.echo = echo
        self.mod = mod

    def __eq__(self, bids_file):
        if not isinstance(bids_file, BIDSFile):
            try:
                bids_file = parse_bids_filename(bids_file)
            except ParseException:
                return False

        if str(self) == str(bids_file):
            return True

        return False

    def __str__(self):
        str_rep = ["sub-{}_ses-{}".format(self.subject, self.session)]
        if self.task:
            str_rep.append("task-{}".format(self.task))
        if self.acq:
            str_rep.append("acq-{}".format(self.acq))
        if self.ce:
            str_rep.append("ce-{}".format(self.ce))
        if self.dir:
            str_rep.append("dir-{}".format(self.dir))
        if self.rec:
            str_rep.append("rec-{}".format(self.rec))

        str_rep.append("run-{}".format(self.run))

        if self.echo:
            str_rep.append("echo-{}".format(self.echo))
        if self.mod:
            str_rep.append("mod-{}".format(self.mod))

        str_rep.append(self.suffix)
        return "_".join(str_rep)

    def __repr__(self):
        return "<datman.scanid.BIDSFile {}>".format(self.__str__())


FILENAME_RE = DatmanIdentifier.scan_re + '_' + \
              r'(?P<tag>[^_]+)_' + \
              r'(?P<series>\d+)_' + \
              r'(?P<description>.*?)' + \
              r'(?P<ext>.nii.gz|.nii|.json|.bvec|.bval|.tar.gz|.tar|.dcm|' + \
              r'.IMA|.mnc|.nrrd|$)'

FILENAME_PHA_RE = DatmanIdentifier.pha_re + '_' + \
              r'(?P<tag>[^_]+)_' + \
              r'(?P<series>\d+)_' + \
              r'(?P<description>.*?)' + \
              r'(?P<ext>.nii.gz|.nii|.json|.bvec|.bval|.tar.gz|.tar|.dcm|' + \
              r'.IMA|.mnc|.nrrd|$)'

BIDS_SCAN_RE = r'sub-(?P<subject>[A-Z0-9]+)_' + \
               r'ses-(?P<session>[A-Za-z0-9]+)_' + \
               r'(task-(?P<task>[A-Za-z0-9]+)_){0,1}' + \
               r'(acq-(?P<acq>[A-Za-z0-9]+)_){0,1}' + \
               r'(ce-(?P<ce>[A-Za-z0-9]+)_){0,1}' + \
               r'(dir-(?P<dir>[A-Za-z0-9]+)_){0,1}' + \
               r'(rec-(?P<rec>[A-Za-z0-9]+)_){0,1}' + \
               r'(run-(?P<run>[0-9]+)_){0,1}' + \
               r'(echo-(?P<echo>[0-9]+)_){0,1}' + \
               r'(mod-(?P<mod>[A-Za-z0-9]+)_){0,1}' + \
               r'((?![A-Za-z0-9]*-)(?P<suffix>[^_.]+))' + \
               r'.*$'

FILENAME_PATTERN = re.compile('^' + FILENAME_RE)
FILENAME_PHA_PATTERN = re.compile('^' + FILENAME_PHA_RE)
BIDS_SCAN_PATTERN = re.compile(BIDS_SCAN_RE)


def parse(identifier, settings=None):
    """Parse a subject ID matching a supported naming convention.

    Args:
        identifier (:obj:`str`): A string that might be a valid subject ID.
        settings (:obj:`dict`, optional): A dictionary of settings to use when
            parsing the ID. Defaults to None.

    Raises:
        ParseException: If identifier does not match any supported naming
            convention.

    Returns:
        :obj:`Identifer`: An instance of a subclass of Identifier for the
            matched naming convention.
    """
    try:
        return DatmanIdentifier(identifier)
    except ParseException:
        pass

    try:
        return KCNIIdentifier(identifier, settings=settings)
    except ParseException:
        pass

    raise ParseException("Invalid ID - {}".format(identifier))


def parse_filename(path):
    """Parse a datman style file name.

    Args:
        path (:obj:`str`): A file name or full path to parse

    Raises:
        ParseException: If the file name does not match the datman convention.

    Returns:
        tuple: A tuple containing:

            ident (:obj:`DatmanIdentifier`): The parsed subject ID portion of
                the path.
            tag (:obj:`str`): The scan tag that identifies the acquisition.
            series (int): The series number.
            description (:obj:`str`): The series description. Should be
                identical to the SeriesDescription field of the dicom headers
                (aside from some mangling to non-alphanumeric characters).
    """
    fname = os.path.basename(path)
    match = FILENAME_PHA_PATTERN.match(fname)  # check PHA first
    if not match:
        match = FILENAME_PATTERN.match(fname)
    if not match:
        raise ParseException()

    ident = DatmanIdentifier(match.group("id"))

    tag = match.group("tag")
    series = match.group("series")
    description = match.group("description")
    return ident, tag, series, description


def parse_bids_filename(path):
    fname = os.path.basename(path)
    match = BIDS_SCAN_PATTERN.match(fname)
    if not match:
        raise ParseException("Invalid BIDS file name {}".format(path))
    try:
        ident = BIDSFile(subject=match.group("subject"),
                         session=match.group("session"),
                         run=match.group("run"),
                         suffix=match.group("suffix"),
                         task=match.group("task"),
                         acq=match.group("acq"),
                         ce=match.group("ce"),
                         dir=match.group("dir"),
                         rec=match.group("rec"),
                         echo=match.group("echo"),
                         mod=match.group("mod"))
    except ParseException as e:
        raise ParseException("Invalid BIDS file name {} - {}".format(path, e))
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
