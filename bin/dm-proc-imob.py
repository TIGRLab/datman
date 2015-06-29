#!/usr/bin/env python
"""
This analyzes imitate observe behavioural data.It could be generalized
to analyze any rapid event-related design experiment fairly easily.

Usage:
    dm-proc-imob.py [options] <project> <scratch> <script> <assets>

Arguments: 
    <project>           Full path to the project directory containing data/.
    <scratch>           Full path to a scratch directory (for temporary files).
    <script>            Full path to an epitome-style script.
    <assets>            Full path to an assets folder containing EA-timing.csv, EA-vid-lengths.csv.

Options:
    -v,--verbose             Verbose logging
    --debug                  Debug logging

DETAILS

    1) Preprocesses MRI data.
    2) Parses the supplied e-prime file and returns an AFNI-compatible GLM file. 
    3) Runs the GLM analysis at the single-subject level.

    Each subject is run through this pipeline if the outputs do not already exist.

DEPENDENCIES

    + matlab
    + afni

This message is printed with the -h, --help flags.
"""

import os, sys
import copy
import numpy as np
import nibabel as nib
import StringIO as io
import matplotlib.pyplot as plt
import datman.spins as spn
import datman as dm

from docopt import docopt


def process_functional_data(sub, data_path, code_path):
    # copy functional data into epitome-compatible structure
    try:
        niftis = filter(lambda x: 'nii.gz' in x, 
                            os.listdir(os.path.join(data_path, 'nifti', sub)))
    except:
        print('No "nifti" folder found for ' + str(sub) + ', aborting!')
        raise ValueError

    # convert NIFTI names to lowercase
    #niftis = [item.lower() for item in niftis]

    # find T1s
    try:
        T1_data = filter(lambda x: 'T1' in x or 'MPRAGE' in x or 'FSPGR' in x, niftis)
        T1_data.sort()
        T1_data = T1_data[1]
    
    except:
        print('No T1s found for ' + str(sub) + ', aborting!')
        raise ValueError

    # find EA task
    try:
        IM_data = filter(lambda x: 'Imitation' in x or 'Imitate' in x, niftis)
        
        if len(IM_data) == 1:
            IM_data = IM_data[0]
        else:
            print('Found multiple IM data, using newest: {}'.format(str(len(IM_data))))
            IM_data = IM_data[-1]
            #raise ValueError

    except:
        print('No IMITATE data found for {}, aborting!'.format(sub))
        raise ValueError

    try:
        OB_data = filter(lambda x: 'Observation' in x or 'Observe' in x, niftis)
        
        if len(OB_data) == 1:
            OB_data = OB_data[0]
        else:
            print('Found multiple OB data, using newest: {}'.format(str(len(OB_data))))
            OB_data = OB_data[-1]

    except:
        print('No OBSERVE data found for {}, aborting!'.format(sub))
        raise ValueError

    # check if output already exists
    if os.path.isfile('{}/imob/{}_complete.log'.format(data_path, sub)) == True:
        print('Subject {} has already been pre-processed, skipping'.format(sub))
        raise ValueError

    # MKTMP! os.path.mktmp?

    # copy data into temporary epitome structure
    # cleanup!
    spn.utils.make_epitome_folders('/tmp/epitome', 2)
    os.system('cp {}/nifti/{}/{} /tmp/epitome/TEMP/SUBJ/T1/SESS01/RUN01/T1.nii.gz'.format(data_path, sub, T1_data))
    os.system('cp {}/nifti/{}/{} /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/RUN01/FUNC01.nii.gz'.format(data_path, sub, IM_data))
    os.system('cp {}/nifti/{}/{} /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/RUN01/FUNC02.nii.gz'.format(data_path, sub, OB_data))

    # run preprocessing pipeline (shared with EA)
    os.system('bash {}/ea-preproc-fsl.sh'.format(code_path))

    # copy outputs into data folder
    if os.path.isdir('{}/imob'.format(data_path)) == False:
        os.system('mkdir {}/imob'.format(data_path))

    os.system('cp /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/func_MNI-nonlin.EA.01.nii.gz {}/imob/{}_func_MNI-nonlin.im.01.nii.gz'.format(data_path, sub))
    os.system('cp /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/func_MNI-nonlin.EA.02.nii.gz {}/imob/{}_func_MNI-nonlin.ob.02.nii.gz'.format(data_path, sub))
    os.system('cp /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/anat_EPI_mask_MNI-nonlin.nii.gz {}/imob/{}_anat_EPI_mask_MNI.nii.gz'.format(data_path, sub))
    os.system('cp /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/reg_T1_to_TAL.nii.gz {}/imob/{}_reg_T1_to_MNI-lin.nii.gz'.format(data_path, sub))
    os.system('cp /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/reg_nlin_TAL.nii.gz {}/imob/{}_reg_nlin_MNI.nii.gz'.format(data_path, sub))
    os.system('cat /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/PARAMS/motion.EA.01.1D > {}/imob/{}_motion.1D'.format(data_path, sub))
    os.system('cat /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/PARAMS/motion.EA.02.1D >> {}/imob/{}_motion.1D'.format(data_path, sub))
    os.system('cp /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/qc_reg_EPI_to_T1.pdf {}/imob/{}_qc_reg_EPI_to_T1.pdf'.format(data_path, sub))
    os.system('cp /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/qc_reg_T1_to_MNI.pdf {}/imob/{}_qc_reg_T1_to_MNI.pdf'.format(data_path, sub))
    os.system('touch {}/imob/{}_complete.log')
    os.system('rm -r /tmp/epitome')

def generate_analysis_script(sub, data_path, code_path):
    """
    This writes the analysis script to replicate the methods in [insert paper 
    here]. It expects timing files to exist (these are static, and are generated 
    by 'imob-parse.py').

    Briefly, this is a standard rapid-event related design. We use 5 tent 
    functions to explain each event over a 15 second window (this is the 
    standard length of the HRF).

    """
    # first, determine input functional files
    niftis = filter(lambda x: 'nii.gz' in x and sub + '_func' in x, 
                    os.listdir(os.path.join(data_path, 'imob')))
    niftis.sort()

    input_data = ''

    for nifti in niftis:
        input_data = input_data + data_path + '/imob/' + nifti + ' '

    # open up the master script, write common variables
    f = open(data_path + '/imob/' + sub + '_glm_1stlevel_cmd.sh', 'wb')
    f.write("""#!/bin/bash

# Imitate GLM for {sub}.
3dDeconvolve \\
    -input {input_data} \\
    -mask {data_path}/imob/{sub}_anat_EPI_mask_MNI.nii.gz \\
    -ortvec {data_path}/imob/{sub}_motion.1D motion_paramaters \\
    -polort 4 \\
    -num_stimts 12 \\
    -local_times \\
    -jobs 8 \\
    -x1D {data_path}/imob/{sub}_glm_1stlevel_design.mat \\
    -stim_times 1 {data_path}/imob/IM_event-times_AN.1D \'TENT(0,15,5)\' \\
    -stim_label 1 IM_AN \\
    -stim_times 2 {data_path}/imob/IM_event-times_FE.1D \'TENT(0,15,5)\' \\
    -stim_label 2 IM_FE \\
    -stim_times 3 {data_path}/imob/IM_event-times_FX.1D \'TENT(0,15,5)\' \\
    -stim_label 3 IM_FX \\
    -stim_times 4 {data_path}/imob/IM_event-times_HA.1D \'TENT(0,15,5)\' \\
    -stim_label 4 IM_HA \\
    -stim_times 5 {data_path}/imob/IM_event-times_NE.1D \'TENT(0,15,5)\' \\
    -stim_label 5 IM_NE \\
    -stim_times 6 {data_path}/imob/IM_event-times_SA.1D \'TENT(0,15,5)\' \\
    -stim_label 6 IM_SA \\
    -stim_times 7 {data_path}/imob/OB_event-times_AN.1D \'TENT(0,15,5)\' \\
    -stim_label 7 OB_AN \\
    -stim_times 8 {data_path}/imob/OB_event-times_FE.1D \'TENT(0,15,5)\' \\
    -stim_label 8 OB_FE \\
    -stim_times 9 {data_path}/imob/OB_event-times_FX.1D \'TENT(0,15,5)\' \\
    -stim_label 9 OB_FX \\
    -stim_times 10 {data_path}/imob/OB_event-times_HA.1D \'TENT(0,15,5)\' \\
    -stim_label 10 OB_HA \\
    -stim_times 11 {data_path}/imob/OB_event-times_NE.1D \'TENT(0,15,5)\' \\
    -stim_label 11 OB_NE \\
    -stim_times 12 {data_path}/imob/OB_event-times_SA.1D \'TENT(0,15,5)\' \\
    -stim_label 12 OB_SA \\
    -fitts {data_path}/imob/{sub}_glm_1stlevel_explained.nii.gz \\
    -bucket {data_path}/imob/{sub}_glm_1stlevel.nii.gz \\
    -cbucket {data_path}/imob/{sub}_glm_1stlevel_coeffs.nii.gz \\
    -fout \\
    -tout \\
    -xjpeg {data_path}/imob/{sub}_glm_1stlevel_matrix.jpg
""".format(input_data=input_data,data_path=data_path,sub=sub))
    f.close()

def main(base_path, tmp_path, script):
    """
    Loops through subjects, preprocessing using the supplied script and running a
    first-level GLM using AFNI (tent functions, standard 15 s window) on all subjects.
    """

    global VERBOSE 
    global DEBUG
    arguments   = docopt(__doc__)
    base_path   = arguments['<project>']
    scratch     = arguments['<scratch>']
    script      = arguments['<script>']
    assets_path = arguments['<assets>']

    data_path = os.path.join(base_path, 'data')
    code_path = os.path.join(base_path, 'code')
    subjects = dm.utils.get_subjects(data_path)

    # loop through subjects
    for sub in subjects:
        if spn.utils.subject_type(sub) == 'phantom':
            continue
    
        # check if output already exists
        if os.path.isfile('{}/imob/{}_complete.log'.format(data_path, sub)) == True:
            continue
    
        try:
            process_functional_data(sub, data_path, code_path)
            generate_analysis_script(sub, data_path, code_path)
            os.system('bash {}/imob/{}_glm_1stlevel_cmd.sh'.format(data_path, sub))

        except ValueError as ve:
            pass

if __name__ == "__main__":
    main()
