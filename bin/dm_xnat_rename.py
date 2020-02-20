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

import datman.xnat
import datman.config
from datman.exceptions import XnatException

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


def rename_xnat_session(xnat, orig_name, new_name, project=None):
    """Rename a session on XNAT.

    Args:
        xnat (:obj:`datman.xnat.xnat`): A connection to the XNAT server.
        orig_name (:obj:`str`): The current session name on XNAT.
        new_name (:obj:`str`): The new name to apply to the session.
        project (:obj:`str`, optional): The XNAT project the session belongs
            to. If not given, it will be guessed based on orig_name. Defaults
            to None.

    Raises:
        XnatException: If problems internal to
            :obj:`datman.xnat.xnat.rename_session` occur.
        requests.HTTPError: If XNAT's API reports issues.

    Returns:
        bool: True if rename succeeded, False otherwise
    """
    if not project:
        project = get_project(orig_name)

    logger.info("Renaming {} to {} in project {}".format(orig_name, new_name,
                                                         project))

    try:
        xnat.rename_session(project, orig_name, new_name)
    except XnatException as e:
        if '0 experiment' in str(e):
            return True
        try:
            is_renamed(xnat, project, orig_name, new_name)
        except XnatException:
            # Try to fix partial rename
            session = xnat.get_session(project, new_name)
            xnat.rename_experiment(session, orig_name, new_name)

    return is_renamed(xnat, project, orig_name, new_name)


def get_project(session):
    config = datman.config.config()
    try:
        project = config.map_xnat_archive_to_project(session)
    except Exception as e:
        raise type(e)("Can't find XNAT archive name for {}. "
                      "Reason - {}".format(session, e))
    return project


def is_renamed(xnat, xnat_project, old_name, new_name):
    """Verifies that a session rename has succeeded.

    Sometimes XNAT renames only the subject or only the experiment when you
    tell it to rename both. Sometimes it says it failed when it succeeded.
    And sometimes it just fails completely for no observable reason. So... use
    this to check if the job is done before declaring it a failure.

    Args:
        xnat (:obj:`datman.xnat.xnat`): A connection to the XNAT server.
        xnat_project (:obj:`str`): The session's XNAT project name.
        old_name (:obj:`str`): The original name of the session on XNAT.
        new_name (:obj:`str`): The intended final name of the session on XNAT.

    Raises:
        XnatException: If the session was renamed but the experiment was not.

    Returns:
        bool. True if rename appears to have succeeded, False otherwise.
    """
    try:
        session = xnat.get_session(xnat_project, new_name)
    except XnatException:
        return False
    if session.name == new_name and session.experiment_label == new_name:
        return True
    try:
        session = xnat.get_session(xnat_project, old_name)
    except XnatException:
        raise XnatException("Session {} partially renamed to {} for project "
                            "{}".format(old_name, new_name, xnat_project))
    return False


if __name__ == "__main__":
    main()
