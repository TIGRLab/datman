#!/usr/bin/env python
"""
Renames a session and its experiment.

Usage:
    dm_xnat_rename.py [options] <prev_name> <new_name>
    dm_xnat_rename.py [options] <name_file>

Arguments:
    <prev_name>     The current experiment name on XNAT
    <new_name>      The new experiment name
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
import datman.scanid
from datman.exceptions import XnatException, ParseException

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

    config = datman.config.config()
    xnat = datman.xnat.get_connection(
        config,
        url=server,
        auth=(user, password) if user and password else None)

    if not name_path:
        rename_xnat_session(xnat, source, dest, project=project)
        return

    names = read_sessions(name_path)
    for old_name, new_name in names:
        try:
            rename_xnat_session(xnat, old_name, new_name, project=project)
        except Exception as e:
            logger.error("Failed to rename {} to {}. Reason - "
                         "{}".format(old_name, new_name, e))


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

    try:
        ident = datman.scanid.parse(new_name)
    except ParseException:
        raise ParseException("New ID {} for experiment {} doesnt match a "
                             "supported naming convention.".format(
                                 new_name, orig_name))

    logger.info("Renaming {} to {} in project {}".format(orig_name, new_name,
                                                         project))

    orig_subject = xnat.find_subject(project, orig_name)
    try:
        xnat.rename_subject(project, orig_subject, ident.get_xnat_subject_id())
    except HTTPError as e:
        if e.response.status_code == 500:
            # This happens on success sometimes (usually when experiment
            # is empty). Check if the rename succeeded.
            try:
                xnat.get_subject(project, ident.get_xnat_subject_id())
            except XnatException:
                raise e

    xnat.rename_experiment(project, ident.get_xnat_subject_id(),
                           orig_name, ident.get_xnat_experiment_id())


def get_project(session):
    config = datman.config.config()
    try:
        project = config.map_xnat_archive_to_project(session)
    except ParseException as e:
        raise ParseException(
            "Can't guess the XNAT Archive for {}. Reason - {}. Please provide "
            "an XNAT Archive name with the --project option".format(
                session, e))
    except Exception as e:
        raise type(e)("Can't determine XNAT Archive for {}. Reason - {}"
                      "".format(session, e))
    return project


if __name__ == "__main__":
    main()
