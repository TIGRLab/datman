"""
Manages name conventions and functions to ensure that IDs conform to them.

.. note::
    While multiple ID conventions are supported (Datman, KCNI, BIDS)
    the datman convention is the 'base'/default convention used. As a result
    all conventions get parsed into datman fields and return datman IDs when
    get_full_subjectid and other similar methods are called. The original ID
    in its native convention can always be retrieved from 'orig_id'.

"""
import os.path
import re
from abc import ABC, abstractmethod

from datman.exceptions import ParseException


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

    @abstractmethod
    def get_xnat_subject_id(self):
        pass

    @abstractmethod
    def get_xnat_experiment_id(self):
        pass

    def __str__(self):
        if self.session:
            return self.get_full_subjectid_with_timepoint_session()
        else:
            return self.get_full_subjectid_with_timepoint()


class DatmanIdentifier(Identifier):
    """
    Parses a datman-style ID into fields.

    The datman convention is detailed
    `here <https://github.com/TIGRLab/documentation/wiki/Data-Naming>`_

    """

    scan_re = (
        "(?P<id>(?P<study>[^_]+)_"
        "(?P<site>[^_]+)_"
        "(?P<subject>[^_]+)(?<!PHA)_"
        "(?P<timepoint>[^_]+)_"
        "(?!MR)(?!SE)(?P<session>[^_]+))"
    )

    pha_re = (
        "(?P<id>(?P<study>[^_]+)_"
        "(?P<site>[^_]+)_"
        "(?P<subject>PHA_(?P<type>[A-Z]{3})(?P<num>[0-9]{4,6}))"
        "(?P<timepoint>)(?P<session>))"
    )  # empty tp + session

    scan_pattern = re.compile("^" + scan_re + "$")
    pha_pattern = re.compile("^" + pha_re + "$")

    def __init__(self, identifier, settings=None):
        match = self.match(identifier)

        if not match:
            # work around for matching scanids when session not supplied
            match = self.scan_pattern.match(identifier + "_XX")

        if not match:
            raise ParseException(f"Invalid Datman ID {identifier}")

        self._match_groups = match
        self.orig_id = match.group("id")
        self.study = match.group("study")
        self.site = match.group("site")
        self.subject = match.group("subject")
        self.timepoint = match.group("timepoint")
        self.modality = 'MR'
        # Bug fix: spaces were being left after the session number leading to
        # broken file name
        self._session = match.group("session").strip()

    @property
    def session(self):
        if self._session == "XX":
            return ""
        return self._session

    @session.setter
    def session(self, value):
        self._session = value

    def get_xnat_subject_id(self):
        return self.get_full_subjectid_with_timepoint_session()

    def get_xnat_experiment_id(self):
        return self.get_xnat_subject_id()

    def __repr__(self):
        return f"<datman.scanid.DatmanIdentifier {self.__str__()}>"


class KCNIIdentifier(Identifier):
    """
    Parses a KCNI style ID into datman-style fields.

    The KCNI convention is detailed
    `here. <http://neurowiki.camh.ca/mediawiki/index.php/XNATNamingConvention>`_

    .. note: The original KCNI format ID is retrievable from orig_id.

    """  # noqa: E501

    scan_re = (
        "(?P<id>(?P<study>[A-Z]{3}[0-9]{2})_"
        "(?P<site>[A-Z]{3})_"
        "(?P<subject>[A-Z0-9]{4,8})_"
        "(?P<timepoint>[0-9]{2})_"
        "SE(?P<session>[0-9]{2})_(?P<modality>[A-Z]{2,4}))"
    )

    pha_re = (
        "(?P<id>(?P<study>[A-Z]{3}[0-9]{2})_"
        "(?P<site>[A-Z]{3})_"
        "(?P<pha_type>[A-Z]{3})PHA_"
        "(?P<subject>[0-9]{4,6})_(?P<modality>[A-Z]{2,4})"
        "(?P<timepoint>)(?P<session>))"
    )  # empty

    scan_pattern = re.compile("^" + scan_re + "$")
    pha_pattern = re.compile("^" + pha_re + "$")

    def __init__(self, identifier, settings=None):
        match = self.match(identifier)
        if not match:
            raise ParseException(f"Invalid KCNI ID {identifier}")

        self._match_groups = match
        self.orig_id = match.group("id")
        self.study = get_field(match, "study", settings=settings)
        self.site = get_field(match, "site", settings=settings)

        self.subject = get_subid(match.group("subject"), settings=settings)
        try:
            self.pha_type = match.group("pha_type")
        except IndexError:
            # Not a phantom
            self.pha_type = None
        else:
            self.subject = f"PHA_{self.pha_type}{self.subject}"

        self.timepoint = match.group("timepoint")
        self.session = match.group("session")
        self.modality = match.group("modality")

    def get_xnat_subject_id(self):
        study = self._match_groups.group("study")
        site = self._match_groups.group("site")
        subject = self._match_groups.group("subject")
        if self.pha_type:
            subject = self.pha_type + "PHA"
        else:
            subject = self._match_groups.group("subject")
        return "_".join([study, site, subject])

    def get_xnat_experiment_id(self):
        return self.orig_id

    def __repr__(self):
        return f"<datman.scanid.KCNIIdentifier {self.__str__()}>"


class BIDSFile(object):
    def __init__(
        self,
        subject,
        session,
        suffix,
        task=None,
        acq=None,
        ce=None,
        dir=None,
        rec=None,
        run=None,
        echo=None,
        mod=None,
    ):
        self.subject = subject
        self.session = session
        if not run:
            run = "1"
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
                raise ParseException("Invalid entity found for multiphase fmap")
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
        str_rep = [f"sub-{self.subject}_ses-{self.session}"]
        if self.task:
            str_rep.append(f"task-{self.task}")
        if self.acq:
            str_rep.append(f"acq-{self.acq}")
        if self.ce:
            str_rep.append(f"ce-{self.ce}")
        if self.dir:
            str_rep.append(f"dir-{self.dir}")
        if self.rec:
            str_rep.append(f"rec-{self.rec}")

        str_rep.append(f"run-{self.run}")

        if self.echo:
            str_rep.append(f"echo-{self.echo}")
        if self.mod:
            str_rep.append(f"mod-{self.mod}")

        str_rep.append(self.suffix)
        return "_".join(str_rep)

    def __repr__(self):
        return f"<datman.scanid.BIDSFile {self.__str__()}>"


FILENAME_RE = (
    DatmanIdentifier.scan_re
    + "_"
    + r"(?P<tag>[^_]+)_"
    + r"(?P<series>\d+)_"
    + r"(?P<description>.*?)"
    + r"(?P<ext>.nii.gz|.nii|.json|.bvec|.bval|.tar.gz|.tar|.dcm|"
    + r".IMA|.mnc|.nrrd|$)"
)

FILENAME_PHA_RE = (
    DatmanIdentifier.pha_re
    + "_"
    + r"(?P<tag>[^_]+)_"
    + r"(?P<series>\d+)_"
    + r"(?P<description>.*?)"
    + r"(?P<ext>.nii.gz|.nii|.json|.bvec|.bval|.tar.gz|.tar|.dcm|"
    + r".IMA|.mnc|.nrrd|$)"
)

BIDS_SCAN_RE = (
    r"sub-(?P<subject>[A-Z0-9]+)_"
    + r"ses-(?P<session>[A-Za-z0-9]+)_"
    + r"(task-(?P<task>[A-Za-z0-9]+)_){0,1}"
    + r"(acq-(?P<acq>[A-Za-z0-9]+)_){0,1}"
    + r"(ce-(?P<ce>[A-Za-z0-9]+)_){0,1}"
    + r"(dir-(?P<dir>[A-Za-z0-9]+)_){0,1}"
    + r"(rec-(?P<rec>[A-Za-z0-9]+)_){0,1}"
    + r"(run-(?P<run>[0-9]+)_){0,1}"
    + r"(echo-(?P<echo>[0-9]+)_){0,1}"
    + r"(mod-(?P<mod>[A-Za-z0-9]+)_){0,1}"
    + r"((?![A-Za-z0-9]*-)(?P<suffix>[^_.]+))"
    + r".*$"
)

FILENAME_PATTERN = re.compile("^" + FILENAME_RE)
FILENAME_PHA_PATTERN = re.compile("^" + FILENAME_PHA_RE)
BIDS_SCAN_PATTERN = re.compile(BIDS_SCAN_RE)


def parse(identifier, settings=None):
    """
    Parse a subject ID matching a supported naming convention.

    The 'settings' flag can be used to exclude any IDs that do not match the
    specified convention, or to translate certain ID fields to maintain
    consistency within a single naming convention.

    Accepted keys include:
        'ID_TYPE': Restricts parsing to one naming convention (e.g. 'DATMAN'
            or 'KCNI')
        'STUDY': Allows the 'study' field of an ID to be mapped from another
            convention's study code to a datman study code.
        'SITE': Allows the 'site' field of an ID to be translated from another
            convention's site code to a datman site code.

    .. note:: All 'settings' keys must be uppercase.

    Using the settings from the below example will cause parse to reject any
    IDs that are not KCNI format, will translate any valid IDs containing
    'DTI01' to the study code 'DTI', and will translate any valid IDs
    containing the site 'UTO' to the site 'UT1'.

    .. code-block:: python

        settings = {
            'ID_TYPE': 'KCNI',
            'STUDY': {
                'DTI01': 'DTI'
            },
            'SITE': {
                'UTO': 'UT2'
            }
        }

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
    if isinstance(identifier, Identifier):
        if not settings:
            return identifier
        # ID may need to be reparsed based on settings
        identifier = identifier.orig_id

    if settings and "ID_TYPE" in settings:
        id_type = settings["ID_TYPE"]
    else:
        id_type = "DETECT"

    if id_type in ("DATMAN", "DETECT"):
        try:
            return DatmanIdentifier(identifier)
        except ParseException:
            pass

    if id_type in ("KCNI", "DETECT"):
        try:
            return KCNIIdentifier(identifier, settings=settings)
        except ParseException:
            pass

    raise ParseException(f"Invalid ID - {identifier}")


def parse_filename(path):
    """
    Parse a datman style file name.

    Args:
        path (:obj:`str`): A file name or full path to parse

    Raises:
        ParseException: If the file name does not match the datman convention.

    Returns:
        (tuple): A tuple containing:

            * ident (:obj:`DatmanIdentifier`): The parsed subject ID portion of
                the path.
            * tag (:obj:`str`): The scan tag that identifies the acquisition.
            * series (int): The series number.
            * description (:obj:`str`): The series description. Should be
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
        raise ParseException(f"Invalid BIDS file name {path}")
    try:
        ident = BIDSFile(
            subject=match.group("subject"),
            session=match.group("session"),
            run=match.group("run"),
            suffix=match.group("suffix"),
            task=match.group("task"),
            acq=match.group("acq"),
            ce=match.group("ce"),
            dir=match.group("dir"),
            rec=match.group("rec"),
            echo=match.group("echo"),
            mod=match.group("mod"),
        )
    except ParseException as e:
        raise ParseException(f"Invalid BIDS file name {path} - {e}")
    return ident


def make_filename(ident, tag, series, description, ext=None):
    filename = "_".join([str(ident), tag, series, description])
    if ext:
        filename += ext
    return filename


def is_scanid(identifier):
    try:
        parse(identifier)
    except ParseException:
        return False
    return True


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
    return identifier.subject[0:3] == "PHA"


def get_session_num(ident):
    """
    For those times when you always want a numeric session (including
    for phantoms who are technically always session '1')

    """
    if ident.session:
        try:
            num = int(ident.session)
        except ValueError:
            raise ParseException(f"ID {ident} has non-numeric session number")
    elif is_phantom(ident):
        num = 1
    else:
        raise ParseException(f"ID {ident} is missing a session number")
    return num


def get_field(match, field, settings=None):
    """
    Find the value of an ID field, allowing for user specified changes.

    Args:
        match (:obj:`re.Match`): A match object created from a valid ID
        field (:obj:`str`): An ID field name. This corresponds to the match
            groups of valid (supported) ID (e.g. study, site, subject)
        settings (:obj:`dict`, optional): User settings to specify fields that
            should be modified and how to modify them. See the settings
            description in :py:func:`parse` for more info. Defaults to None.

    Returns:
        str: The value of the field based on the re.Match groups and user
            settings.

    """

    if not settings or field.upper() not in settings:
        return match.group(field.lower())

    mapping = settings[field.upper()]
    current_field = match.group(field.lower())
    try:
        new_field = mapping[current_field]
    except KeyError:
        new_field = current_field

    return new_field


def get_subid(current_subid, settings=None):
    if not settings or "SUBJECT" not in settings:
        return current_subid

    mapping = settings["SUBJECT"]

    for pair in mapping:
        regex_str, replacement = pair.split("->")
        regex = re.compile(regex_str)
        match = regex.match(current_subid)
        if match:
            return re.sub(regex_str, replacement, current_subid)

    return current_subid


def get_kcni_identifier(identifier, settings=None):
    """
    Get a KCNIIdentifier from a valid string or an identifier.

    Args:
        identifier (:obj:`string`): A string matching a supported naming
            convention.
        settings (:obj:`dict`, optional): A settings dictionary matching the
            format described in :py:func:`parse`. Defaults to None.

    Raises:
        ParseException: When an ID that doesnt match any supported convention
            is given or when a valid ID can't be converted to KCNI format.

    Returns:
        KCNIIdentifier: An instance of a KCNI identifier with any field
            mappings applied.

    """
    if isinstance(identifier, KCNIIdentifier):
        return identifier

    try:
        return KCNIIdentifier(identifier, settings)
    except ParseException:
        pass

    if isinstance(identifier, DatmanIdentifier):
        ident = identifier
    else:
        ident = DatmanIdentifier(identifier)

    if settings:
        # Flip settings from KCNI -> datman to datman -> KCNI to ensure the
        # KCNI convention is used in KCNIIdentifer.orig_id
        reverse = {}
        for entry in settings:
            if entry == "ID_TYPE" or not isinstance(settings[entry], dict):
                reverse[entry] = settings[entry]
                continue
            reverse[entry] = {val: key for key, val in settings[entry].items()}
    else:
        reverse = None

    study = get_field(ident._match_groups, "study", reverse)
    site = get_field(ident._match_groups, "site", reverse)
    subject = get_subid(ident._match_groups.group("subject"), reverse)

    if not is_phantom(ident):
        kcni = (
            f"{study}_{site}_{subject.zfill(4)}_"
            f"{ident.timepoint}_SE{ident.session}_MR"
        )
        return KCNIIdentifier(kcni, settings)

    try:
        pha_type = ident._match_groups.group("type")
        num = ident._match_groups.group("num")
    except IndexError:
        raise ParseException(f"Can't parse datman phantom {ident} to KCNI ID")
    subject = f"{pha_type}PHA_{num}"

    return KCNIIdentifier(f"{study}_{site}_{subject}_MR", settings)
