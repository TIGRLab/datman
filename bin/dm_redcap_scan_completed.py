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
import datman.dashboard as dashboard

logger = logging.getLogger(os.path.basename(__file__))

cfg = None
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


def get_records(api_url, token, instrument, record_key):
    payload = {'token': token,
               'content': 'record',
               'forms': instrument,
               'format': 'json',
               'type': 'flat',
               'rawOrLabel': 'raw',
               'fields': record_key}
    response = requests.post(api_url, data=payload)

    if response.status_code != 200:
        raise Exception('API request failed. HTTP status code: {}.  Reason: '
                        '{}'.format(response.status_code, response.text))

    return response.json()


def get_version(api_url, token):
    payload = {'token': token,
               'content': 'version'}
    response = requests.post(api_url, data=payload)
    version = response.content

    try:
        version = version.decode('UTF-8')
    except AttributeError:
        pass

    return version


def add_session_redcap(record, record_key):
    record_id = record[record_key]
    subject_id = record[cfg.get_key('REDCAP_SUBJ')].upper()
    if not datman.scanid.is_scanid(subject_id):
        subject_id = subject_id + '_01'
        try:
            datman.scanid.is_scanid(subject_id)
        except datman.scanid.ParseException:
            logger.error('Invalid session: {}, skipping'.format(subject_id))
            return
    try:
        ident = parse_id(subject_id)
    except datman.scanid.ParseException:
        logger.error('Invalid session: {}, skipping'.format(subject_id))
        return

    session_date = record[cfg.get_key('REDCAP_DATE')]

    try:
        session = dashboard.get_session(ident, date=session_date, create=True)
    except datman.exceptions.DashboardException as e:
        logger.error('Failed adding session {} to dashboard. Reason: '
                     '{}'.format(ident, e))
        return

    try:
        record_comment = record[cfg.get_key('REDCAP_COMMENTS')]
        event_id = cfg.get_key('REDCAP_EVENTID')[record['redcap_event_name']]
    except (datman.config.UndefinedSetting, datman.config.ConfigException):
        logger.error("Can't add REDCap session info. Verify that "
                     "values 'REDCAP_COMMENTS' and 'REDCAP_EVENTID' are "
                     "correctly defined in the config file")
        return
    except KeyError:
        record_comment = None
        event_id = None

    try:
        session.add_redcap(record_id, redcap_project, redcap_url, instrument,
                           date=session_date,
                           comment=record_comment,
                           event_id=event_id,
                           version=redcap_version)
    except Exception:
        logger.error('Failed adding REDCap info for session {} to '
                     'dashboard'.format(ident))


def parse_id(subject_id):
    """Parse the ID from the redcap form into datman convention.

    Args:
        subject_id (:obj:`str`): A string subject ID

    Raises:
        datman.scanid.ParseException: When an ID can't be converted to a
            valid datman ID.

    Returns:
        datman.scanid.Identifier
    """
    ident = datman.scanid.parse(subject_id)

    if isinstance(ident, datman.scanid.DatmanIdentifier):
        return ident

    # If the redcap form contained a KCNI ID, fields may need to be mapped to
    # the datman version.
    try:
        id_map = cfg.get_key('ID_MAP')
    except datman.config.UndefinedSetting:
        # KCNI site and study fields match the datman fields.
        return ident

    return datman.scanid.parse(subject_id, settings=id_map)


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
    logging.getLogger('datman.dashboard').addHandler(ch)

    # setup the config object
    cfg = datman.config.config(study=study)

    # get paths
    dir_meta = cfg.get_path('meta')

    # configure redcap variables
    api_url = cfg.get_key('REDCAP_URL')
    redcap_url = api_url.replace('/api/', '/')

    token_path = os.path.join(dir_meta, cfg.get_key('REDCAP_TOKEN'))
    token = read_token(token_path)

    redcap_project = cfg.get_key('REDCAP_PROJECTID')
    instrument = cfg.get_key('REDCAP_INSTRUMENT')
    date_field = cfg.get_key('REDCAP_DATE')
    status_field = cfg.get_key('REDCAP_STATUS')
    status_val = cfg.get_key('REDCAP_STATUS_VALUE')
    record_key = cfg.get_key('REDCAP_RECORD_KEY')

    # make status_val into a list
    if not (isinstance(status_val, list)):
        status_val = [status_val]

    redcap_version = get_version(api_url, token)

    response_json = get_records(api_url, token, instrument, record_key)

    project_records = []
    for item in response_json:
        # only grab records where instrument has been marked complete
        if not (item[date_field] and item[status_field] in status_val):
            continue
        project_records.append(item)

    for record in project_records:
        add_session_redcap(record, record_key)


if __name__ == '__main__':
    main()
