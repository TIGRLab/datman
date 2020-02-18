#!/usr/bin/env python
"""
Renames a session and its experiment.

Usage:
    dm_xnat_rename.py [options] <prev_name> <new_name>
    dm_xnat_rename.py [options] <name_file>

Arguments:
    <prev_name>     The current name on XNAT
    <new_name>      The name to change to
    <name_file>     The full path to a csv file of sessions to rename. Each
                    entry for a session should be formatted as
                    "current_name,new_name", one entry per line.

Options:
    --server,-s <server>        The URL of the xnat server to rename a session
                                on. If unset, it will be read from the
                                'XNATSERVER' environment var

    --user,-u <user>            The username to log in with. If unset, it will
                                be read from the 'XNAT_USER' environment var.

    --pass,-p <pass>            The password to log in with. If unset it will
                                be read from the 'XNAT_PASS' environment var.

    --project xnat_project      Limit the rename to the given XNAT project

    --debug, -d
    --verbose, -v
    --quiet, -q
"""
import os
import logging
from docopt import docopt
from requests import HTTPError

import datman.xnat
import datman.config

logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))


def main():
    arguments = docopt(__doc__)
    name_path = arguments['<name_file>']
    source = arguments['<prev_name>']
    dest = arguments['<new_name>']
    server = arguments['--server']
    user = arguments['--user']
    password = arguments['--pass']
    project = arguments['--project']

    set_log_level(arguments)

    xnat = get_xnat(server, user, password)

    if not name_path:
        rename_xnat_session(xnat, source, dest, project=project)
        return

    names = read_sessions(name_path)
    for entry in names:
        try:
            rename_xnat_session(xnat, entry[0], entry[1], project=project)
        except Exception as e:
            logger.error("Failed to rename {} to {}. Reason - "
                         "{}".format(entry[0], entry[1], e))


def set_log_level(arguments):
    debug = arguments['--debug']
    verbose = arguments['--verbose']
    quiet = arguments['--quiet']

    # The xnat module is noisy, its default level should be 'error'
    xnat_logger = logging.getLogger("datman.xnat")
    xnat_logger.setLevel(logging.ERROR)

    if debug:
        logger.setLevel(logging.DEBUG)
        xnat_logger.setLevel(logging.DEBUG)
    if verbose:
        logger.setLevel(logging.INFO)
        xnat_logger.setLevel(logging.INFO)
    if quiet:
        logger.setLevel(logging.ERROR)


def get_xnat(server, user, password):
    if not server:
        config = datman.config.config()
        server = datman.xnat.get_server(config)
    if not user or not password:
        user, password = datman.xnat.get_auth()
    return datman.xnat.xnat(server, user, password)


def read_sessions(name_file):
    with open(name_file, "r") as name_list:
        lines = name_list.readlines()

    entries = []
    for entry in lines:
        fields = entry.split(",")
        if len(fields) != 2:
            logger.error("Invalid entry found: {}. Ignoring".format(entry))
            continue
        entries.append([field.strip() for field in fields])
    logger.debug("Found {} valid entries".format(len(entries)))
    return entries


def rename_xnat_session(xnat, current, new, project=None, tries=3):
    """
    Returns True if rename is successful
    """
    if not project:
        project = get_project(current)

    logger.info("Renaming {} to {} in project {}".format(current, new,
                                                         project))

    try:
        xnat.rename_session(project, current, new)
    except HTTPError as e:
        logger.debug("Error was raised: {}".format(e))
        if e.response.status_code == 409:
            if not false_alarm(tries, xnat, project, current, new):
                raise e
        elif e.response.status_code == 422:
            if not retry(tries, xnat, project, current, new):
                raise e
        else:
            raise e
    except datman.xnat.XnatException as e:
        if '0 experiment' in str(e):
            return True
        raise e

    return is_renamed(xnat, project, current, new)


def false_alarm(tries, xnat, project, current, new):
    logger.debug("URL conflict reported")
    try:
        renamed = is_renamed(xnat, project, current, new)
    except datman.xnat.XnatException:
        logger.debug("Likely a real error, exiting.")
        return False
    if renamed:
        logger.debug("False alarm, rename completed successfully.")
        return True
    if tries <= 2:
        logger.debug("Likely a real error, exiting.")
        return False
    logger.debug("Likely false alarm, attempting rename again")
    return True


def retry(tries, xnat, project, current, new):
    try:
        if is_renamed(xnat, project, current, new):
            return True
    except datman.xnat.XnatException:
        logger.debug("Partial rename occurred, using new name to "
                     "search for data to finish update")
        current = new

    logger.debug("Full rename failed, {} tries remaining".format(tries))
    if tries > 0:
        return rename_xnat_session(xnat, current, new, project,
                                   tries - 1)
    return False


def get_project(session):
    config = datman.config.config()
    try:
        project = config.map_xnat_archive_to_project(session)
    except Exception as e:
        raise type(e)("Can't find XNAT archive name for {}. "
                      "Reason - {}".format(session, e))
    return project


def is_renamed(xnat, xnat_project, old_name, new_name):
    """
    Sometimes XNAT renames only the subject or only the experiment when you
    tell it to rename both. Sometimes it says it failed when it succeeded.
    And sometimes it just fails completely for no observable reason (or
    because of a three year old failed autorun.xml pipeline). So... use this
    to check if the job is done before declaring it a failure.
    """
    try:
        session = xnat.get_session(xnat_project, new_name)
    except datman.xnat.XnatException:
        return False
    if session.name == new_name and session.experiment_label == new_name:
        return True
    try:
        session = xnat.get_session(xnat_project, old_name)
    except datman.xnat.XnatException as e:
        raise type(e)("Session {} partially renamed to {} for project "
                      "{}".format(old_name, new_name, xnat_project))
    return False


if __name__ == "__main__":
    main()
