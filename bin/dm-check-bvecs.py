#!/usr/bin/env python
"""
Checks that DTI bvec and bvals match the gold standards. 

Usage:
    dm-check-bvecs.py [options] <standards/> <logdir/> <examsdir/>

Arguments: 
    <standards/>            Folder with subfolders named by tag. Each subfolder
                            has a sample gold standard dicom file for that tag.

    <logdir/>               Folder to contain the outputs (specific errors found)
                            of this script. A log file is created in this
                            folder for each exam, named: dm-check-headers-<examdir>.log

    <examsdir/>             Folder with subfolder for each exam to check. Each
                            exam directory should have export nifti series,
                            some of which have corresponding .bvec/.bval files

Options: 
    --filter TEXT           A string to filter exams by (ex. site name). All
                            exam folders found in <examsdir/> must have this
                            text in their name.
    --verbose               Print mismatches to stdout as well as the log file
"""

from docopt import docopt
import datman as dm
import difflib
import glob
import logging as log
import os
import pprint
import re
import sys

def diff_files(examdir, standardsdir):
     
    diffs = {}  # map from file to diff against gold standard
    for ext in ['bvec','bval']:
        for test in glob.glob(examdir+'/*.'+ext):
            tag = dm.scanid.parse_filename(os.path.basename(test))[1]
            gold = glob.glob("{}/{}/*.{}".format(standardsdir, tag, ext))
            
            if len(gold) > 1:
                log.error('More than one gold standard .{} file for tag {}'.format(ext, tag))
                continue
            
            if len(gold) == 0:
                log.error('No gold standard .{} file for tag {}'.format(ext, tag))
                continue

            diff = difflib.ndiff(open(test).readlines(), open(gold[0]).readlines())
            changes = [l for l in diff if l.startswith('+ ') or l.startswith('- ')]

            if changes: 
                diffs[test] = ''.join(changes)

    return diffs 

def main():
    arguments = docopt(__doc__)
    standardsdir = arguments['<standards/>']
    logsdir = arguments['<logdir/>']
    examsdir = arguments['<examsdir/>']
    filtertext = arguments['--filter']
    verbose = arguments['--verbose']

    log.basicConfig(
        level=log.WARN, format="[dm-check-bvec] %(levelname)s: %(message)s")

    if verbose:
        log.getLogger('').setLevel(log.INFO)

    if not os.path.isdir(logsdir):
        log.error('Log directory {} does not exist'.format(logsdir))
        sys.exit(1)
    if not os.path.isdir(standardsdir):
        log.error('Standards directory {} does not exist'.format(standardsdir))
        sys.exit(1)
    if not os.path.isdir(examsdir):
        log.error('Exams directory {} does not exist'.format(examsdir))
        sys.exit(1)

    globexpr = '*'
    if filtertext: 
        globexpr = '*{}*'.format(filtertext)

    for examdir in glob.glob('{}/{}/'.format(examsdir,globexpr)):
        if '_PHA_' in examdir:  # ignore phantoms
            continue

        diffs = diff_files(examdir, standardsdir)

        if not diffs: 
            continue

        logfile = os.path.join(logsdir, "dm-check-bvecs-{}.log".format(
            os.path.basename(os.path.normpath(examdir))))

        if not os.path.exists(logfile):  # display warning on first encounter
            log.warn('{} mismatches for exam {}'.format(len(diffs), examdir))

        fname = open(logfile, "w")

        for path, diff in diffs.iteritems():
            message = re.sub('^',path+": ", diff.strip(), flags=re.MULTILINE)
            log.info(message)
            fname.write(message + "\n")

if __name__ == '__main__':
    main()
