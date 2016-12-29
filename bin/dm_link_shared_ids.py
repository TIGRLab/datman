#!/usr/bin/env python
"""
Finds REDCap records for the given study and if a scan has multiple IDs (i.e. it
is shared with another study) updates xnat to reflect this information and
tries to create a links from the exported original data to its pseudonyms. If
the original data set has been signed off on or has blacklist entries this
information will be shared with the newly linked ID.

The XNAT and REDCap URLs are read from the site config file (shell variable
'DM_CONFIG' by default).

Usage:
    dm_link_shared_ids.py [options] <project>

Options:
    --xnat FILE         The path to a text file containing the xnat credentials.
                        If not set the 'xnat-credentials' file in the project
                        metadata folder will be used.
    --redcap FILE       The path to a text file containing a redcap token to
                        access 'Scan completed' surveys. If not set the
                        'redcap-token' file in the project metadata folder will
                        be used.
    --site-config FILE  The path to a site configuration file. If not set, the
                        default defined for datman.config.config() is used.
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

import datman
import datman.config, datman.scanid, datman.utils

DRYRUN = False

logging.basicConfig(level=logging.WARN,
        format='[%(name)s] %(levelname)s : %(message)s',
        disable_existing_loggers=False)
logger = logging.getLogger(os.path.basename(__file__))

def main():
    global DRYRUN
    arguments = docopt(__doc__)
    project = arguments['<project>']
    xnat_cred = arguments['--xnat']
    redcap_cred = arguments['--redcap']
    site_config = arguments['--site-config']
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    quiet = arguments['--quiet']
    DRYRUN = arguments['--dry-run']

    if verbose:
        logger.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)
    if quiet:
        logger.setLevel(logging.ERROR)

    config = datman.config.config(filename=site_config, study=project)
    user_name, password = get_xnat_credentials(config, xnat_cred)
    xnat_url = config.get_key('XNATSERVER')

    scan_complete_records = get_project_redcap_records(config, redcap_cred)

    with XNATConnection(user_name, password, xnat_url) as connection:
        for record in scan_complete_records:
            link_shared_ids(config, connection, record)

def get_xnat_credentials(config, xnat_cred):
    if not xnat_cred:
        xnat_cred = os.path.join(config.get_path('meta'), 'xnat-credentials')

    try:
        credentials = read_credentials(xnat_cred)
        user_name = credentials[0]
        password = credentials[1]
    except IndexError:
        logger.error("XNAT credential file {} is missing the user name or " \
                "password.".format(xnat_cred))
        sys.exit(1)
    return user_name, password

def read_credentials(cred_file):
    credentials = []
    try:
        with open(cred_file, 'r') as creds:
            for line in creds:
                credentials.append(line.strip('\n'))
    except:
        logger.error("Cannot read credential file or file does not exist: " \
                "{}.".format(cred_file))
        sys.exit(1)
    return credentials

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

    project_records = []
    for item in response.json():
        record = Record(item)
        if record.id is None:
            continue
        if record.matches_study(current_study):
            project_records.append(record)

    return project_records

def get_redcap_token(config, redcap_cred):
    if not redcap_cred:
        redcap_cred = os.path.join(config.get_path('meta'), 'redcap-token')

    try:
        token = read_credentials(redcap_cred)[0]
    except IndexError:
        logger.error("REDCap credential file {} is empty.".format(redcap_cred))
        sys.exit(1)
    return token

def link_shared_ids(config, connection, record):
    xnat_archive = config.get_key('XNAT_Archive', site=record.id.site)
    project = connection.select.project(xnat_archive)
    subject = project.subject(str(record.id))
    experiment = get_experiment(subject)

    if not experiment:
        logger.error("No matching experiments for subject {}." \
                " Skipping".format(record.id))
        return

    logger.debug("Working on subject {} in project {}".format(record.id,
            xnat_archive))

    if record.comment and not DRYRUN:
        update_xnat_comment(experiment, subject, record)

    if record.shared_ids and not DRYRUN:
        update_xnat_shared_ids(subject, record)
        make_links(record, config)

def get_experiment(subject):
    experiment_names = subject.experiments().get()

    if not experiment_names:
        logger.debug("{} does not have any MR scans".format(subject))
        return None
    elif len(experiment_names) > 1:
        logger.error("{} has more than one MR scan. Updating only the " \
                "first".format(subject))

    return subject.experiment(experiment_names[0])

def update_xnat_comment(experiment, subject, record):
    logger.debug("Subject {} has comment: \n {}".format(record.id,
            record.comment))
    try:
        experiment.attrs.set("note", record.comment)
        subject.attrs.set("xnat:subjectData/fields/field[name='comments']/field",
                "See MR Scan notes")
    except xnat.core.errors.DatabaseError:
        logger.error('{} scan comment is too long for notes field. Adding ' \
              'note to check redcap record instead.'.format(record.id))
        subject.attrs.set("xnat:subjectData/fields/field[name='comments']/field",
                'Comment too long, refer to REDCap record.')

def update_xnat_shared_ids(subject, record):
    logger.debug("{} has alternate id(s) {}".format(record.id, record.shared_ids))
    try:
        subject.attrs.set("xnat:subjectData/fields/field[name='sharedids']/field",
                ", ".join(record.shared_ids))
    except xnat.core.errors.DatabaseError:
        logger.error('{} shared id list too long for xnat field, adding note '\
                'to check REDCap record instead.'.format(record.id))
        subject.attrs.set("xnat:subjectData/fields/field[name='sharedids']/field",
                'ID list too long, refer to REDCap record.')

def make_links(record):
    source = record.id
    for target in record.shared_ids:
        logger.info("Making links from source {} to target {}".format(source,
                target))

        command = "dm-link-project-scans.py {} {}".format(source, target)
        return_code, out = datman.utils.run(command)
        if return_code:
            logger.error("dm-link-project-scans failed, cannot link source {} "
                    "to target {}. ".format(source, target))
            return

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
        keys = record_dict.keys()
        shared_id_fields = []
        for key in keys:
            if 'shared_parid' in key:
                shared_id_fields.append(key)

        shared_ids = []
        for key in shared_id_fields:
            value = record_dict[key]
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
            logger.error("REDCap record with record_id {} contains non-datman" \
                    " ID {}.".format(self.record_id, subid))
            return None
        return subject_id

class XNATConnection(object):
    def __init__(self, user_name, password, xnat_url):
        self.user = user_name
        self.password = password
        self.server = "https://" + xnat_url

    def __enter__(self):
        self.connection = xnat.Interface(server=self.server, user=self.user,
                password=self.password)
        return self.connection

    def __exit__(self, type, value, traceback):
        self.connection.disconnect()

if __name__ == '__main__':
    main()
