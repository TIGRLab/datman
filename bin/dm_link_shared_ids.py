#!/usr/bin/env python
"""
Finds REDCap records for the given study and if a session has multiple IDs
(i.e. it is shared with another study) updates the dashboard and tries to
create links from the exported original data to its pseudonyms.

Usage:
    dm_link_shared_ids.py [options] <project>

Arguments:
    <project>           The name of a project defined in the site config file.

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

import datman.config
import datman.scanid
import datman.utils

import bin.dm_link_project_scans as link_scans
import datman.dashboard as dashboard
from datman.exceptions import InputException, UndefinedSetting

DRYRUN = False

logging.basicConfig(
    level=logging.WARN,
    format="[%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger(os.path.basename(__file__))


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

    if verbose:
        logger.setLevel(logging.INFO)
        link_scans.logger.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)
        link_scans.logger.setLevel(logging.DEBUG)
    if quiet:
        logger.setLevel(logging.ERROR)
        link_scans.logger.setLevel(logging.ERROR)

    config = datman.config.config(filename=site_config, study=project)

    scan_complete_records = get_redcap_records(config, redcap_cred)
    for record in scan_complete_records:
        if not record.shared_ids:
            continue
        make_links(record)


def get_redcap_records(config, redcap_cred):
    token = get_token(config, redcap_cred)
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
        id_map = config.get_key('ID_MAP')
    except UndefinedSetting:
        id_map = None

    try:
        project_records = parse_records(response, current_study, id_map)
    except ValueError as e:
        logger.error("Couldnt parse redcap records for server response {}. "
                     "Reason: {}".format(response.content, e))
        project_records = []

    return project_records


def get_token(config, redcap_cred):
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


def parse_records(response, study, id_map):
    records = []
    for item in response.json():
        record = Record(item, id_map)
        if record.id is None:
            logger.debug(
                f"Record with ID {item['record_id']} has malformed subject ID "
                f"{item['par_id']}"
            )
            continue
        if record.matches_study(study):
            records.append(record)
    return records


def make_links(record):
    source = record.id
    for target in record.shared_ids:
        logger.info(
            f"Making links from source {source} to target {target}"
        )
        target_cfg = datman.config.config(study=target)
        try:
            target_tags = list(target_cfg.get_tags(site=source.site))
        except Exception:
            target_tags = []

        target_tags = ",".join(target_tags)

        if DRYRUN:
            logger.info(
                "DRYRUN - would have made links from source ID "
                f"{source} to target ID {target} for tags {target_tags}"
            )
            continue

        link_scans.create_linked_session(str(source), str(target), target_tags)
        if dashboard.dash_found:
            share_redcap_record(target, record)


def share_redcap_record(session, shared_record):
    logger.debug(
        f"Sharing redcap record {shared_record.record_id} from participant "
        f"{shared_record.id} with ID {session}"
    )

    target_session = dashboard.get_session(session)
    if not target_session:
        logger.error(
            f"Can't link redcap record in dashboard. {session} not found"
        )
        return

    if target_session.redcap_record:
        logger.debug(
            f"Session {target_session} already has record "
            f"{target_session.redcap_record}"
        )
        return

    source_session = dashboard.get_session(shared_record.id)
    if not source_session.redcap_record:
        logger.debug("Redcap record has not been added to original session "
                     "yet, will re-attempt sharing later")
        return

    try:
        source_session.redcap_record.share_record(target_session)
    except Exception as e:
        logger.error(f"Failed to link redcap record. Reason: {e}")


class Record(object):
    def __init__(self, record_dict, id_map=None):
        self.record_id = record_dict['record_id']
        self.id = self.__get_datman_id(record_dict['par_id'], id_map)
        self.study = self.__get_study()
        self.comment = record_dict['cmts']
        self.shared_ids = self.__get_shared_ids(record_dict, id_map)

    def matches_study(self, study_tag):
        if study_tag == self.study:
            return True
        return False

    def __get_study(self):
        if self.id is None:
            return None
        return self.id.study

    def __get_shared_ids(self, record_dict, id_map):
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
            subject_id = self.__get_datman_id(value, id_map)
            if subject_id is None:
                # Badly named shared id value. Skip it.
                continue
            shared_ids.append(str(subject_id))
        return shared_ids

    def __get_datman_id(self, subid, id_map):
        try:
            subject_id = datman.scanid.parse(subid, id_map)
        except datman.scanid.ParseException:
            logger.error("REDCap record with record_id {} contains non-datman "
                         "ID {}.".format(self.record_id, subid))
            return None
        return subject_id

    def __repr__(self):
        return f"<Record {self.id}>"


if __name__ == '__main__':
    main()
