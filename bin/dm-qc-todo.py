#!/usr/bin/env python
"""
Searches all studies for QC documents which haven't been signed off on.

Usage:
    dm-qc-todo.py [options]

Options:
    --show-newer     Show data files newer than QC doc
    --root PATH      Path to parent folder to all study folders.
                     [default: /archive/data-2.0]
    --study=<study>  Process a singe study

Expects to be run in the parent folder to all study folders. Looks for the file
checklist.csv in subfolders, and prints out any QC pdf from those that haven't
been signed off on.
"""

import docopt
import glob
import os
import os.path
import re
import datman.config as config

def read_checklist(checklist_file):
    checklist_dict = {}

    with open(checklist_file) as checklist:
        lines = checklist.readlines()

    for line in lines:
        entry = line.strip().split()
        try:
            key = os.path.splitext(entry[0])[0]
        except:
            # Empty line, skip it
            continue
        try:
            rest = entry[1:]
        except:
            entry = ''
        checklist_dict[key] = rest
    return checklist_dict

def get_project_dirs(root, maxdepth=2):
    """
    Search for datman project directories below root.

    A project directory is defined as a directory having a
    metadata/checklist.csv file.

    Returns a list of absolute paths to project folders.
    """
    paths = []
    for dirpath, dirs, files in os.walk(root):
        checklist = os.path.join(dirpath, 'metadata', 'checklist.csv')
        if os.path.exists(checklist):
            del dirs[:]  # don't descend
            paths.append(dirpath)
        depth = dirpath.count(os.path.sep) - root.count(os.path.sep)
        if depth >= maxdepth:
            del dirs[:]
    return paths

def get_mtime(path):
    """
    Returns the value of os.path.getmtime. If a broken link is found the link
    is removed and 0 returned.

    This function is needed because when the target of a link is blacklisted and
    removed the links to it are not cleaned up, and were causing os.path.getmtime
    to crash.
    """
    try:
        return os.path.getmtime(path)
    except OSError:
        if os.path.islink(path):
            print("Removing broken link {}".format(path))
            os.remove(path)
            return 0
        else:
            # Something went very wrong, reraise the OSError! :(
            raise

def main():
    arguments = docopt.docopt(__doc__)
    rootdir = arguments['--root']
    if arguments['--study']:
        cfg = config.config()
        rootdir = cfg.get_study_base(arguments['--study'])

    for projectdir in get_project_dirs(rootdir):
        checklist = os.path.join(projectdir, 'metadata', 'checklist.csv')

        checklistdict = read_checklist(checklist)

        for timepointdir in sorted(glob.glob(projectdir + '/data/nii/*')):
            if '_PHA_' in timepointdir:
                continue

            timepoint = os.path.basename(timepointdir)
            qcdocname = 'qc_' + timepoint
            qcdoc = os.path.join(projectdir, 'qc', timepoint, (qcdocname + '.html'))

            data_mtime = max(map(get_mtime, glob.glob(timepointdir + '/*.nii.gz')+[timepointdir]))

            # notify about missing QC reports or those with no checklist entry
            if qcdocname not in checklistdict:
                print('No checklist entry for {}'.format(timepointdir))
                continue
            elif not os.path.exists(qcdoc):
                print('No QC doc generated for {}'.format(timepointdir))
                continue

            # find QC documents that are older than the most recent data export
            if arguments['--show-newer'] and data_mtime > os.path.getmtime(qcdoc):
                newer = filter(lambda x: os.path.getmtime(x) > os.path.getmtime(qcdoc), glob.glob(timepointdir + '/*'))
                if newer != []:
                    print('{}: QC doc is older than data in folder {} {} {}'.format(qcdoc, timepointdir, data_mtime, os.path.getmtime(qcdoc)))
                    print('\t' + '\n\t'.join(newer))

            # notify about unchecked QC reports
            if not checklistdict[qcdocname]:
                print '{}: QC doc not signed off on'.format(qcdoc)

if __name__ == '__main__':
    main()
