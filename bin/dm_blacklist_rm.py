#!/usr/bin/env python
"""
Searches the file system for any outputs created from a series on the blacklist
and deletes them. WARNING: This will not remove lines from output CSVs
that apply to blacklisted subjects. It is not a replacement for making sure that
pipeline scripts respect the blacklist!

Usage:
    dm_blacklist_rm.py [options] [--ignore-path=KEY]... <project>
    dm_blacklist_rm.py [options] [--ignore-path=KEY]... <project> <series>

Arguments:
    <project>           The name of a datman managed project
    <series>            The name of a series that belongs to <project>. Should
                        be in the format of a blacklist entry series, i.e. no
                        extension or preceding path.

Options:
    --blacklist FILE    The path to the blacklist file to use. Overrides the
                        default metadata/blacklist.csv for this project. The
                        blacklist will not be read if the series argument is
                        given.
    --ignore-path KEY   A value from the configuration file 'path' field to
                        not search through. [default: qc meta]
    -v --verbose
    -d --debug
    -q --quiet
    -n --dry-run

"""
import os
import re
import sys
import logging

import datman.config
import datman.utils
from datman.docopt import docopt

logging.basicConfig(level=logging.WARN,
        format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

DRYRUN = False

def main():
    global DRYRUN
    arguments = docopt(__doc__)
    project = arguments['<project>']
    series = arguments['<series>']
    blacklist = arguments['--blacklist']
    ignored_paths = arguments['--ignore-path']
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    quiet = arguments['--quiet']
    DRYRUN = arguments['--dry-run']

    if verbose:
        logger.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)
    if quiet:
        logger.setLevel(logging.ERROR)

    config = datman.config.config(study=project)

    blacklist = get_blacklist(arguments['--blacklist'], series, config)
    logger.debug("Found blacklist data: {}".format(blacklist))

    remove_blacklisted_items(blacklist, config, ignored_paths)

def get_blacklist(blacklist_file, series, config):
    if series:
        return [series]

    if blacklist_file is None:
        blacklist_file = os.path.join(config.get_path('meta'), 'blacklist.csv')

    if not os.path.exists(blacklist_file):
        logger.error("Blacklist {} does not exist. " \
                "Exiting.".format(blacklist_file))
        sys.exit(1)

    logger.debug("Reading blacklist file {}".format(blacklist_file))
    blacklist = []
    with open(blacklist_file, 'r') as blacklist_data:
        for line in blacklist_data:
            series = get_series(line)
            if not series:
                continue
            blacklist.append(series)

    return blacklist

def get_series(line):
    regex = ',|\s'
    fields = re.split(regex, line)
    if not fields or fields[0] == 'series':
        return ''
    return fields[0]

def remove_blacklisted_items(blacklist, config, ignored_paths):
    found_items = collect_blacklisted_items(blacklist, config, ignored_paths)

    for item in found_items:
        remove_item(item)
        remove_parent_dir_if_empty(item)

def collect_blacklisted_items(blacklist, config, ignored_paths):
    search_paths = get_search_paths(config, ignored_paths)

    file_list = []
    for path in search_paths:
        full_path = config.get_path(path)
        if not os.path.exists(full_path):
            continue
        for item in blacklist:
            found_files = find_files(full_path, item)
            if found_files:
                file_list.extend(found_files)
    return file_list

def get_search_paths(config, ignored_paths):
    paths = config.get_key('paths')
    try:
        path_keys = paths.keys()
    except AttributeError:
        logger.info("No paths set for {}".format(config.study_name))
        return []
    search_paths = [path for path in path_keys if path not in ignored_paths]
    return search_paths

def find_files(search_path, item):
    command = 'find {} -name \"{}*\"'.format(search_path, item)
    return_code, out = datman.utils.run(command)

    if not out:
        return []
    found_files = out.strip().split('\n')
    return found_files

def remove_item(item):
    logger.info('Removing blacklisted item {}'.format(item))
    try:
        if DRYRUN:
            return
        os.remove(item)
    except OSError:
        logger.error("Cannot remove file {}".format(item))

def remove_parent_dir_if_empty(item):
    parent_dir = os.path.dirname(item)
    if not os.listdir(parent_dir):
        logger.debug('Removing empty directory {}'.format(parent_dir))
        if DRYRUN:
            return
        os.rmdir(parent_dir)

if __name__ == "__main__":
    main()
