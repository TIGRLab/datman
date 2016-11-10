#!/usr/bin/env python
"""
Transfers the scan completed survey information into xnat

Usage:
    transfer_scan_info.py [options] <credential_file>

Arguments:
    <credential_file>       The path to the file containing the xnat user name,
                            xnat password, and REDCap token with each on a separate
                            line.

Options:
    --redcap URL            The url to access REDCap's api for this site
                            [default: https://edc.camhx.ca/redcap/api/]

    --xnat URL              The url to access the XNAT database
                            [default: https://xnat.imaging-genetics.camh.ca:443]

    -v, --verbose           Print descriptive messages as updates are being done.
"""

import sys
import requests
import pyxnat as xnat
import logging
from docopt import docopt
from contextlib import contextmanager

logging.basicConfig(level=logging.WARN, format='%(levelname)s:%(message)s')
LOGGER = logging.getLogger(__name__)

def main():
    arguments   = docopt(__doc__)
    cred_file   = arguments['<credential_file>']
    redcap_url  = arguments['--redcap']
    xnat_url    = arguments['--xnat']
    verbose     = arguments['--verbose']

    if verbose:
        LOGGER.setLevel(logging.INFO)

    token, user_name, password = read_credentials(cred_file)
    scan_complete_surveys = get_redcap_records(token, redcap_url)

    for record in scan_complete_surveys:
        with xnat_connection(user_name, password, xnat_url) as connection:
            add_record_to_xnat(connection, record)

def read_credentials(cred_file):
    try:
        lines = open(cred_file, 'r').readlines()
    except:
        sys.exit("Cannot read credential file {}.".format(cred_file))

    try:
        user_name = lines[0].strip('\n')
        password = lines[1].strip('\n')
        token = lines[2].strip('\n')
    except IndexError:
        sys.exit("Missing credentials. Please ensure that the credential file "\
                 "contains the xnat user name, the xnat password and the "\
                 "REDCap token on a separate line each and in that order.")

    return (token, user_name, password)

def get_redcap_records(token, redcap_url):
    payload = {'token': token,
               'format': 'json',
               'content': 'record',
               'type': 'flat'}

    response = requests.post(redcap_url, data=payload)

    if response.status_code != 200:
        sys.exit("Cannot access REDCap data. Check that the URL and token are "\
                 "correct.")

    return response.json()

@contextmanager
def xnat_connection(user_name, password, xnat_url):
    connection = xnat.Interface(server=xnat_url,
                                user=user_name,
                                password=password)
    yield connection
    connection.disconnect()

def add_record_to_xnat(xnat_connection, record):
    subject_id = record['par_id']
    comment = record['cmts']
    shared_ids = get_shared_ids(record)

    matching_projects = get_projects_containing_id(xnat_connection, subject_id)

    if matching_projects is None:
        LOGGER.error("no records in the given database have subject id "\
              "{}".format(subject_id))
        return

    for project_name in matching_projects:
        project = xnat_connection.select.project(project_name)
        subject = project.subject(subject_id)
        experiment = get_experiment(subject)

        if experiment is None:
            LOGGER.info("Skipping {}".format(subject_id))
            return

        LOGGER.info("Working on {} in project {}".format(subject_id, project_name))

        # Handle comment field update
        if comment:
            LOGGER.info("{} has comment {}".format(subject_id, comment))
            try:
                experiment.attrs.set('note', comment)
                subject.attrs.set("xnat:subjectData/fields/field[name='comments']/field",
                              "See MR Scan notes")
                LOGGER.info("{} comment field updated".format(subject_id))
            except xnat.core.errors.DatabaseError:
                LOGGER.error('{} scan comment is too long for notes field. Adding ' \
                      'note to check redcap record instead.'.format(subject_id))
                subject.attrs.set("xnat:subjectData/fields/field[name='comments']/field",
                            'Comment too long, refer to REDCap record.')

        # Handle sharedIds field update
        if shared_ids:
            LOGGER.info("{} has alternate id(s) {}".format(subject_id, shared_ids))
            try:
                subject.attrs.set("xnat:subjectData/fields/field[name='sharedids']/field",
                          shared_ids)
                LOGGER.info("{} sharedIds field updated".format(subject_id))
            except xnat.core.errors.DatabaseError:
                LOGGER.error('{} shared id list too long for xnat field, adding note '\
                      'to check REDCap record instead.'.format(subject_id))
                subject.attrs.set("xnat:subjectData/fields/field[name='sharedids']/field",
                          'ID list too long, refer to REDCap record.')

def get_shared_ids(record):
    shared_ids = []
    max_num_shared_id_fields = len(record.keys())

    for num in xrange(1, max_num_shared_id_fields):
        current_id_field = 'shared_parid_{}'.format(num)
        if current_id_field in record.keys():
            shared_ids.append(record[current_id_field])
        else:
            # Remaining fields in record do not contain shared id info so exit
            break

    shared_ids = filter(None, shared_ids)
    id_string = ', '.join(shared_ids)

    return id_string

def get_projects_containing_id(xnat_connection, subject_id):
    '''Returns a list of all projects in the xnat database that contain a record
    with the subject label field <subject_id>'''

    constraints =  [('xnat:subjectData/SUBJECT_LABEL', '=', subject_id),
                     'AND']
    matching_projects = xnat_connection.select('xnat:subjectData', ['xnat:subjectData/PROJECT']).where(constraints)

    projects = []
    for line in matching_projects:
        projects.append(line['project'])

    return projects

def get_experiment(subject):
    experiment_names = subject.experiments().get()

    if len(experiment_names) == 0:
        LOGGER.error("{} does not have any MR scans.".format(subject))
        return None
    elif len(experiment_names) > 1:
        LOGGER.error("{} has more than one MR scan.".format(subject))
        return None

    return subject.experiment(experiment_names[0])

if __name__ == '__main__':
    main()
