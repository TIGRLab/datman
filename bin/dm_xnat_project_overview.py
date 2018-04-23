#!/usr/bin/env python
"""
Compiles a csv overview for all xnat projects associated with the given study.
This csv is identical to the spreadsheet that can be downloaded from the
GUI, except that the Age column (usually empty) has been dropped and
date added / user who added data columns have been added. Additionally, if the
given study is associated with multiple xnat projects the data for all will be
returned in a single spreadsheet.

Usage:
    dm_xnat_project_overview.py [options] <project>

Arguments:
    <project>                   The name of a datman managed project.

Options:
    --output PATH               Specify the output location for the
                                overview csv. By default will be added to the
                                metadata folder for this project.
    --config_file PATH          The site configuration yaml file to use.
                                Overrides the DM_CONFIG environment variable.
    --system STR                The system to run on. Overrides the DM_SYSTEM
                                environment variable.
    --xnat-credentials PATH     The full path to the text file containing an
                                xnat username and password to use. Overrides
                                the xnat-credentials file expected in
                                a project's metadata folder
    -q, --quiet
    -d, --debug
    -v, --verbose

"""
import os
import datetime
import logging

from docopt import docopt
import requests
import pyxnat

import datman.config
import datman.utils

logging.basicConfig(level=logging.WARN,
        format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

def main():
    arguments = docopt(__doc__)
    project = arguments['<project>']
    output_loc = arguments['--output']
    config_file = arguments['--config_file']
    system = arguments['--system']
    xnat_cred = arguments['--xnat-credentials']
    quiet = arguments['--quiet']
    debug = arguments['--debug']
    verbose = arguments['--verbose']

    if verbose:
        logger.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)
    if quiet:
        logger.setLevel(logging.ERROR)

    config = datman.config.config(filename=config_file, system=system,
            study=project)

    output_file = set_output_name(output_loc, config)

    xnat_url = get_xnat_url(config)
    username, password = datman.utils.get_xnat_credentials(config, xnat_cred)
    xnat_project_names = config.get_xnat_projects()
    logger.debug("Summarizing XNAT projects {}".format(xnat_project_names))

    with datman.utils.XNATConnection(xnat_url, username,
            password) as xnat_connection:
        overviews = get_session_overviews(xnat_connection, xnat_project_names)

    with requests.Session() as session:
        session.auth = (username, password)
        MR_ids = get_MR_ids(session, xnat_url, xnat_project_names)

    merged_records = merge_overview_and_labels(overviews, MR_ids)
    write_overview_csv(merged_records, output_file)

def set_output_name(output_loc, config):
    if not output_loc:
        output_loc = config.get_path('meta')

    output_name = os.path.join(output_loc,
            '{}-{}-overview.csv'.format(config.study_name,
            datetime.date.today()))

    logger.info("Output location set to: {}".format(output_name))
    return output_name

def get_xnat_url(config):
    url = config.get_key('XNATSERVER')
    if 'https' not in url:
        url = "https://" + url
    return url

def get_session_overviews(xnat, project_names):
    overview = []
    for project in project_names:
        project_overview = select_project_data(xnat, project)
        if not project_overview:
            logger.error("No mrSessionData found for project {}".format(project))
            continue
        logger.debug("Adding data from project {}".format(project))
        overview.extend(project_overview)
    return overview

def select_project_data(xnat, project, retry=3):
    if retry <= 0:
        logger.error("Could not access xnat for project {}".format(project))
        return None

    constraints = [('xnat:mrSessionData/PROJECT', '=', project)]
    try:
        result = xnat.select('xnat:mrSessionData').where(constraints)
    except pyxnat.core.errors.DatabaseError:
        tries = retry - 1
        logger.info("pyxnat couldn't access database for project {}. Tries "
                "remaining: {}".format(project, tries))
        return select_project_data(xnat, project, retry=retry-1)
    return result.data

def get_MR_ids(xnat_session, xnat_url, xnat_projects):
    MR_ids = []
    for project in xnat_projects:
        response = select_MR_summary(xnat_session, xnat_url, project)
        if not response or response.status_code != 200:
            logger.error("Failed to get MR IDs for project {} with status "
                    "code {}".format(project, response.status_code))
            continue
        try:
            mr_id_records = response.json()['ResultSet']['Result']
        except KeyError:
            logger.error("Cannot parse records for project {}".format(project))
            continue
        MR_ids.extend(mr_id_records)
    return MR_ids

def select_MR_summary(xnat_session, xnat_url, project, retry=3):
    if retry == 0:
        logger.error("Failed to get MR IDs for project {}".format(project))
        return None

    url = "{}/data/archive/experiments?format=json&project={}".format(xnat_url,
            project)
    try:
        response = xnat_session.get(url, timeout=30)
    except requests.exceptions.ReadTimeout:
        tries = retry - 1
        logger.info("XNAT read timed out for project {}. "
                "Tries remaining: {}".format(project, tries))
        response = select_MR_summary(xnat_session, xnat_url, project, retry=tries)
    return response

def merge_overview_and_labels(session_overviews, MR_ids):
    for item in session_overviews:
        try:
            session_id = item['session_id']
        except KeyError:
            logger.error("Could not read session id for record: {}. "
                    "Skipping.".format(item))
            continue
        label, date = find_label_and_date(session_id, MR_ids)
        item['MR_label'] = label
        item['date'] = date
    return session_overviews

def find_label_and_date(session_id, MR_ids):
    for MR_record in MR_ids:
        try:
            current_id = MR_record['ID']
        except KeyError:
            logger.error("Could not read ID from MR_record {}. "
                    "Ignoring it.".format(MR_record))
            MR_ids.remove(MR_record)
            continue
        if current_id == session_id:
            try:
                label = MR_record['label']
            except KeyError:
                logger.error("Could not read label for session {}."
                        "".format(session_id))
                label = "No MR_Label found"
            try:
                date = MR_record['date']
            except KeyError:
                logger.error("Could not read date for session {}"
                        "".format(session_id))
                date = "No date found"
            MR_ids.remove(MR_record)
            return label, date
    return "Cannot find MR ID", "Cannot find date"

def write_overview_csv(records, output_file):
    headers = 'MR_ID,subject_label,project,date,date_added,added_by,scanner,scans\n'
    with open(output_file, 'w') as output:
        output.write(headers)
        for record in records:
            line = get_line(record)
            output.write(line)

def get_line(record):
    MR_ID = get_item(record, 'MR_label')
    date = get_item(record, 'date')
    raw_add_date = get_item(record, 'insert_date')
    date_added = raw_add_date.split(" ")[0]
    added_by = get_item(record, 'insert_user')
    project = get_item(record, 'project')
    subject_label = get_item(record, 'subject_label')
    scanner = get_item(record, 'scanner_csv')
    raw_scan_list = get_item(record, 'mr_scan_count_agg')
    scans = raw_scan_list.replace(', ', ';')
    line = "{mr},{subject},{project},{date},{insert_date},{insert_user}," \
            "{scanner},\"{scans}\"\n".format(mr=MR_ID, subject=subject_label,
            project=project, date=date, insert_date=date_added,
            insert_user=added_by, scanner=scanner, scans=scans)
    return line

def get_item(record, key):
    try:
        item = record[key]
    except KeyError:
        logger.debug("Key {} does not exist in record {}".format(key, record))
        item = "Not found in record."
    return item

if __name__ == "__main__":
    main()
