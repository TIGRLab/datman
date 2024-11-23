#!/usr/bin/env python
"""
Searches the file system for any data on the blacklist and removes them
from subject data folders to avoid pipeline failures etc.

Usage:
    dm_blacklist_rm.py [options] [--path=KEY]... <project>

Arguments:
    <project>           The name of a datman managed project

Options:
    --keep              If provided, the blacklisted scans will be moved to
                        a 'blacklisted' subdir instead of being deleted.
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
import logging
import shutil

from docopt import docopt

import datman.config
import datman.scan
import datman.utils

logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

DRYRUN = False


def main():
    global DRYRUN
    arguments = docopt(__doc__)
    project = arguments['<project>']
    keep = arguments['--keep']
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
    search_paths = get_search_paths(config, override_paths)

    for sub in metadata:
        if not metadata[sub]:
            continue

        logger.debug(f"Working on {sub}")
        session = datman.scan.Scan(sub, config)
        handle_blacklisted_scans(
            session, metadata[sub], search_paths, keep=keep
        )


def get_search_paths(config, user_paths=None):
    """Get path types to search for blacklisted files in.

    Args:
        config (:obj:`datman.config.config`): A datman config object for the
            current study.
        user_paths (:obj:`list`): A list of path types to search through.
            Optional. Causes the configuration file setting to be ignored.

    Returns:
        list: A list of path types that will be searched.
    """
    if user_paths:
        path_keys = user_paths
    else:
        try:
            path_keys = config.get_key("BlacklistDel")
        except datman.config.UndefinedSetting:
            # Fall back to the default
            path_keys = ['nii', 'mnc', 'nrrd', 'resources']
    return path_keys


def handle_blacklisted_scans(session, bl_scans, search_paths, keep=False):
    """Move or delete all blacklisted scans for the given path types.

    Args:
        session (:obj:`datman.scan.Scan`): A datman scan object for the
            current session.
        bl_scans (:obj:`list`): A list of strings each representing a
            blacklisted scan.
        search_paths (:obj:`list`): A list of path types to move/delete
            blacklisted scans from. Each path type must exist in the
            datman config files.
        keep (bool): Whether to move files instead of deleting them. Optional,
            default False.
    """
    for scan in bl_scans:
        for path_type in search_paths:
            found = session.find_files(scan, format=path_type)

            if not found:
                continue

            logger.debug(f"Files found for removal: {found}")

            if DRYRUN:
                logger.info("DRYRUN - Leaving files in place.")
                continue

            for item in found:
                if keep:
                    path = getattr(session, f"{path_type}_path")
                    logger.info(
                        f"Moving blacklisted files to {path}/blacklisted"
                    )
                    move_file(path, item)
                else:
                    delete_file(item)


def move_file(path, item):
    """Move a file to a 'blacklisted' subdir inside the given path.

    Args:
        path (:obj:`str`): The path to move put the 'blacklisted' folder.
        item (:obj:`str`): The full path to a blacklisted file to move.
    """
    bl_dir = os.path.join(path, "blacklisted")
    try:
        os.mkdir(bl_dir)
    except FileExistsError:
        pass

    try:
        shutil.move(item, bl_dir)
    except shutil.Error as e:
        logger.error(f"Failed to move blacklisted file {item} - {e}")


def delete_file(file_path):
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass
    except (PermissionError, IsADirectoryError):
        logger.error(f"Failed to delete blacklisted item {file_path}.")


if __name__ == "__main__":
    main()
