#!/usr/bin/env python
"""
Searches all studies for QC documents which haven't been signed off on. 

Usage: 
    dm-qc-todo.py [options]

Options:
    --no-older       Don't check for QC documents older than source data
    --show-newer     Show data files newer than QC doc

Expects to be run in the parent folder to all study folders. Looks for the file
checklist.csv in subfolders, and prints out any QC pdf from those that haven't
been signed off on.   
"""

import docopt
import glob
import os
import os.path
import re


def get_project_dirs(root, maxdepth=4):
    """
    Search for datman project directories below root. 

    A project directory is defined as a directory having data/ and metadata/
    folders. 

    Returns a list of absolute paths to project folders.
    """
    paths = []
    for dirpath, dirs, files in os.walk(root):
        if 'data' in dirs and 'metadata' in dirs:
            del dirs[:]  # don't descend
            paths.append(dirpath)
        depth = dirpath.count(os.path.sep) + 1
        if depth >= maxdepth:
            del dirs[:]
    return paths


def main():
    arguments = docopt.docopt(__doc__)

    for projectdir in get_project_dirs("."):
        checklist = os.path.join(projectdir, 'metadata', 'checklist.csv')
        if not os.path.exists(checklist):
            continue

        # map qc pdf to comments
        checklistdict = {d[0]: d[1:] for d in [l.strip().split()
                                               for l in open(checklist).readlines() if l.strip()]}

        # check whether data is newer than qc doc or
        # whether qc doc hasn't been signed off on
        for timepointdir in glob.glob(projectdir + '/data/nii/*'):
            if '_PHA_' in timepointdir:
                continue

            timepoint = os.path.basename(timepointdir)
            qcdocname = 'qc_' + timepoint + '.pdf'
            qcdoc = os.path.join(projectdir, 'qc', qcdocname)
            data_ctime = max(
                map(os.path.getctime, glob.glob(timepointdir + '/*')))

            if qcdocname not in checklistdict or not os.path.exists(qcdoc):
                print 'No QC doc generated for {}'.format(timepointdir)

            elif not arguments['--no-older'] and data_ctime > os.path.getctime(qcdoc):
                print '{}: QC doc is older than data in folder {}'.format(qcdoc, timepointdir)
                if arguments['--show-newer']:
                    newer = filter(lambda x: os.path.getctime(x) > os.path.getctime(qcdoc),
                                   glob.glob(timepointdir + '/*'))
                    print '\t' + '\n\t'.join(newer)

            elif not checklistdict[qcdocname]:
                print '{}: QC doc not signed off on'.format(qcdoc)

            else:  # qc doc signed off on
                pass

if __name__ == '__main__':
    main()
