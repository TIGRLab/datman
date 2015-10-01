#!/usr/bin/env python
"""
This converts some files from the freesurfer outputs into nifty for epitome scripts to use.

Usage:
    dm-freesurfer-sink.py [options] <subjectsdir> <t1directory>

Arguments:
    <subjectsdir>            The freesurfer SUBJECTS_DIR (output directory)
    <t1directory>            Output directory for converted files

Options:
    -v,--verbose             Verbose logging
    --debug                  Debug logging
    -n,--dry-run             Dry run


This converts some files from the freesurfer outputs into nifty for epitome scripts to use.

Requires AFNI and Freesurfer modules loaded.

freesurfer outputs are expected to be in <subjectsdir>
The converted files go into <t1directory>/data/t1

"""
from docopt import docopt
import os, sys
import copy
from random import choice
from glob import glob
from string import ascii_uppercase, digits
import numpy as np
import datman as dm

def export_data(sub, fs_path, t1_path):
    """
    Copies the deskulled T1 and masks to the t1/ directory.
    """
    cmd = 'mri_convert -it mgz -ot nii \
           {fs_path}/{sub}/mri/brain.mgz \
           {t1_path}/{sub}_T1_TMP.nii.gz'.format(
                                               fs_path=fs_path,
                                               t1_path=t1_path,
                                               sub=sub)
    dm.utils.run(cmd)

    cmd = '3daxialize \
           -prefix {t1_path}/{sub}_T1.nii.gz \
           -axial {t1_path}/{sub}_T1_TMP.nii.gz'.format(
                                                  t1_path=t1_path,
                                                  sub=sub)
    dm.utils.run(cmd)

    cmd = 'mri_convert -it mgz -ot nii \
           {fs_path}/{sub}/mri/aparc+aseg.mgz \
           {t1_path}/{sub}_APARC_TMP.nii.gz'.format(
                                                  fs_path=fs_path,
                                                  t1_path=t1_path,
                                                  sub=sub)
    dm.utils.run(cmd)

    cmd = '3daxialize \
           -prefix {t1_path}/{sub}_APARC.nii.gz \
           -axial {t1_path}/{sub}_APARC_TMP.nii.gz'.format(
                                                     t1_path=t1_path,
                                                     sub=sub)
    dm.utils.run(cmd)

    cmd = 'mri_convert -it mgz -ot nii \
           {fs_path}/{sub}/mri/aparc.a2009s+aseg.mgz \
           {t1_path}/{sub}_APARC2009_TMP.nii.gz'.format(
                                                      fs_path=fs_path,
                                                      t1_path=t1_path,
                                                      sub=sub)
    dm.utils.run(cmd)

    cmd = '3daxialize \
           -prefix {t1_path}/{sub}_APARC2009.nii.gz \
           -axial {t1_path}/{sub}_APARC2009_TMP.nii.gz'.format(
                                                         t1_path=t1_path,
                                                         sub=sub)
    dm.utils.run(cmd)

    cmd = 'rm {t1_path}/{sub}*_TMP.nii.gz'.format(
                                                t1_path=t1_path,
                                                sub=sub)
    dm.utils.run(cmd)

def main():
    """
    Essentially, sets up t1 dir for epitomeness brainz. :D
    """
    global VERBOSE
    global DRYRUN
    global DEBUG
    arguments    = docopt(__doc__)
    fs_path      = arguments['<subjectsdir>']
    t1_path      = arguments['<t1directory>']
    VERBOSE      = arguments['--verbose']
    DEBUG        = arguments['--debug']
    DRYRUN       = arguments['--dry-run']

    # sets up relative paths
    fs_path = os.path.normpath(fs_path)
    t1_path = dm.utils.define_folder(os.path.normpath(t1_path))

    # configure the freesurfer environment
    os.environ['SUBJECTS_DIR'] = fs_path

    list_of_names = []
    subjects = dm.utils.get_subjects(fs_path)

    # copy anatomicals, masks to t1 folder
    for sub in subjects:
        if dm.scanid.is_phantom(sub) == True: continue

        if os.path.isfile(os.path.join(t1_path, sub + '_T1.nii.gz')) == False:
            export_data(sub, fs_path, t1_path)

if __name__ == '__main__':
    main()
