#!/usr/bin/env python
"""
Finds REDCap records for the given study and if a scan has multiple IDs (i.e.
it is shared with another study) updates xnat to reflect this information and
tries to create a links from the exported original data to its pseudonyms. If
the original data set has been signed off on or has blacklist entries this
information will be shared with the newly linked ID.

The XNAT and REDCap URLs are read from the site config file (shell variable
'DM_CONFIG' by default).

Usage:
    dm_link_shared_ids.py [options] <project>

Arguments:
    <project>           The name of a project defined in the site config file
                        that may have multiple IDs for some of its subjects.

Options:
    --redcap FILE       A path to a text file containing a redcap token to
                        access 'Scan completed' surveys. If not set the
                        environment variable 'REDCAP_TOKEN' will be used

    --site-config FILE  The path to a site configuration file. If not set,
                        the default defined for datman.config.config() is used.

    -v, --verbose
    -d, --debug
    -q, --quiet
    --dry-run
"""
import os
import sys
import logging

from docopt import docopt
import requests
import pyxnat as xnat

import datman.config
import datman.scanid
import datman.utils

import bin.dm_link_project_scans as link_scans
import datman.dashboard as dashboard
from datman.exceptions import InputException

DRYRUN = False

# use of stream handler over basic config allows log format to change to more
# descriptive format later if needed while also ensure a consistent default
logger = logging.getLogger(os.path.basename(__file__))
log_handler = logging.StreamHandler()
logger.addHandler(log_handler)
log_handler.setFormatter(logging.Formatter('[%(name)s] %(levelname)s : '
                                           '%(message)s'))


def main():
    global DRYRUN
    arguments = docopt(__doc__)
    project = arguments['<project>']
    redcap_cred = arguments['--redcap']
    site_config = arguments['--site-config']
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    quiet = arguments['--quiet']
    DRYRUN = arguments['--dry-run']

    # Set log format
    log_handler.setFormatter(logging.Formatter('[%(name)s] %(levelname)s - '
                                               '{study}: %(message)s'
                                               ''.format(study=project)))
    log_level = logging.WARN

    if verbose:
        log_level = logging.INFO
    if debug:
        log_level = logging.DEBUG
    if quiet:
        log_level = logging.ERROR

    logger.setLevel(log_level)
    # Needed to see log messages from dm_link_project_scans
    link_scans.logger.setLevel(log_level)

    config = datman.config.config(filename=site_config, study=project)

    user_name, password = os.environ["XNAT_USER"], os.environ["XNAT_PASS"]
    xnat_url = get_xnat_url(config)

    scan_complete_records = get_project_redcap_records(config, redcap_cred)

    with datman.utils.XNATConnection(xnat_url, user_name,
                                     password) as connection:
        for record in scan_complete_records:
            link_shared_ids(config, connection, record)


def get_xnat_url(config):
    url = config.get_key('XNATSERVER')
    if 'https' not in url:
        url = "https://" + url
    return url


def get_project_redcap_records(config, redcap_cred):
    token = get_redcap_token(config, redcap_cred)
    redcap_url = config.get_key('REDCAPAPI')

    logger.debug("Accessing REDCap API at {}".format(redcap_url))

    payload = {'token': token,
               'format': 'json',
               'content': 'record',
               'type': 'flat'}

    response = requests.post(redcap_url, data=payload)
    if response.status_code != 200:
        logger.error("Cannot access redcap data at URL {}".format(redcap_url))
        sys.exit(1)

    current_study = config.get_key('STUDY_TAG')

    try:
        project_records = parse_records(response, current_study)
    except ValueError as e:
        logger.error("Couldnt parse redcap records for server response {}. "
                     "Reason: {}".format(response.content, e))
        project_records = []

    return project_records


def get_redcap_token(config, redcap_cred):
    if not redcap_cred:
        token = os.getenv('REDCAP_TOKEN')
        if not token:
            raise InputException("Redcap token not provided. Set the shell "
                                 "variable 'REDCAP_TOKEN' or provide a file")
        return token

    try:
        token = datman.utils.read_credentials(redcap_cred)[0]
    except IndexError:
        logger.error("REDCap credential file {} is empty.".format(redcap_cred))
        sys.exit(1)
    return token


def parse_records(response, study):
    records = []
    for item in response.json():
        record = Record(item)
        if record.id is None:
            continue
        if record.matches_study(study):
            records.append(record)
    return records


def link_shared_ids(config, connection, record):
    try:
        xnat_archive = config.get_key('XNAT_Archive', site=record.id.site)
    except datman.config.UndefinedSetting:
        logger.error("Can't find XNAT_Archive for subject {}"
                     "".format(record.id))
        return
    project = connection.select.project(xnat_archive)
    subject = project.subject(str(record.id))
    experiment = get_experiment(subject)

    if not experiment:
        logger.error("Redcap or XNAT record may be misnamed - no "
                     "matching experiments found on XNAT for redcap subject "
                     "{}. Skipping".format(record.id))
        return

    logger.debug("Working on subject {} in project {}".format(record.id,
                                                              xnat_archive))

    if record.comment and not DRYRUN:
        update_xnat_comment(experiment, subject, record)

    if record.shared_ids and not DRYRUN:
        update_xnat_shared_ids(subject, record)
        make_links(record)


def get_experiment(subject):
    experiment_names = subject.experiments().get()

    if not experiment_names:
        logger.debug("{} does not have any MR scans".format(subject))
        return None
    elif len(experiment_names) > 1:
        logger.error("{} has more than one MR scan. Updating only the "
                     "first".format(subject))

    return subject.experiment(experiment_names[0])


def update_xnat_comment(experiment, subject, record):
    logger.debug("Subject {} has comment: \n {}".format(record.id,
                                                        record.comment))
    try:
        experiment.attrs.set("note", record.comment)
        subject.attrs.set(
            "xnat:subjectData/fields/field[name='comments']/field",
            "See MR Scan notes")
    except xnat.core.errors.DatabaseError:
        logger.error(
            "Cannot write record {} comment to xnat. Adding note to "
            "check redcap record instead".format(record.id))
        subject.attrs.set(
            "xnat:subjectData/fields/field[name='comments']/field",
            "Refer to REDCap record.")


def update_xnat_shared_ids(subject, record):
    logger.debug("{} has alternate id(s) {}".format(record.id,
                                                    record.shared_ids))
    try:
        subject.attrs.set(
            "xnat:subjectData/fields/field[name='sharedids']/field",
            ", ".join(record.shared_ids))
    except xnat.core.errors.DatabaseError:
        logger.error(
            "{} shared ids cannot be added to XNAT. Adding note "
            "to check REDCap record instead.".format(record.id))
        subject.attrs.set(
            "xnat:subjectData/fields/field[name='sharedids']/field",
            "Refer to REDCap record.")


def make_links(record):
    source = record.id
    for target in record.shared_ids:
        logger.info("Making links from source {} to target {}".format(source,
                                                                      target))
        target_cfg = datman.config.config(study=target)
        try:
            target_tags = list(target_cfg.get_tags(site=record.id.site))
        except Exception:
            target_tags = []

        target_tags = ",".join(target_tags)

        link_scans.create_linked_session(str(source), str(target), target_tags)
        if dashboard.dash_found:
            share_redcap_record(target, record)


def share_redcap_record(session, shared_record):
    logger.debug("Sharing redcap record {} from participant {} with ID "
                 "{}".format(shared_record.record_id,
                             shared_record.id,
                             session))

    target_session = dashboard.get_session(session)
    if not target_session:
        logger.error("Can't link redcap record in dashboard. Participant {} "
                     "not found".format(session))
        return

    if target_session.redcap_record:
        logger.debug("Session {} already has record {}".format(
                            target_session,
                            target_session.redcap_record))
        return

    source_session = dashboard.get_session(shared_record.id)
    if not source_session.redcap_record:
        logger.debug("Redcap record has not been added to original session "
                     "yet, will re-attempt sharing later")
        return

    try:
        source_session.redcap_record.share_record(target_session)
    except Exception as e:
        logger.error("Failed to link redcap record. Reason: {}".format(e))


class Record(object):
    def __init__(self, record_dict):
        self.record_id = record_dict['record_id']
        self.id = self.__get_datman_id(record_dict['par_id'])
        self.study = self.__get_study()
        self.comment = record_dict['cmts']
        self.shared_ids = self.__get_shared_ids(record_dict)

    def matches_study(self, study_tag):
        if study_tag == self.study:
            return True
        return False

    def __get_study(self):
        if self.id is None:
            return None
        return self.id.study

    def __get_shared_ids(self, record_dict):
        keys = list(record_dict)
        shared_id_fields = []
        for key in keys:
            if 'shared_parid' in key:
                shared_id_fields.append(key)

        shared_ids = []
        for key in shared_id_fields:
            value = record_dict[key].strip()
            if not value:
                # No shared id for this field.
                continue
            subject_id = self.__get_datman_id(value)
            if subject_id is None:
                # Badly named shared id value. Skip it.
                continue
            shared_ids.append(value)
        return shared_ids

    def __get_datman_id(self, subid):
        try:
            subject_id = datman.scanid.parse(subid)
        except datman.scanid.ParseException:
            logger.error("REDCap record with record_id {} contains non-datman "
                         "ID {}.".format(self.record_id, subid))
            return None
        return subject_id


if __name__ == '__main__':
    main()
