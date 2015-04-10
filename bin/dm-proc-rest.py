#!/usr/bin/env python
"""
rest.py <experiment-directory> <script>

Runs the defined epitome script on the resting-state data.

Requires AFNI, FSL, modules to be loaded.
Requires freesurfer.py to have been completed.

outputs are placed in <experiment-directory>/data/rest.
logs in data_path/logs/rest.
"""

import os, sys
import copy
import numpy as np
import nibabel as nib
import StringIO as io
import matplotlib.pyplot as plt
import datman as dm
import tempfile as tmp

def proc_data(sub, nii_path, t1_path, rest_path, tmp_path, script):
    """
    Copies functional data into epitome-compatible structure, then runs the
    associated epitome script on the data. Finally, we copy the outputs into
    the 'rest' directory.
    """
    
    # find the freesurfer outputs for the T1 data
    try:
        niftis = filter(lambda x: 'nii.gz' in x, os.listdir(t1_path))
        niftis = filter(lambda x: sub in x, niftis)
    except:
        print('ERROR: No "t1" folder/outputs found for ' + str(sub))
        raise ValueError

    try:
        t1_data = filter(lambda x: 't1' in x.lower(), niftis)
        t1_data.sort()
        t1_data = t1_data[0]
    
    except:
        print('ERROR: No t1 found for ' + str(sub))
        raise ValueError

    try:
        aparc = filter(lambda x: 'aparc.nii.gz' in x.lower(), niftis)
        aparc.sort()
        aparc = aparc[0]
    
    except:
        print('ERROR: No aparc atlas found for ' + str(sub))
        raise ValueError

    try:
        aparc2009 = filter(lambda x: 'aparc2009.nii.gz' in x.lower(), niftis)
        aparc2009.sort()
        aparc2009 = aparc2009[0]

    except:
        print('ERROR: No aparc 2009 atlas found for ' + str(sub))
        raise ValueError

    # find resting state data
    try:
        niftis = filter(lambda x: 'nii.gz' in x, os.listdir(os.path.join(
                                                            nii_path, sub)))
    except:
        print('ERROR: No "nifti" folder found for ' + str(sub) + ', aborting!')
        raise ValueError

    try:
        rest_data = filter(lambda x: 'rst' in x.lower(), niftis)
        
        if len(rest_data) > 1:
            print('*** Multiple resting-state data! Using most recent ' + sub) 

        rest_data = rest_data[-1]

    except:
        print('ERROR: No REST data found for ' + str(sub))
        raise ValueError

    # check if output already exists, abort if so
    if os.path.isfile(os.path.join(rest_path, sub + '_complete.log')) == True:
        return None

    # copy data into temporary epitome structure
    tmpfolder = tmp.mkdtemp(prefix='rest-', dir=tmp_path)
    tmpdict[sub] = tmpfolder

    dm.utils.make_epitome_folders(tmpfolder, 1)
    os.system('cp {t1_path}/{t1_data} {tmpfolder}/TEMP/SUBJ/T1/SESS01/anat_T1_brain.nii.gz'.format(t1_path=t1_path, t1_data=t1_data, tmpfolder=tmpfolder))
    os.system('cp {t1_path}/{aparc} {tmpfolder}/TEMP/SUBJ/T1/SESS01/anat_aparc_brain.nii.gz'.format(t1_path=t1_path, aparc=aparc, tmpfolder=tmpfolder))
    os.system('cp {t1_path}/{aparc2009} {tmpfolder}/TEMP/SUBJ/T1/SESS01/anat_aparc2009_brain.nii.gz'.format(t1_path=t1_path, aparc=aparc2009, tmpfolder=tmpfolder))
    os.system('cp {nii_path}/{sub}/{rest_data} {tmpfolder}/TEMP/SUBJ/FUNC/SESS01/RUN01/FUNC01.nii.gz'.format(nii_path=nii_path, sub=sub, rest_data=rest_data, tmpfolder=tmpfolder))

    # submit to queue
    cmd = 'bash ' + script + ' ' + tmpfolder
    name = 'datman_rest_{sub}_{uid}'.format(sub=sub, uid=uid)
    log = os.path.join(data_path, 'logs/rest')
    cmd = 'echo {cmd} | qsub -o {log} -S /bin/bash -V -q main.q -cwd -N {name} -l mem_free=3G,virtual_free=3G -j y'.format(cmd=cmd, log=log, name=name)
    os.system(cmd)

    return name, tmpdict

def export_data(sub, folder, rest_path):

    os.system('cp {folder}/TEMP/SUBJ/FUNC/SESS01/func_MNI-nonlin.REST.01.nii.gz {rest_path}/{sub}_func_MNI-nonlin.01.nii.gz'.format(folder=folder, rest_path=rest_path, sub=sub))
    os.system('cp {folder}/TEMP/SUBJ/FUNC/SESS01/anat_EPI_mask_MNI-nonlin.nii.gz {rest_path}/{sub}_anat_EPI_mask_MNI.nii.gz'.format(folder=folder, rest_path=rest_path, sub=sub))
    os.system('cp {folder}/TEMP/SUBJ/FUNC/SESS01/reg_T1_to_TAL.nii.gz {rest_path}/{sub}_reg_T1_to_MNI-lin.nii.gz'.format(folder=folder, rest_path=rest_path, sub=sub))
    os.system('cp {folder}/TEMP/SUBJ/FUNC/SESS01/reg_nlin_TAL.nii.gz {rest_path}/{sub}_reg_nlin_MNI.nii.gz'.format(folder=folder, rest_path=rest_path, sub=sub))
    os.system('cat {folder}/TEMP/SUBJ/FUNC/SESS01/PARAMS/motion.REST.01.1D > {rest_path}{sub}_motion.1D'.format(folder=folder, rest_path=rest_path, sub=sub))

    # TODO
    #
    # # copy out QC images of registration
    # os.system('cp {folder}/TEMP/SUBJ/FUNC/SESS01/'
    #                         + 'qc_reg_EPI_to_T1.pdf ' +
    #               data_path + '/rest/' + sub + '_qc_reg_EPI_to_T1.pdf')
    # os.system('cp {folder}/TEMP/SUBJ/FUNC/SESS01/'
    #                         + 'qc_reg_T1_to_MNI.pdf ' +
    #               data_path + '/rest/' + sub + '_qc_reg_T1_to_MNI.pdf')

    os.system('touch {rest_path}/{sub}_complete.log'.format(rest_path=rest_path, sub=sub))
    os.system('rm -r ' + folder)

def generate_analysis_script(sub, data_path, code_path):
    """
    This will eventually do some graph theory stuff. For now, it will lol.

    """
    # first, determine input functional files
    # niftis = filter(lambda x: 'nii.gz' in x and sub + '_func' in x, 
    #                 os.listdir(os.path.join(data_path, 'imob')))
    # niftis.sort()

    # input_data = ''

    # for nifti in niftis:
    #     input_data = input_data + data_path + '/imob/' + nifti + ' '

    print('lol')

def main(base_path, script):
    """
    Essentially, analyzes the resting-state data.

    1) Runs functional data through a defined epitome script.
    2) Extracts time series from the cortex using MRI-space ROIs.
    3) Generates a correlation matrix for each subject.
    4) Generates an experiment-wide correlation matrix.
    5) Generates a set of graph metrics for each subject. 
    """
    # sets up paths
    data_path = dm.utils.define_folder(os.path.join(base_path, 'data'))
    nii_path = dm.utils.define_folder(os.path.join(data_path, 'nii'))
    t1_path = dm.utils.define_folder(os.path.join(data_path, 't1'))
    rest_path = dm.utils.define_folder(os.path.join(data_path, 'rest'))
    tmp_path = dm.utils.define_folder(os.path.join(data_path, 'tmp'))
    _ = dm.utils.define_folder(os.path.join(data_path, 'logs'))
    _ = dm.utils.define_folder(os.path.join(data_path, 'logs/rest'))

    list_of_names = []
    tmpdict = {}
    subjects = spn.utils.get_subjects(data_path)

    # loop through subjects
    for sub in subjects:

        if dm.scanid.is_phantom(sub) == True: continue
        if os.path.isfile(os.path.join(
                          rest_path,  sub + '_complete.log')) == True:
            continue
    
        try:
            # pre-process the data
            name = proc_data(sub, nii_path, t1_path, rest_path, tmp_path, 
                                                                  script)

        except ValueError as ve:
            print('ERROR: ' + str(sub) + ' !!!')

    # wait for fresurfer to complete
    dm.utils.run_dummy_q(list_of_names)
    list_of_names.append(name)

    # copy functionals, registrations, motion parameters to rest folder.
    for sub in subjects:
        if dm.scanid.is_phantom(sub) == True: continue
        if os.path.isfile(os.path.join(
                          rest_path,  sub + '_complete.log')) == False:
            export_data(sub, tmpdict[sub], rest_path)

if __name__ == "__main__":
    if len(sys.argv) == 3:
        main(sys.argv[1], sys.argv[2])
    else:
        print(__doc__)