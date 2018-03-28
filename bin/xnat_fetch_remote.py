#!/usr/bin/env python
"""
This script fetches all data from an xnat server and stores each found session
as a zip file. It was originally created to grab data from OPT CU's xnat server
and store it in the data/zips folder for later upload to our own server.

There are two ways to use this script:

    1. Specify all the needed details at the command line: XNAT project name,
       server URL, path to a file containing login credentials and an output path
    2. Specify a datman study. The configuration files will then be searched for
       an 'XNAT_source_archive' (gives XNAT project name), 'XNAT_source' (server
       URL), and 'XNAT_source_credentials' (gives name of a credentials file
       stored in metadata or the full path to a file elsewhere). These can be
       added to the study configuration at either the site or study level. The
       output location will be set to the study's 'zips' folder.

Whether the credentials file is found from the command line or the configuration
file the format is expected to be username then password each separated by a newline.

Usage:
    xnat_fetch_remote.py [options] <project> <server> <credentials_path> <destination>
    xnat_fetch_remote.py [options] <study>


Arguments:
    <study>                 Name of the datman study to process.
    <project>               The XNAT project to pull from.
    <server>                Full URL to the remote XNAT server to pull from.
    <credentials_path>      The full path to a file containing the xnat username
                            a newline, and then the xnat password.
    <destination>           The full path to the intended destination for all
                            downloaded data. The script will attempt to avoid
                            redownloading data if data already exists at
                            this location.

Options:
    -s, --site SITE         The name of a site defined in the project configuration.
                            Restricts the script to checking only the given
                            site. Only relevant if <study> is given.
    -l, --log-to-server     Set whether to log to the logging server.
                            Only used if <study> is given.
    -n, --dry-run           Do nothing
    -v, --verbose
    -d, --debug
    -q, --quiet

"""
import os
import sys
import zipfile
import logging
import logging.handlers

from docopt import docopt

import datman.config
import datman.xnat
import datman.utils

logging.basicConfig(level=logging.WARN,
        format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

def main():
    arguments = docopt(__doc__)
    xnat_project = arguments['<project>']
    xnat_server = arguments['<server>']
    xnat_credentials = arguments['<credentials_path>']
    destination = arguments['<destination>']
    study = arguments['<study>']
    given_site = arguments['--site']
    use_server = arguments['--log-to-server']

    if not study:
        username, password = get_credentials(xnat_credentials)
        get_data(xnat_project, xnat_server, username, password, destination)
        return

    config = datman.config.config(study=study)

    if use_server:
        add_server_handler(config)

    sites = [given_site] if given_site else config.get_sites()

    for site in sites:
        credentials, server, project, destination = get_xnat_config(config, site)
        username, password = get_credentials(credentials)
        get_data(project, server, username, password, destination)

def get_credentials(credentials_path):
    try:
        with open(credentials_path, 'r') as cred_file:
            cred_contents = cred_file.readlines()
    except:
        logger.critical("Can't read credentials file: {}".format(credentials_path))
        sys.exit(1)
    try:
        username = cred_contents[0].strip()
        password = cred_contents[1].strip()
    except IndexError:
        logger.critical("Credentials file incorrectly formatted. Please ensure "
                "that file contains only a username followed by a password and "
                "that they are separated by a newline")
        sys.exit(1)
    return username, password

def get_data(xnat_project, xnat_server, username, password, destination):
    current_zips = os.listdir(destination)
    with datman.xnat.xnat(xnat_server, username, password) as xnat:
        sessions_list = xnat.get_sessions(xnat_project)
        for session_metadata in sessions_list:
            session_name = session_metadata['label']
            try:
                session = xnat.get_session(xnat_project, session_name)
            except Exception as e:
                logger.error("Failed to get session {} from xnat. "
                        "Reason: {}".format(session_name, e.message))
                continue
            zip_name = session_name + ".zip"
            zip_path = os.path.join(destination, zip_name)
            if zip_name in current_zips and not update_needed(zip_path, session, xnat):
                print("Found all data for {}. Passing.".format(session_name))
                continue
            print("Download Needed for {}!".format(session_name))
            #download_data()
            # scan_url = "data/archive/projects/{project}/subjects/{subid}/experiments/{subid}/scans/ALL/files?format=zip"
            # resources_url = "/data/archive/projects/{project}/subjects/{subid}/experiments/{subid}/files?format=zip"

def update_needed(zip_file, session, xnat):
    zip_headers = datman.utils.get_archive_headers(zip_file)

    if not session.experiment:
        logger.error("{} does not have any experiments.".format(session.name))
        return False

    # Check experiment matches
    zip_experiment_ids = [scan.StudyInstanceUID for scan in zip_headers.values()]
    if len(set(zip_experiment_ids)) > 1:
        logger.error("Zip file contains more than one experiment: "
                "{}. Passing.".format(zip_file))
        return False

    if session.experiment_UID not in zip_experiment_ids:
        logger.error("Zip file experiment ID does not match xnat session of "
                "the same name: {}".format(zip_file))
        return False

    zip_scan_uids = [scan.SeriesInstanceUID for scan in zip_headers.values()]

    # Check resource data matches
    xnat_resources = session.get_resources(xnat)
    with zipfile.ZipFile(zip_file) as zf:
        zip_resources = datman.utils.get_resources(zf)
    zip_resources = [urllib.pathname2url(p) for p in zip_resources]

    if not files_downloaded(zip_resources, xnat_resources) or not files_downloaded(
            zip_scan_uids, session.scan_UIDs):
        logger.error("Some of XNAT contents for {} is missing from file system. "
                "Zip file will be deleted and recreated".format(session.name))
        return True

    return False

def files_downloaded(local_list, remote_list):
    return set(remote_list).issubset(set(local_list))

def get_experiment(session):
    experiments = [exp for exp in session['children']
            if exp['field'] == 'experiments/experiment']

    session_id = session['data_fields']['label']
    if not experiments:
        raise ValueError("No experiments found for {}".format(session_id))
    elif len(experiments) > 1:
        logger.error("More than one session uploaded to ID {}. Processing "
                "only the first.".format(session_id))

    return experiments[0]['items'][0]

def add_server_handler(config):
    try:
        server_ip = config.get_key('LOGSERVER')
    except KeyError:
        raise KeyError("\'LOGSERVER\' not defined in site config file.")
    server_handler = logging.handlers.SocketHandler(server_ip,
            logging.handlers.DEFAULT_TCP_LOGGING_PORT)
    logger.addHandler(server_handler)

def get_xnat_config(config, site):
    try:
        cred_file = config.get_key('XNAT_source_credentials', site=site)
        server = config.get_key('XNAT_source', site=site)
        archive = config.get_key('XNAT_source_archive', site=site)
    except KeyError:
        logger.critical("Missing configuration. Please ensure study or site "
                "configuration defines all needed values: XNAT_source, "
                "XNAT_source_credentials, XNAT_source_archive. See help string "
                "for more details.")
        sys.exit(1)

    destination = config.get_path('zips')

    # User may provide full path or name of a file in metadata folder
    if os.path.exists(cred_file):
        credentials_path = cred_file
    else:
        credentials_path = os.path.join(config.get_path('meta'), cred_file)
        if not os.path.exists(credentials_path):
            logger.critical("Can't find credentials file at {} or {}. Please "
                    "check that \'XNAT_source_credentials\' is set correctly.".format(
                    cred_file, credentials_path))
            sys.exit(1)

    return credentials_path, server, archive, destination

if __name__ == "__main__":
    main()
