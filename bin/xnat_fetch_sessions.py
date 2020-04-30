#!/usr/bin/env python
"""
This script fetches all sessions from an xnat server and stores each found
session as a zip file. It was originally created to grab data from OPT CU's
xnat server and store it in the data/zips folder for later upload to our server.

If this script is provided with only the study the datman configuration files
will be searched for the following configuration:

    - XNAT_source : URL of the server to pull from
    - XNAT_source_archive: Name of the XNAT project on XNAT_source to pull from
    - XNAT_source_credentials: Name of the file in metadata (or the full
      path to a file stored elsewhere) that contains the username and password
      (separated by a newline) to use to log in to XNAT_source

These variables can be added at the project level or the site level (or both if
a site overrides some project default).

Usage:
    xnat_fetch_sessions.py [options] <project> <server> <username> <password> <destination>
    xnat_fetch_sessions.py [options] <study>


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
    -s, --site SITE         Restricts to checking only the configuration for
                            the given site. Only relevant if <study> is given.
    -l, --log-to-server     Set whether to log to the logging server.
                            Only used if <study> is given.
    -n, --dry-run           Do nothing
    -v, --verbose
    -d, --debug
    -q, --quiet

"""  # noqa: E501
import os
import sys
import glob
import shutil
import logging
import logging.handlers
from zipfile import ZipFile

from docopt import docopt

import datman.config
import datman.xnat
import datman.utils

DRYRUN = False

logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))


def main():
    global DRYRUN
    arguments = docopt(__doc__)
    xnat_project = arguments['<project>']
    xnat_server = arguments['<server>']
    username = arguments['<username>']
    password = arguments['<password>']
    destination = arguments['<destination>']
    study = arguments['<study>']
    given_site = arguments['--site']
    use_server = arguments['--log-to-server']
    DRYRUN = arguments['--dry-run']

    if arguments['--debug']:
        logger.setLevel(logging.DEBUG)
    elif arguments['--verbose']:
        logger.setLevel(logging.INFO)
    elif arguments['--quiet']:
        logger.setLevel(logging.ERROR)

    if not study:
        with datman.xnat.xnat(xnat_server, username, password) as xnat:
            download_subjects(xnat, xnat_project, destination)
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
            logger.error("{}".format(e))
            continue
        username, password = get_credentials(credentials_file)
        with datman.xnat.xnat(server, username, password) as xnat:
            download_subjects(xnat, project, destination)


def download_subjects(xnat, xnat_project, destination):
    try:
        current_zips = os.listdir(destination)
    except FileNotFoundError:
        os.mkdir(destination)

    for subject_id in xnat.get_subject_ids(xnat_project):
        try:
            subject = xnat.get_subject(xnat_project, subject_id)
        except Exception as e:
            logger.error("Failed to get subject {} from xnat. "
                         "Reason: {}".format(subject_id, e))
            continue

        exp_names = [item for item in subject.experiments.keys()]

        if not exp_names:
            logger.error("Subject {} has no experiments.".format(subject.name))
            continue

        if len(exp_names) > 1:
            logger.error("Found {} experiments for subject {}".format(
                len(exp_names), subject.name))
            continue

        experiment = subject.experiments[exp_names[0]]

        zip_name = subject.name.upper() + ".zip"
        zip_path = os.path.join(destination, zip_name)
        if zip_name in current_zips and not update_needed(
                zip_path, experiment, xnat):
            logger.debug("All data downloaded for {}. Passing.".format(
                experiment.name))
            continue

        if DRYRUN:
            logger.info("Would have downloaded experiment {} from project "
                        "{} to {}".format(
                            experiment.name, xnat_project, zip_path))
            continue

        with datman.utils.make_temp_directory() as temp:
            try:
                temp_zip = experiment.download(
                    xnat, temp, zip_name=zip_name)
            except Exception as e:
                logger.error("Cant download experiment {}. Reason: {}"
                             "".format(experiment, e))
                continue
            restructure_zip(temp_zip, zip_path)


def update_needed(zip_file, experiment, xnat):
    """
    This checks if an update is needed the same way dm_xnat_upload does. The
    logic is not great. A single file being deleted / truncated / corrupted
    does not get noticed. Both of them need an update at some later date,
    preferably to use XNAT's metadata on num of files and file size.
    """
    zip_headers = datman.utils.get_archive_headers(zip_file)
    zip_experiment_ids = get_experiment_ids(zip_headers)
    if len(set(zip_experiment_ids)) > 1:
        logger.error("Zip file contains more than one experiment: "
                     "{}. Passing.".format(zip_file))
        return False

    if experiment.uid not in zip_experiment_ids:
        logger.error("Zip file UID does not match xnat experiment "
                     "of the same name: {}".format(zip_file))
        return False

    zip_scan_uids = get_scan_uids(zip_headers)
    zip_resources = get_resources(zip_file)
    xnat_resources = experiment.get_resources(xnat)

    if not files_downloaded(zip_resources, xnat_resources) or \
       not files_downloaded(zip_scan_uids, experiment.scan_UIDs):
        logger.error("Some of XNAT contents for {} is missing from file "
                     "system. Zip file will be deleted and recreated"
                     "".format(experiment.name))
        return True

    return False


def get_experiment_ids(zip_file_headers):
    return [scan.StudyInstanceUID for scan in zip_file_headers.values()]


def get_scan_uids(zip_file_headers):
    return [scan.SeriesInstanceUID for scan in zip_file_headers.values()]


def get_resources(zip_file):
    with ZipFile(zip_file) as zf:
        zip_resources = datman.utils.get_resources(zf)
    return zip_resources


def files_downloaded(local_list, remote_list):
    # If given paths, need to strip them
    local_list = [os.path.basename(item) for item in local_list]
    remote_list = [os.path.basename(item) for item in remote_list]
    # Length must also be checked, because if paths were given duplicates are
    # meaningful and will be lost by checking for subset only
    downloaded = (len(local_list) >= len(remote_list) and
                  set(remote_list).issubset(set(local_list)))
    return downloaded


def get_credentials(credentials_path):
    try:
        with open(credentials_path, 'r') as cred_file:
            cred_contents = cred_file.readlines()
    except Exception as e:
        logger.critical("Can't read credentials file {}"
                        "".format(credentials_path))
        raise e
    try:
        username = cred_contents[0].strip()
        password = cred_contents[1].strip()
    except IndexError:
        logger.critical("Credentials file incorrectly formatted. Please "
                        "ensure that file contains only a username followed "
                        "by a password and that they are separated by a "
                        "newline")
        sys.exit(1)
    return username, password


def add_server_handler(config):
    try:
        server_ip = config.get_key('LOGSERVER')
    except datman.config.UndefinedSetting:
        raise KeyError("\'LOGSERVER\' not defined in site config file.")
    server_handler = logging.handlers.SocketHandler(
                                server_ip,
                                logging.handlers.DEFAULT_TCP_LOGGING_PORT)
    logger.addHandler(server_handler)


def get_xnat_config(config, site):
    try:
        cred_file = config.get_key('XNAT_source_credentials', site=site)
        server = config.get_key('XNAT_source', site=site)
        archive = config.get_key('XNAT_source_archive', site=site)
    except datman.config.UndefinedSetting:
        raise KeyError("Missing configuration. Please ensure study or site "
                       "configuration defines all needed values: XNAT_source, "
                       "XNAT_source_credentials, XNAT_source_archive. See "
                       "help string for more details.")

    destination = config.get_path('zips')

    # User may provide full path or name of a file in metadata folder
    if os.path.exists(cred_file):
        credentials_path = cred_file
    else:
        credentials_path = os.path.join(config.get_path('meta'), cred_file)
        if not os.path.exists(credentials_path):
            logger.critical("Can't find credentials file at {} or {}. Please "
                            "check that 'XNAT_source_credentials' is set "
                            "correctly.".format(cred_file, credentials_path))
            sys.exit(1)

    return credentials_path, server, archive, destination


def restructure_zip(temp_zip, output_zip):
    """
    Folder structure is apparently meaningful for the resources of some
    studies, but download from another XNAT server can leave the resources
    nested inside unneeded folders.
    """
    # Only one found so far
    bad_prefix = 'resources/MISC/'

    temp_path, _ = os.path.split(temp_zip)
    extract_dir = datman.utils.define_folder(os.path.join(temp_path,
                                                          "extracted"))

    with ZipFile(temp_zip, 'r') as zip_handle:
        if not bad_folders_exist(zip_handle, bad_prefix):
            # No work to do, move downloaded zip and return
            move(temp_zip, output_zip)
            return
        zip_handle.extractall(extract_dir)

    for item in glob.glob(os.path.join(extract_dir, bad_prefix, "*")):
        move(item, extract_dir)

    remove_snapshots(extract_dir)
    remove_empty_dirs(extract_dir)
    datman.utils.make_zip(extract_dir, output_zip)


def bad_folders_exist(zip_handle, prefix):
    for item in zip_handle.namelist():
        if item.startswith(prefix):
            return True
    return False


def remove_snapshots(base_dir):
    """
    Snapshots arent needed for anything but get pulled down for every series
    when they exist.
    """
    for cur_path, folders, files in os.walk(base_dir):
        if folders and 'SNAPSHOTS' in folders:
            shutil.rmtree(os.path.join(cur_path, 'SNAPSHOTS'))


def remove_empty_dirs(base_dir):
    empty_dir = os.path.join(base_dir, 'resources')
    try:
        shutil.rmtree(empty_dir)
    except OSError as e:
        logger.info("Cant delete {}. Reason: {}".format(empty_dir, e))


def move(source, dest):
    try:
        shutil.move(source, dest)
    except Exception:
        logger.error("Couldnt move {} to destination {}".format(source, dest))


if __name__ == "__main__":
    main()
