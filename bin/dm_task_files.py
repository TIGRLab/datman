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
from datman.scan import Scan
import datman.dashboard as dashboard

logging.basicConfig(level=logging.WARN,
        format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

def main():
    args = docopt(__doc__)
    study = args['<study>']

    config = datman.config.config(study=study)
    subjects = datman.utils.get_subject_metadata(config)

    regex = config.get_key('task_regex')
    resources_dir = config.get_path('resources')
    out_dir = config.get_path('task')
    if not os.path.exists(out_dir):
        os.mkdir(out_dir)

    for subject in subjects:
        sessions = glob.glob(os.path.join(resources_dir, subject + '_*'))

        if not sessions:
            continue

        for resource_folder in sessions:
            task_files = get_task_files(regex, resource_folder)

            if not task_files:
                continue

            dest_folder = os.path.join(out_dir, subject)
            try:
                os.mkdir(dest_folder)
            except OSError:
                pass

            for item in task_files:
                dest = os.path.join(dest_folder, os.path.basename(item))
                src = datman.utils.get_relative_source(item, dest)
                try:
                    os.symlink(src, dest)
                except OSError as e:
                    if e.errno == 13:
                        logger.error("Can't symlink task file {} to {} - Permission"
                                " denied.".format(item, dest))
                    elif e.errno == 17:
                        continue
                    else:
                        raise e

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
            if re.search(regex, item, re.IGNORECASE) and not re.search(ignore,
                    item, re.IGNORECASE):
                task_files.append(os.path.join(path, item))
    return task_files

if __name__ == '__main__':
    main()
