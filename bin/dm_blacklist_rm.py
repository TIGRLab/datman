#!/usr/bin/env python
"""
Searches the file system for any data on the blacklist and deletes them.

Usage:
    dm_blacklist_rm.py [options] [--path=KEY]... <project>

Arguments:
    <project>           The name of a datman managed project

Options:
    --path KEY          If provided overrides the 'BlacklistDel' setting
                        from the config files, which defines the directories
                        to delete blacklisted items from. 'KEY' may be the name
                        of any path defined in the main config file (e.g.
                        'nii'). This option can be repeated to include multiple
                        paths.
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
    override_paths = arguments['--path']
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
    base_paths = get_base_paths(config, override_paths)

    remove_blacklisted_items(metadata, base_paths)


def get_base_paths(config, user_paths):
    """Get the full path to each base directory to search for blacklisted data.
    """
    if user_paths:
        path_keys = user_paths
    else:
        try:
            path_keys = config.get_key("BlacklistDel")
        except datman.config.UndefinedSetting:
            # Fall back to the default
            path_keys = ['nii', 'mnc', 'nrrd', 'resources']

    base_paths = []
    for key in path_keys:
        try:
            found = config.get_path(key)
        except datman.config.UndefinedSetting:
            logger.warning(f"Given undefined path type - {key}. Ignoring.")
            continue

        if os.path.exists(found):
            base_paths.append(found)

    return base_paths


def remove_blacklisted_items(metadata, base_paths):
    for sub in metadata:
        blacklist_entries = metadata[sub]
        if not blacklist_entries:
            continue

        logger.debug(f"Working on {sub}")
        for path in base_paths:
            for sub_dir in glob.glob(os.path.join(path, sub + "*")):
                for entry in blacklist_entries:
                    remove_matches(sub_dir, entry)


def remove_matches(path, fname):
    matches = find_files(path, fname)
    if matches:
        logger.info(f"Files found for deletion: {matches}")
    if DRYRUN:
        return
    for item in matches:
        try:
            os.remove(item)
        except FileNotFoundError:
            pass
        except (PermissionError, IsADirectoryError):
            logger.error(f"Failed to delete blacklisted item {item}.")


def find_files(path, fname):
    return glob.glob(os.path.join(path, fname + "*"))


if __name__ == "__main__":
    main()
