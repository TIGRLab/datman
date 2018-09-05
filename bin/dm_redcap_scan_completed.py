#!/usr/bin/env python
"""
Add MR comments from the Scan Completed instrument on REDCap to the database.

Usage:
    dm_redcap_scan_completed.py [options] <study>

Arguments:
    <study>             Name of the study to process

Options:
    -q --quiet          Less logging
    -v --verbose        Verbose logging
    -d --debug          Debug logging
"""

import os
import sys
import requests
import logging

from docopt import docopt

import datman.config
import datman.scanid
import datman.dashboard

logger = logging.getLogger(os.path.basename(__file__))

cfg = None
dashboard = None
redcap_url = None
redcap_version = None
redcap_project = None
instrument = None


def read_token(token_file):
    if not os.path.isfile(token_file):
        logger.error('REDCap token file: {} not found'.format(token_file))
        raise IOError

    with open(token_file, 'r') as token_file:
        token = token_file.readline().strip()

    return token


def get_records(api_url, token, instrument):
    payload = {'token': token,
               'content': 'record',
               'forms': instrument,
               'format': 'json',
               'type': 'flat',
               'rawOrLabel': 'raw',
               'fields': 'record_id'}
    response = requests.post(api_url, data=payload)
    return response


def get_version(api_url, token):
    payload = {'token': token,
               'content': 'version'}
    response = requests.post(api_url, data=payload)
    version = response.content
    return version


def add_session_redcap(record):
    record_id = record['record_id']
    subject_id = record[cfg.get_key(['REDCAP_SUBJ'])].upper()
    if not datman.scanid.is_scanid(subject_id):
        try:
            subject_id = subject_id + '_01'
            datman.scanid.is_scanid(subject_id)
        except:
            logger.error('Invalid session: {}, skipping'.format(subject_id))
            return

    ident = datman.scanid.parse(subject_id)
    session_name = ident.get_full_subjectid_with_timepoint()
    session_date = record[cfg.get_key(['REDCAP_DATE'])]

    try:
        session = dashboard.get_add_session(session_name,
                                            date=session_date,
                                            create=True)
    except datman.dashboard.DashboardException as e:
        logger.error('Failed adding session {} to dashboard'.format(session_name))

    try:
        datman.dashboard.add_redcap(session,
                                 record_id,
                                 session_date,
                                 cfg.get_key(['REDCAP_EVENTID'])[record['redcap_event_name']],
                                 record[cfg.get_key(['REDCAP_COMMENTS'])],
                                 redcap_url,
                                 redcap_version,
                                 redcap_project,
                                 instrument)
    except:
        logger.error('Failed adding REDCap info for session {} to dashboard'.format(session_name))


def main():
    global cfg
    global dashboard
    global redcap_url
    global redcap_version
    global redcap_project
    global instrument

    arguments = docopt(__doc__)
    study = arguments['<study>']
    quiet = arguments['--quiet']
    verbose = arguments['--verbose']
    debug = arguments['--debug']

    # setup logging
    ch = logging.StreamHandler(sys.stdout)
    log_level = logging.WARN

    if quiet:
        log_level = logging.ERROR
    if verbose:
        log_level = logging.INFO
    if debug:
        log_level = logging.DEBUG

    logger.setLevel(log_level)
    ch.setLevel(log_level)

    formatter = logging.Formatter('%(asctime)s - %(name)s - {study} - '
                                  '%(levelname)s - %(message)s'.format(
                                       study=study))
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logging.getLogger('datman.utils').addHandler(ch)

    # setup the config object
    cfg = datman.config.config(study=study)

    # get paths
    dir_meta = cfg.get_path('meta')

    # set up the dashboard object
    try:
        dashboard = datman.dashboard.dashboard(study)
    except datman.dashboard.DashboardException as e:
        raise e
        logger.error('Failed to initialise dashboard')

    # configure redcap variables
    api_url = cfg.get_key(['REDCAP_URL'])
    redcap_url = api_url.replace('/api/', '/')

    token_path = os.path.join(dir_meta, cfg.get_key(['REDCAP_TOKEN']))
    token = read_token(token_path)

    redcap_project = cfg.get_key(['REDCAP_PROJECTID'])
    instrument = cfg.get_key(['REDCAP_INSTRUMENT'])

    redcap_version = get_version(api_url, token)

    response = get_records(api_url, token, instrument)

    project_records = []
    for item in response.json():
        # only grab records where instrument has been marked complete
        if not (item[cfg.get_key(['REDCAP_DATE'])] and
                item[cfg.get_key(['REDCAP_STATUS'])] == '1'):
            continue
        project_records.append(item)

    for record in project_records:
        add_session_redcap(record)


if __name__ == '__main__':
    main()
