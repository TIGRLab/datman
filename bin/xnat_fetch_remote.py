#!/usr/bin/env python
"""
This script fetches all data from an xnat server and stores each found session
as a zip file. It was originally created to grab data from OPT CU's xnat server
and store it in the data/zips folder for later upload to our own server.

If this script is provided with only the study the datman configuration files
will be searched for the following configuration:

    - XNAT_source : the url of the server to pull from
    - XNAT_source_archive: The name of the XNAT project on XNAT_source to pull from
    - XNAT_source_credentials: the name of the file in metadata (or the full
      path to a file stored elsewhere) that contains the username and password
      (separated by a newline) to use to log in to XNAT_source

These variables can be added at the project level or the site level (or both if
a site overrides some project default).

Usage:
    xnat_fetch_remote.py [options] <project> <server> <username> <password> <destination>
    xnat_fetch_remote.py [options] <study>


Arguments:
    <study>                 Name of the datman study to process.
    <project>               The XNAT project to pull from.
    <server>                Full URL to the remote XNAT server to pull from.
    <username>              Username to use for <server>
    <password>              Password to use for <server>
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
import urllib
import shutil
import logging
import logging.handlers
from zipfile import ZipFile

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
    username = arguments['<username>']
    password = arguments['<password>']
    destination = arguments['<destination>']
    study = arguments['<study>']
    given_site = arguments['--site']
    use_server = arguments['--log-to-server']

    if not study:
        get_data(xnat_project, xnat_server, username, password, destination)
        return

    config = datman.config.config(study=study)

    if use_server:
        add_server_handler(config)

    sites = [given_site] if given_site else config.get_sites()

    for site in sites:
        try:
            credentials_file, server, project, destination = get_xnat_config(
                    config, site)
        except KeyError as e:
            logger.error("{}".format(e.message))
            continue
        username, password = get_credentials(credentials_file)
        get_data(project, server, username, password, destination)

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
            zip_name = session_name.upper() + ".zip"
            zip_path = os.path.join(destination, zip_name)
            if zip_name in current_zips and not update_needed(zip_path, session,
                    xnat):
                logger.debug("All data downloaded for {}. Passing.".format(
                        session_name))
                continue
            try:
                zip_file = session.download(xnat, destination,
                        zip_name=zip_name)
            except Exception as e:
                logger.error("Cant download session {}. Reason: {}".format(
                        session_name, e.message))
                continue
            remove_redundant_subfolders(zip_file)

def update_needed(zip_file, session, xnat):
    zip_headers = datman.utils.get_archive_headers(zip_file)

    if not session.experiment:
        logger.error("{} does not have any experiments.".format(session.name))
        return False

    zip_experiment_ids = get_experiment_ids(zip_headers)
    if len(set(zip_experiment_ids)) > 1:
        logger.error("Zip file contains more than one experiment: "
                "{}. Passing.".format(zip_file))
        return False

    if session.experiment_UID not in zip_experiment_ids:
        logger.error("Zip file experiment ID does not match xnat session of "
                "the same name: {}".format(zip_file))
        return False

    zip_scan_uids = get_scan_uids(zip_headers)
    zip_resources = get_resources(zip_file)
    xnat_resources = session.get_resources(xnat)

    if not files_downloaded(zip_resources, xnat_resources) or not files_downloaded(
            zip_scan_uids, session.scan_UIDs):
        logger.error("Some of XNAT contents for {} is missing from file system. "
                "Zip file will be deleted and recreated".format(session.name))
        return True

    return False

def get_experiment_ids(zip_file_headers):
    return [scan.StudyInstanceUID for scan in zip_file_headers.values()]

def get_scan_uids(zip_file_headers):
    return [scan.SeriesInstanceUID for scan in zip_file_headers.values()]

def get_resources(zip_file):
    with zipfile.ZipFile(zip_file) as zf:
        zip_resources = datman.utils.get_resources(zf)
    return [urllib.pathname2url(p) for p in zip_resources]

def files_downloaded(local_list, remote_list):
    return set(remote_list).issubset(set(local_list))

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
        raise KeyError("Missing configuration. Please ensure study or site "
                "configuration defines all needed values: XNAT_source, "
                "XNAT_source_credentials, XNAT_source_archive. See help string "
                "for more details.")

    destination = config.get_path('zips')

    # User may provide full path or name of a file in metadata folder
    if os.path.exists(cred_file):
        credentials_path = cred_file
    else:
        credentials_path = os.path.join(config.get_path('meta'), cred_file)
        if not os.path.exists(credentials_path):
            logger.critical("Can't find credentials file at {} or {}. Please "
                    "check that \'XNAT_source_credentials\' is set "
                    "correctly.".format(cred_file, credentials_path))
            sys.exit(1)

    return credentials_path, server, archive, destination

def remove_redundant_subfolders(zip_file):
    """
    Folder structure is apparently meaningful for the resources of some studies,
    but download from another XNAT server can leave the resources nested inside
    unneeded folders. It seems that the
    """
    bad_prefix = 'resources/MISC/'


    # Open zip as read only
    # For each file in list with bad prefix
        # Extract to temp folder

    # Open file for modification
    # For each extracted file
        # Delete from zip
        # Copy over without bad prefix


    ################################### ADD IN WHEN DONE
    # with datman.utils.make_temp_directory()
    temp = "/tmp/testing_dir/"



    #
    # file_list = []
    # with ZipFile(zip_file, 'r') as zip_handle:
    #     files = zip_handle.namelist()
    #     for item in files:
    #         if item.startswith(bad_prefix):
    #             try:
    #                 zip_handle.extract(item, temp)
    #             except Exception as e:
    #                 logger.error("Could not extract {} from zip file {}. "
    #                         "Any redundant subfolders will be left alone for "
    #                         "this zip.".format(
    #                         item, zip_file))
    #                 return
    #             file_list.append(item)
    #
    # with ZipFile(zip_file, 'a') as zip_handle:
    #

if __name__ == "__main__":
    main()
