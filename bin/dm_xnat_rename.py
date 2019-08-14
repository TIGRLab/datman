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
                    "previous_name,new_name", one entry per line.

Options:
    --server, -s    The URL of the xnat server to rename a session on. If unset,
                    it will be read from the 'XNATSERVER' environment var
    --user, -u      The username to log in with. If unset, it will be read from
                    the 'XNAT_USER' environment var.
    --pass, -p      The password to log in with. If unset it will be read from
                    the 'XNAT_PASS' environment var.
"""

from requests import HTTPError
from docopt import docopt

import datman.xnat
import datman.config

def main():
    arguments = docopt(__doc__)
    name_path = arguments['<name_file>']
    source = arguments['<prev_name>']
    dest = arguments['<new_name>']
    server = arguments['--server']
    user = arguments['--user']
    password = arguments['--pass']

    xnat = get_xnat(server, user, password)

    if not name_path:
        rename_xnat_session(xnat, source, dest)
        return

    names = read_sessions(name_path)
    config = datman.config.config()
    for entry in names:
        rename_xnat_session(xnat, names[0], names[1], config)

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
            print("Invalid entry found: {}. Ignoring".format(entry))
            continue
        entries.append([field.strip() for field in fields])
    return entries

def rename_xnat_session(xnat, current, new, config=None):
    """
    Returns True if rename is successful
    """
    if not config:
        config = datman.config.config()
    try:
        project = config.map_xnat_archive_to_project(current)
    except Exception as e:
        print("Can't find XNAT archive name for {}. Reason - {}".format(
                current, e))
        return False
    try:
        xnat.rename_session(project, current, new)
    except HTTPError as e:
        if e.response.status_code != 422:
            raise e
        # XNAT may say rename failed when it didnt because of 'autorun.xml'
        # pipeline getting stuck. Check if failure is real before reporting
        try:
            session = xnat.get_session(study, new)
        except:
            print("Can't verify name change from {} to {}. Probable "
                    "failure.".format(current, new))
            return False
        if session.name != new or session.experiment_label != new:
            raise e

    return True

if __name__ == "__main__":
    main()
