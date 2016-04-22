#!/usr/bin/env python
"""
Searches all studies for QC documents which haven't been signed off on.

Usage:
    dm-qc-todo.py [options]

Options:
    --no-older       Don't check for QC documents older than source data
    --show-newer     Show data files newer than QC doc
    --root PATH      Path to parent folder to all study folders.
                     [default: /archive/data-2.0]

Expects to be run in the parent folder to all study folders. Looks for the file
checklist.csv in subfolders, and prints out any QC pdf from those that haven't
been signed off on.
"""

import docopt
import glob
import os
import os.path
import re

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


def main():
    arguments = docopt.docopt(__doc__)
    rootdir = arguments['--root']

    for projectdir in get_project_dirs(rootdir):
        checklist = os.path.join(projectdir, 'metadata', 'checklist.csv')

        # map qc pdf to comments
        checklistdict = {d[0]: d[1:] for d in [l.strip().split()
                                               for l in open(checklist).readlines() if l.strip()]}

        ## add .html for all .pdf keys
        for k in checklistdict.keys():
            if '.pdf' in k:
                checklistdict[k.replace('.pdf','.html')] = checklistdict[k]

        # check whether data is newer than qc doc or
        # whether qc doc hasn't been signed off on
        for timepointdir in sorted(glob.glob(projectdir + '/data/nii/*')):
            if '_PHA_' in timepointdir:
                continue

            timepoint = os.path.basename(timepointdir)
            qcdocname = 'qc_' + timepoint + '.html'
            qcdoc = os.path.join(projectdir, 'qc', timepoint, qcdocname)

            data_mtime = max(
                map(os.path.getmtime, glob.glob(timepointdir + '/*')+[timepointdir]))

            if qcdocname not in checklistdict or not os.path.exists(qcdoc):
                print 'No QC doc generated for {}'.format(timepointdir)

            elif not arguments['--no-older'] and data_mtime > os.path.getmtime(qcdoc):
                print '{}: QC doc is older than data in folder {} {} {}'.format(qcdoc, timepointdir, data_mtime, os.path.getmtime(qcdoc))
                if arguments['--show-newer']:
                    newer = filter(lambda x: os.path.getmtime(x) > os.path.getmtime(qcdoc),
                                   glob.glob(timepointdir + '/*'))
                    print '\t' + '\n\t'.join(newer)

            elif not checklistdict[qcdocname]:
                print '{}: QC doc not signed off on'.format(qcdoc)

            else:  # qc doc signed off on
                pass

if __name__ == '__main__':
    main()
