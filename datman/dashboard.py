from __future__ import absolute_import
from functools import wraps
import os
import logging
from datetime import datetime

import datman.scanid
from datman.exceptions import DashboardException

logger = logging.getLogger(__name__)

try:
    from dashboard import queries, monitors
except ImportError:
    dash_found = False
    logger.error("Dashboard not found, proceeding without it.")
else:
    dash_found = True



def dashboard_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not dash_found:
            logger.warning("Dashboard not installed or configured correctly, "
                    "ignoring functionality.")
            if 'create' in kwargs.keys() or f.__name__.startswith('add'):
                raise DashboardException("Can't add record. Dashboard not "
                        "installed or configured")
            return None
        return f(*args, **kwargs)
    return decorated_function


def scanid_required(f):
    """
    This decorator checks that the wrapped function's first argument is an
    instance of datman.scanid.Identifier and attempts to convert it if not.

    A DashboardException will be raised if an Identifier isn't found or can't
    be created
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        name = args[0]
        if not isinstance(name, datman.scanid.Identifier):
            try:
                name = datman.scanid.parse(name)
            except datman.scanid.ParseException:
                raise DashboardException("Expected: a valid subject ID or "
                        "an instance of datman.scanid.Identifier. Received: "
                        "{}".format(name))
            args = list(args)
            args[0] = name
        return f(*args, **kwargs)
    return decorated_function


def filename_required(f):
    """
    This decorator checks that the wrapped function has received a datman
    style file name as either a string or as a datman.scanid.Identifier instance
    with kwargs tag, series, and description set.

    A DashboardException will be raised if the expected information is not given
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        name = args[0]
        if not isinstance(name, datman.scanid.Identifier):
            try:
                name, tag, series, descr = datman.scanid.parse_filename(name)
            except:
                try:
                    name = datman.scanid.parse(name)
                except:
                    raise datman.scanid.ParseException("A datman file name was "
                            "expected. Received {} instead.".format(name))
                try:
                    tag = kwargs['tag']
                    series = kwargs['series']
                    descr = kwargs['description']
                except:
                    raise DashboardException("An expected keyword argument "
                            "wasnt found. Please ensure either 'tag', "
                            "'series', and 'description' are set, or a "
                            "datman filename is given as an argument.")
            args = list(args)
            args[0] = name
            kwargs['tag'] = tag
            kwargs['series'] = series
            kwargs['description'] = descr
        elif ('tag' not in kwargs or
                'series' not in kwargs or
                'description' not in kwargs):
            raise DashboardException("An expected option was unset. This "
                    "function requires either a datman ident + 'tag', 'series' "
                    "and 'description' options be set or that a full filename "
                    "is given as a string")
        return f(*args, **kwargs)
    return decorated_function

@dashboard_required
def set_study_status(name, is_open):
    studies = queries.get_study(name=name)
    if not studies:
        raise DashboardException("ID {} contains invalid study / site "
                "combination".format(name))
    if len(studies) > 1:
        raise DashboardException("Can't identify study for {}. {} matching "
                "records found for the given study name".format(name,
                len(studies)))
    study = studies[0]
    study.is_open = is_open
    study.save()


@dashboard_required
@scanid_required
def get_subject(name, create=False):
    found = queries.find_subjects(name.get_full_subjectid_with_timepoint())
    if len(found) > 1:
        raise DashboardException("Couldnt identify record for {}. {} matching "
            "records found".format(name, len(found)))
    if len(found) == 1:
        return found[0]

    if create:
        return add_subject(name)

    return None


@dashboard_required
@scanid_required
def add_subject(name):
    studies = queries.get_study(tag=name.study, site=name.site)
    if not studies:
        raise DashboardException("ID {} contains invalid study / site "
                "combination".format(name))
    if len(studies) > 1:
        raise DashboardException("Can't identify study for {}. {} matching "
                "records found for that study / site combination".format(name,
                len(studies)))
    study = studies[0].study

    return study.add_timepoint(name)


@dashboard_required
@scanid_required
def get_session(name, create=False, date=None):
    try:
        sess_num = datman.scanid.get_session_num(name)
    except datman.scanid.ParseException:
        logger.info("{} is missing a session number. Using default session "
                "'1'".format(name))
        sess_num = 1

    session = queries.get_session(name.get_full_subjectid_with_timepoint(),
            sess_num)

    if not session and create:
        session = add_session(name, date=date)

    return session


@dashboard_required
@scanid_required
def add_session(name, date=None):
    timepoint = get_subject(name, create=True)

    try:
        sess_num = datman.scanid.get_session_num(name)
    except datman.scanid.ParseException:
        logger.info("{} is missing a session number. Using default session "
                "'1'".format(name))
        sess_num = 1

    if timepoint.is_phantom and sess_num > 1:
        raise DashboardException("ERROR: attempt to add repeat scan session to "
                "phantom {}".format(str(name)))

    if date:
        try:
            date = datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            logger.error("Cannot create session: Invalid date format {}."
                    "".format(date))
            raise DashboardException("Invalid date format {}".format(date))

    new_session = timepoint.add_session(sess_num, date=date)

    if timepoint.expects_redcap():
        try:
            monitors.monitor_redcap_import(str(timepoint), sess_num)
        except monitors.MonitorException as e:
            logger.error("Could not add scheduled check for redcap scan "
                    "completed survey for {}. Reason: {}".format(str(timepoint),
                    str(e)))

    return new_session


@dashboard_required
@filename_required
def get_scan(name, tag=None, series=None, description=None, source_id=None,
        create=False):
    scan_name = _get_scan_name(name, tag, series)

    scan = queries.get_scan(scan_name,
            timepoint=name.get_full_subjectid_with_timepoint(),
            session=name.session)

    if len(scan) > 1:
        raise DashboardException("Couldnt identify scan {}. {} matches "
                "found".format(scan_name, len(scan)))
    if len(scan) == 1:
        return scan[0]

    if create:
        return add_scan(name, tag=tag, series=series, description=description,
                source_id=source_id)

    return None


@dashboard_required
@filename_required
def add_scan(name, tag=None, series=None, description=None, source_id=None):
    session = get_session(name, create=True)
    studies = queries.get_study(tag=name.study, site=name.site)
    scan_name = _get_scan_name(name, tag, series)

    if len(studies) != 1:
        raise DashboardException("Can't identify study to add scan {} to. {} "
                "matches found.".format(scan_name, len(studies)))
    study = studies[0].study
    allowed_tags = [st.tag for st in study.scantypes]

    if tag not in allowed_tags:
        raise DashboardException("Scan name {} contains tag not configured "
                "for study {}".format(scan_name, str(study)))

    return session.add_scan(scan_name, series, tag, description,
            source_id=source_id)


@dashboard_required
def get_project(name=None, tag=None, site=None):
    """
    Return a study from the dashboard database that either matches the
    study name (e.g. 'SPINS') or matches a study tag (e.g. 'SPN01') + an
    optional site code to help locate the correct study when the same code
    is reused for multiple sites or studies.
    """
    if not (name or tag):
        raise DashboardException("Can't locate a study without the study "
                "nickname or a study tag")
    studies = queries.get_study(name=name, tag=tag, site=site)
    search_term = name or tag
    if len(studies) == 0:
        raise DashboardException("Failed to locate study matching {}".format(
                search_term))
    if len(studies) > 1:
        raise DashboardException("{} does not uniquely identify "
                "a project".format(search_term))
    if not name:
        return studies[0].study
    return studies[0]


@dashboard_required
def get_default_user():
    try:
        user = os.environ['DASHBOARD_USER']
    except KeyError:
        raise DashboardException("Can't retrieve default dashboard user ID. "
                "DASHBOARD_USER environment variable not set.")
    user = queries.get_user(user)
    if not user or len(user) > 1:
        raise DashboardException("Can't locate default user {} in "
                "dashboard database".format(user))
    return user[0]

# @dashboard_required
# def get_scantype(scantype):
#     if not dash_found:
#         return None
    # 1. Just query the database for the tag and return?

# @dashboard_required
# def delete_subject(name):
    # 1. Retrieve from database
    # 2. Delete, report if attempting to delete non-existent?
    # 3. Return True if delete, false otherwise

# @dashboard_required
# def add_redcap():
    # 1. Makes a redcap record

def _get_scan_name(ident, tag, series):
    name = "_".join([str(ident), tag, str(series)])
    return name
