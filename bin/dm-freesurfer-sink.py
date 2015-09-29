#!/usr/bin/env python
"""
dm-freesurfer-sink.py <experiment-directory>

This converts some files from the freesurfer outputs into nifty for epitome scripts to use.

Requires AFNI and Freesurfer modules loaded.

freesurfer outputs are expected to be in <experiment-directory>/data/freesurfer
The converted files go into <experiment-directory>/data/t1

"""

import os, sys
import copy
from random import choice
from glob import glob
from string import ascii_uppercase, digits
import numpy as np
import datman as dm

def export_data(sub, data_path):
    """
    Copies the deskulled T1 and masks to the t1/ directory.
    """
    cmd = 'mri_convert -it mgz -ot nii \
           {data_path}/freesurfer/{sub}/mri/brain.mgz \
           {data_path}/t1/{sub}_T1_TMP.nii.gz'.format(
                                               data_path=data_path,
                                               sub=sub)
    dm.utils.run(cmd)

    cmd = '3daxialize \
           -prefix {data_path}/t1/{sub}_T1.nii.gz \
           -axial {data_path}/t1/{sub}_T1_TMP.nii.gz'.format(
                                                  data_path=data_path,
                                                  sub=sub)
    dm.utils.run(cmd)

    cmd = 'mri_convert -it mgz -ot nii \
           {data_path}/freesurfer/{sub}/mri/aparc+aseg.mgz \
           {data_path}/t1/{sub}_APARC_TMP.nii.gz'.format(
                                                  data_path=data_path,
                                                  sub=sub)
    dm.utils.run(cmd)

    cmd = '3daxialize \
           -prefix {data_path}/t1/{sub}_APARC.nii.gz \
           -axial {data_path}/t1/{sub}_APARC_TMP.nii.gz'.format(
                                                     data_path=data_path,
                                                     sub=sub)
    dm.utils.run(cmd)

    cmd = 'mri_convert -it mgz -ot nii \
           {data_path}/freesurfer/{sub}/mri/aparc.a2009s+aseg.mgz \
           {data_path}/t1/{sub}_APARC2009_TMP.nii.gz'.format(
                                                      data_path=data_path,
                                                      sub=sub)
    dm.utils.run(cmd)

    cmd = '3daxialize \
           -prefix {data_path}/t1/{sub}_APARC2009.nii.gz \
           -axial {data_path}/t1/{sub}_APARC2009_TMP.nii.gz'.format(
                                                         data_path=data_path,
                                                         sub=sub)
    dm.utils.run(cmd)

    cmd = 'rm {data_path}/t1/{sub}*_TMP.nii.gz'.format(
                                                data_path=data_path,
                                                sub=sub)
    dm.utils.run(cmd)

def main(base_path):
    """
    Essentially, runs freesurfer on brainz. :D
    """
    # sets up relative paths
    data_path = dm.utils.define_folder(os.path.join(base_path, 'data'))
    nii_path = dm.utils.define_folder(os.path.join(data_path, 'nii'))
    t1_path = dm.utils.define_folder(os.path.join(data_path, 't1'))
    fs_path = dm.utils.define_folder(os.path.join(data_path, 'freesurfer'))
    _ = dm.utils.define_folder(os.path.join(base_path, 'logs'))
    log_path = dm.utils.define_folder(os.path.join(base_path, 'logs/freesurfer'))

    # configure the freesurfer environment
    os.environ['SUBJECTS_DIR'] = fs_path

    list_of_names = []
    subjects = dm.utils.get_subjects(nii_path)

    # copy anatomicals, masks to t1 folder
    for sub in subjects:
        if dm.scanid.is_phantom(sub) == True: continue

        if os.path.isfile(os.path.join(t1_path, sub + '_T1.nii.gz')) == False:
            export_data(sub, data_path)

if __name__ == "__main__":
    if len(sys.argv) == 2:
        main(sys.argv[1])
    else:
        print(__doc__)
