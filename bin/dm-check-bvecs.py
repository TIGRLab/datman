#!/usr/bin/env python
"""
For each subject, ensures the dicom data's headers in the xnat database
are similar to those in the supplied gold-standard folder.

Usage:
    dm-check-bvecs.py [options] <standards> <logs> <blacklist> <exam>...

Arguments: 
    <standards/>            Folder with subfolders named by tag. Each subfolder
                            has a sample gold standard dicom file for that tag.

    <logs/>                 Folder to contain the outputs (specific errors found)
                            of this script.

    <blacklist>             YAML file for recording ignored / processed series.

    <exam/>                 Folder with one dicom file sample from each series
                            to check

Options: 
    --verbose               Print warnings

DETAILS
    
    Outputs a mismatch warning per subject to STDOUT.
    Outputs the full diff of the mismatche to logs/subjectname.log
    Records analyzed subjects to the blacklist (so these warnings are not continually produced).

"""

import datman as dm
from docopt import docopt
import numpy as np
from subprocess import Popen, PIPE
import os, sys
import glob
import datetime

def diff_files(examdir, standardsdir, logsdir, blacklist):

    date = datetime.date.today()
    logfile = os.path.join(logsdir, os.path.basename(examdir)) + '.log'
    
    errors = 0
      
    # get list of .bvecs
    bvecs = glob.glob('{}/*.bvec'.format(examdir))
    for b in bvecs:
        tag = dm.scanid.parse_filename(os.path.basename(b))[1]
        test = glob.glob(os.path.join(standardsdir, tag) + '/*.bvec')
        
        if len(test) > 1:
            print('ERROR: [dm-check-bvecs] more than one goldSTD BVEC file for TAG = {}.'.format(tag))
            sys.exit()
        
        if len(test) == 0:
            print('ERROR: [dm-check-bvecs] No goldSTD BVEC found for TAG = {}.'.format(tag))
            sys.exit()
        else:
            p = Popen(['diff', b, test[0]], stdout=PIPE, stderr=PIPE)
            out, err = p.communicate()
       
        if len(out) > 0:
            with open(logfile, "a") as fname:
                fname.write('{} : TAG = {} BVEC DIFF:\n{}\n'.format(b, tag, out))
            errors = errors + 1

    # get a list of .bvals
    bvals = glob.glob('{}/*.bval'.format(examdir)) 
    for b in bvals:
        tag = dm.scanid.parse_filename(os.path.basename(b))[1]
        test = glob.glob(os.path.join(standardsdir, tag) + '/*.bval')
        
        if len(test) > 1:
            print('ERROR: [dm-check-bvecs] more than one gold standard BVAL file for TAG = {}'.format(tag))
            sys.exit()

        if len(test) == 0:
            print('ERROR: [dm-check-bvecs] No goldSTD BVAL found for TAG = {}.'.format(tag))
            sys.exit()
        else:
            p = Popen(['diff', b, test[0]], stdout=PIPE, stderr=PIPE)
            out, err = p.communicate()
        
        if len(out) > 0:
            with open(logfile, "a") as fname:
                fname.write('{} : TAG = {} BVAL DIFF:\n{}\n'.format(b, tag, out))
            errors = errors + 1

    return errors

def main():
    global VERBOSE

    arguments    = docopt(__doc__)
    standardsdir = arguments['<standards>']
    logsdir      = arguments['<logs>']
    examdirs     = arguments['<exam>']
    blacklist    = arguments['<blacklist>']
    VERBOSE      = arguments['--verbose']

    logsdir = dm.utils.define_folder(logsdir)

    # check inputs
    if os.path.isdir(logsdir) == False:
        print('ERROR: [dm-check-bvecs] Log directory {} does not exist'.format(logsdir))
        sys.exit()
    if os.path.isdir(standardsdir) == False:
        print('ERROR: [dm-check-bvecs] Standards directory {} does not exist'.format(standardsdir))
        sys.exit()

    dm.yamltools.touch_blacklist_stage(blacklist, 'dm-check-bvecs')

    # remove phantoms from examdirs
    examdirs = filter(lambda x: '_PHA_' not in x, examdirs)
    try:
        ignored_series = dm.yamltools.list_series(blacklist, 'dm-check-bvecs')
    except:
        ignored_series = []

    for examdir in examdirs:
        if os.path.basename(examdir) in ignored_series:
            continue
        errors = diff_files(examdir, standardsdir, logsdir, blacklist)
        dm.yamltools.blacklist_series(blacklist, 'dm-check-bvecs', os.path.basename(examdir), 'done')

        if errors > 0:
            print('ERROR: [dm-check-bvecs] {} BVEC/BVAL mismatches for {}'.format(errors, os.path.basename(examdir)))

if __name__ == '__main__':
    main()
