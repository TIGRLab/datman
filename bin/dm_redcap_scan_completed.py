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

from dashboard import db
from dashboard.models import Session

# set up logging
logger = logging.getLogger(__name__)

formatter = logging.Formatter('%(asctime)s - %(name)s - '
                              '%(levelname)s - %(message)s')

log_handler = logging.StreamHandler(sys.stdout)
log_handler.setFormatter(formatter)

logger.addHandler(log_handler)


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
    record_id = record['record_id'].upper()
    session_date = record[cfg.get_key(['REDCAP_DATE'])]
    session_comments = record[cfg.get_key(['REDCAP_COMMENTS'])]

    query = Session.query.filter(Session.name.like('%{}%'.format(record_id)))

    if query.count() < 1:
        logger.warn('Session {} not found, skipping'.format(record_id))
        return

    if query.count() > 1:
        # if query brings multiple sessions, try filtering by scan date
        query = query.filter(Session.date == session_date)

    # only add redcap records if a single query is found
    if not query.count() == 1:
        logger.error('Session {} with scan date {} could not be matched, \
                      skipping'.format(record_id, session_date))
        return

    session = query.first()
    session.redcap_record = record_id
    session.redcap_entry_date = session_date
    session.redcap_comment = session_comments
    session.redcap_url = redcap_url
    session.redcap_version = redcap_version
    session.redcap_projectid = redcap_project
    session.redcap_instrument = instrument
    db.session.add(session)
    logger.info('Added record for session {}'.format(record_id))
    db.session.commit()


def main():
    global cfg
    global redcap_url
    global redcap_version
    global redcap_project
    global instrument

    arguments = docopt(__doc__)
    study = arguments['<study>']
    quiet = arguments['--quiet']
    verbose = arguments['--verbose']
    debug = arguments['--debug']

    # setup log levels
    log_level = logging.WARN

    if quiet:
        log_level = logging.ERROR
    if verbose:
        log_level = logging.INFO
    if debug:
        log_level = logging.DEBUG

    logger.setLevel(log_level)
    log_handler.setLevel(log_level)

    # setup the config object
    cfg = datman.config.config(study=study)

    # get paths
    dir_meta = cfg.get_path('meta')

    # configure redcap variables
    api_url = cfg.get_key(['REDCAP_URL'])
    redcap_url = api_url.replace('/api/', '/')

    token_path = os.path.join(dir_meta, cfg.get_key(['REDCAP_TOKEN']))
    token = read_token(token_path)

    instrument = cfg.get_key(['REDCAP_INSTRUMENT'])

    redcap_project = cfg.get_key(['REDCAP_PROJECTID'])

    redcap_version = get_version(api_url, token)

    response = get_records(api_url, token, instrument)

    project_records = []
    for item in response.json():
        # only grab records where instrument has been marked complete
        if not (item[cfg.get_key(['REDCAP_DATE'])] and
                item['{}_complete'.format(instrument)] == '2'):
            continue
        project_records.append(item)

    for record in project_records:
        add_session_redcap(record)


if __name__ == '__main__':
    main()
