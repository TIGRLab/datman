#!/usr/bin/env python
"""
Usage:
    dm_task_files.py <study>

Arguments:
    <study>             A datman managed study name
"""

import os
import re
import glob
import logging

from docopt import docopt

import datman.config
import datman.utils
import datman.dashboard as dashboard

logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))


def main():
    args = docopt(__doc__)
    study = args['<study>']

    config = datman.config.config(study=study)
    subjects = datman.dashboard.get_study_subjects(study)
    resources_dir = config.get_path('resources')
    out_dir = config.get_path('task')
    regex = get_regex(config)

    try:
        os.mkdir(out_dir)
    except OSError:
        pass

    for subject in subjects:

        sessions = glob.glob(os.path.join(resources_dir, subject + '_*'))

        if not sessions:
            continue

        for resource_folder in sessions:
            task_files = get_task_files(regex, resource_folder)

            if not task_files:
                continue

            session = os.path.basename(resource_folder)
            dest_folder = os.path.join(out_dir, session)
            try:
                os.mkdir(dest_folder)
            except OSError:
                pass

            renamed_files = resolve_duplicate_names(task_files)

            for fname in renamed_files:
                dest_path = os.path.join(dest_folder, fname)
                link_task_file(renamed_files[fname], dest_path)
                add_to_dashboard(session, dest_path)


def get_regex(config):
    try:
        regex = config.get_key('TASK_REGEX')
    except datman.config.UndefinedSetting:
        logger.warn("'TASK_REGEX' not defined in settings, using default "
                    "regex to locate task files.")
        regex = 'behav|\.edat2'  # noqa: W605
    return regex


def get_task_files(regex, resource_folder, ignore='.pdf|tech'):
    task_files = []
    for path, subdir, files in os.walk(resource_folder):
        if re.search(regex, path, re.IGNORECASE):
            for item in files:
                if re.search(ignore, item, re.IGNORECASE):
                    # Skip items matching the 'ignore' string
                    continue
                task_files.append(os.path.join(path, item))
            # move on to avoid adding a duplicate entry if a file name
            # also matches the regex
            continue
        for item in files:
            if re.search(regex, item, re.IGNORECASE) and not re.search(
                                                            ignore,
                                                            item,
                                                            re.IGNORECASE):
                task_files.append(os.path.join(path, item))
    return task_files


def link_task_file(src_path, dest_path):
    src = datman.utils.get_relative_source(src_path, dest_path)
    try:
        os.symlink(src, dest_path)
    except OSError as e:
        if e.errno == 13:
            logger.error("Can't symlink task file {} to {} - Permission"
                         " denied.".format(src, dest_path))
        elif e.errno == 17:
            pass
        else:
            raise e


def resolve_duplicate_names(task_files):
    all_fnames = sort_fnames(task_files)
    resolved_names = {}
    for unique_name in all_fnames:
        file_paths = all_fnames[unique_name]

        if len(file_paths) == 1:
            resolved_names[unique_name] = file_paths[0]
            continue

        common_prefix = os.path.commonprefix(file_paths)
        for item in file_paths:
            new_name = morph_name(item, common_prefix)
            resolved_names[new_name] = item

    return resolved_names


def sort_fnames(file_list):
    all_fnames = {}
    for item in file_list:
        name = os.path.basename(item)
        all_fnames.setdefault(name, []).append(item)
    return all_fnames


def morph_name(file_path, common_prefix):
    """
    Returns a unique name by finding the unique part of a file's path and
    combining it into a hyphen separated file name
    """
    unique_part = file_path.replace(common_prefix, '')
    dir_levels = unique_part.count('/')
    if dir_levels == 0:
        new_name = unique_part
    else:
        # Common prefix may have split a directory name, so derive the new name
        # from the original path instead to ensure full names are used
        new_name = "-".join(file_path.split('/')[-(dir_levels + 1):])
    return new_name


def add_to_dashboard(session, task_file):
    if not dashboard.dash_found:
        return

    db_session = dashboard.get_session(session)
    if not db_session:
        logger.info("{} not yet in dashboard database. Cannot add task file "
                    "{}".format(session, task_file))
        return

    task = db_session.add_task(task_file)
    if not task:
        logger.error("Failed to add task file {} to dashboard "
                     "database".format(task_file))
    return


if __name__ == '__main__':
    main()
