#!/usr/bin/env python
"""
freesurfer.py <experiment-directory>

This runs freesurfer on the input T1 data.

Requires AFNI and Freesurfer modules loaded.

outputs are placed in <experiment-directory>/data/freesurfer
logs in data_path/logs/freesurfer.
"""

import os, sys
import copy
from random import choice
from glob import glob
from string import ascii_uppercase, digits
import numpy as np
import nibabel as nib
import StringIO as io
import matplotlib.pyplot as plt
import datman as dm

def proc_data(sub, data_path):
    # copy functional data into epitome-compatible structure
    try:
        niftis = filter(lambda x: 'nii.gz' in x, 
                            os.listdir(os.path.join(data_path, 'nii', sub)))
    except:
        print('ERROR: No "nii" folder found for ' + str(sub))
        raise ValueError

    try:
        t1_data = filter(lambda x: 't1' in x.lower(), niftis)
        t1_data.sort()
    
    except:
        print('ERROR: No T1s found for ' + str(sub))
        raise ValueError

    # generate the freesurfer command (using all available T1s)
    inputs = ''
    for t1 in t1_data:
        inputs = inputs + ' -i ' + os.path.join(data_path, 'nii', sub, t1)

    cmd = 'recon-all -all -notal-check -cw256 -subjid ' +  sub
    cmd = cmd + inputs + ' -qcache'

    # submit to queue
    uid = ''.join(choice(ascii_uppercase + digits) for _ in range(6))
    name = 'datman_fs_{sub}_{uid}'.format(sub=sub, uid=uid)
    log = os.path.join(data_path, 'logs/freesurfer')
    cmd = """echo {cmd} | qsub -o {log} -S /bin/bash -V -q main.q -cwd \
             -N {name} -l mem_free=6G,virtual_free=6G -j y \
          """.format(cmd=cmd, log=log, name=name)
    dm.utils.run(cmd)

    return name

def run_dummy_q(list_of_names):
    """
    This holds the script until all of the queued freesurfer items are done.
    """
    print('Holding for remaining freesurfer processes.')
    cmd = ('echo sleep 30 | qsub -sync y -q main.q '   
                              + '-hold_jid ' + ",".join(list_of_names))
    dm.utils.run(cmd)
    print('... Done.')

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
    for sub in subjects:

        if dm.scanid.is_phantom(sub) == True: continue
        if os.path.isdir(os.path.join(fs_path, sub)) == True: continue

        try:
            # run through freesurfer
            name = proc_data(sub, data_path)
            list_of_names.append(name)

        except ValueError as ve:
            print('ERROR: ' + str(sub) + ' !!!')

    # wait for fresurfer to complete
    dm.utils.run_dummy_q(list_of_names)

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
