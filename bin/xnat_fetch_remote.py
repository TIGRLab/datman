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
    xnat_fetch_remote.py [options] <project> <server> <credentials> <destination>
    xnat_fetch_remote.py [options] <study>


Arguments:
    <study>                 Name of the datman study to process.
    <project>               The XNAT project to pull from.
    <server>                Full URL to the remote XNAT server to pull from.
    <credentials>           The full path to a file containing the xnat username
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
import logging
import logging.handlers

from docopt import docopt

import datman.config
import datman.xnat

logging.basicConfig(level=logging.WARN,
        format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

def main():
    arguments = docopt(__doc__)
    xnat_project = arguments['<project>']
    xnat_server = arguments['<server>']
    xnat_credentials = arguments['<credentials>']
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
    with datman.xnat.xnat(xnat_server, username, password) as xnat:
        project = xnat.get_project(xnat_project)
        print(project)

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
