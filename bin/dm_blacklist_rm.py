#!/usr/bin/env python
"""
Searches the file system for any data on the blacklist and deletes them.

WARNING: This is not a replacement for making sure that pipeline scripts
respect the blacklist! It will only clean the data folder.

Usage:
    dm_blacklist_rm.py [options] [--ignore-path=KEY]... <project>

Arguments:
    <project>           The name of a datman managed project

Options:
    -v --verbose
    -d --debug
    -q --quiet
    -n --dry-run

"""
import os
import glob
import logging

from docopt import docopt

import datman.config
import datman.scan
import datman.utils
from datman.scanid import ParseException

logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

DRYRUN = False


def main():
    global DRYRUN
    arguments = docopt(__doc__)
    project = arguments['<project>']
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
    metadata = datman.utils.get_subject_metadata(config, allow_partial=True)
    remove_blacklisted_items(metadata, config)


def remove_blacklisted_items(metadata, config):
    for sub in metadata:
        blacklist_entries = metadata[sub]
        if not blacklist_entries:
            continue
        try:
            scan = datman.scan.Scan(sub, config)
        except ParseException as e:
            logger.error("Couldn't retrieve session info for {}, ignoring. "
                         "Reason - {}".format(sub, e))
            continue
        logger.debug("Working on {}".format(sub))
        remove_blacklisted(scan, blacklist_entries)


def remove_blacklisted(scan, entries):
    for entry in entries:
        remove_matches(scan.nii_path, entry)
        remove_matches(scan.dcm_path, entry)
        remove_matches(scan.nrrd_path, entry)
        remove_matches(scan.mnc_path, entry)
        remove_matches(scan.resource_path, entry)


def remove_matches(path, fname):
    matches = find_files(path, fname)
    if matches:
        logger.info("Files found for deletion: {}".format(matches))
    if DRYRUN:
        return
    for item in matches:
        try:
            os.remove(item)
        except FileNotFoundError:
            pass
        except (PermissionError, IsADirectoryError):
            logger.error("Failed to delete blacklisted item {}.".format(item))


def find_files(path, fname):
    return glob.glob(os.path.join(path, fname + "*"))


if __name__ == "__main__":
    main()
