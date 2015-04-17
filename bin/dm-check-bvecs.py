#!/usr/bin/env python
"""
dm-compare-dirs.py <experiment-directory> <gold-directory>

For each subject, ensures the dicom data's headers in the xnat database
are similar to those in the supplied gold-standard folder.

logs in <data_path>/logs/goldstd.
"""

import datman as dm
import numpy as np
from subprocess import Popen, PIPE
import os, sys
import glob
import datetime
import logging

def diff_files(sub, nii_path, gold_path, log_path):
    """
    Diffs .bvec and .bvals.
    """
    # make a kewl log
    date = datetime.date.today()
    log = '{log_path}/{strfdate}.log'.format(log_path=log_path,
                                             strfdate=date.strftime('%y%m%d'))
    logging.basicConfig(filename=log,level=logging.DEBUG)
      
    # get list of .bvecs
    bvecs = glob.glob(os.path.join(nii_path, sub) + '/*.bvec')
    for b in bvecs:
        tag = dm.scanid.parse_filename(os.path.basename(b))[1]
        test = glob.glob(os.path.join(gold_path, tag) + '/*.bvec')
        if len(test) > 1:
            print('ERROR: more than one gold standard BVEC file!')
            raise ValueError
        if len(test) == 0:
            continue
        else:
            p = Popen(['diff', b, test[0]], stdout=PIPE, stderr=PIPE)
            out, err = p.communicate()
        if len(out) > 0:
            print(os.path.basename(b) + ': TAG = ' + tag + ' BVEC DIFF.')
            logging.warning(os.path.basename(b) + ': TAG = ' + tag + ', BVEC DIFF:')
            logging.warning(out)

    # get a list of .bvals
    bvals = glob.glob(os.path.join(nii_path, sub) + '/*.bval') 
    for b in bvals:
        tag = dm.scanid.parse_filename(os.path.basename(b))[1]
        test = glob.glob(os.path.join(gold_path, tag) + '/*.bval')
        if len(test) > 1:
            print('ERROR: more than one gold standard BVAL file!')
            raise ValueError
        if len(test) == 0:
            continue
        else:
            p = Popen(['diff', b, test[0]], stdout=PIPE, stderr=PIPE)
            out, err = p.communicate()
        if len(out) > 0:
            print(os.path.basename(b) + ': TAG = ' + tag + ', BVAL DIFF.')
            logging.warning(os.path.basename(b) + ': TAG = ' + tag + ', BVAL DIFF:')
            logging.warning(out)

def main(base_path, gold_path):
    """
    Iterates through subjects, finds DTI data, and compares with gold-stds.
    """
    # sets up paths
    data_path = dm.utils.define_folder(os.path.join(base_path, 'data'))
    nii_path = dm.utils.define_folder(os.path.join(data_path, 'nii'))
    _ = dm.utils.define_folder(os.path.join(data_path, 'logs'))
    log_path = dm.utils.define_folder(os.path.join(data_path, 'logs/goldstd'))

    subjects = dm.utils.get_subjects(nii_path)

    # loop through subjects
    for sub in subjects:
        if dm.scanid.is_phantom(sub) == True: continue
        try:
            # pre-process the data
            diff_files(sub, nii_path, gold_path, log_path)

        except ValueError as ve:
            print('ERROR: ' + str(sub) + ' !!!')

if __name__ == '__main__':
    if len(sys.argv) == 3:
        main(sys.argv[1], sys.argv[2])
    else:
        print(__doc__)

