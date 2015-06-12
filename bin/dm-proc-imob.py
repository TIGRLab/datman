#!/usr/bin/env python
"""
This auto-grad student analyzes the imitate observe task for the 
SPINS grant:
1) Preprocesses MRI data.
2) Parses the supplied e-prime file and returns an AFNI-compatible GLM file. 
3) Runs the GLM analysis at the single-subject level.
"""

import os, sys
import copy
import numpy as np
import nibabel as nib
import StringIO as io
import matplotlib.pyplot as plt
import datman.spins as spn

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
        T1_data = filter(lambda x: 'T1' in x or 
                                   'MPRAGE' in x or 
                                   'FSPGR' in x, niftis)
        T1_data.sort()
        T1_data = T1_data[1]
    
    except:
        print('No T1s found for ' + str(sub) + ', aborting!')
        raise ValueError

    # find EA task
    try:
        IM_data = filter(lambda x: 'Imitation' in x or
                                   'Imitate' in x, niftis)
        
        if len(IM_data) == 1:
            IM_data = IM_data[0]
    
        else:
            print('Found multiple IM data, using newest' + str(len(IM_data)))
            IM_data = IM_data[-1]
            #raise ValueError

    except:
        print('No IMITATE data found for ' + str(sub) + ', aborting!')
        raise ValueError

    try:
        OB_data = filter(lambda x: 'Observation' in x or
                                   'Observe' in x, niftis)
        
        if len(OB_data) == 1:
            OB_data = OB_data[0]
    
        else:
            print('Found multiple OB data, using newest ' + str(len(OB_data)))
            OB_data = OB_data[-1]

    except:
        print('No OBSERVE data found for ' + str(sub) + ', aborting!')
        raise ValueError

    # check if output already exists
    if os.path.isfile(data_path + '/imob/' + sub + '_complete.log') == True:
        print('Subject ' + sub + ' has already been pre-processed, skipping')
        raise ValueError

    # MKTMP! os.path.mktmp?

    # copy data into temporary epitome structure
    # cleanup!
    spn.utils.make_epitome_folders('/tmp/epitome', 2)
    os.system('cp ' + data_path + '/nifti/' + sub + '/' + str(T1_data) + 
                  ' /tmp/epitome/TEMP/SUBJ/T1/SESS01/RUN01/T1.nii.gz')
    os.system('cp ' + data_path + '/nifti/' + sub + '/' + str(IM_data) + 
                  ' /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/RUN01/FUNC01.nii.gz')
    os.system('cp ' + data_path + '/nifti/' + sub + '/' + str(OB_data) + 
                  ' /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/RUN02/FUNC02.nii.gz')

    # run preprocessing pipeline (shared with EA)
    os.system('bash ' + code_path + '/ea-preproc-fsl.sh')

    # copy outputs into data folder
    if os.path.isdir(data_path + '/imob') == False:
        os.system('mkdir ' + data_path + '/imob' )

    # functional data
    os.system('cp /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/'
                            + 'func_MNI-nonlin.EA.01.nii.gz ' +
                  data_path + '/imob/' + sub + '_func_MNI-nonlin.im.01.nii.gz')
    os.system('cp /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/'
                            + 'func_MNI-nonlin.EA.02.nii.gz ' +
                  data_path + '/imob/' + sub + '_func_MNI-nonlin.ob.02.nii.gz')

    # MNI space EPI mask
    os.system('cp /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/'
                            + 'anat_EPI_mask_MNI-nonlin.nii.gz ' 
                            + data_path + '/imob/' + sub 
                            + '_anat_EPI_mask_MNI.nii.gz')

    # MNI space single-subject T1
    os.system('cp /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/'
                            + 'reg_T1_to_TAL.nii.gz '
                            + data_path + '/imob/' + sub 
                            + '_reg_T1_to_MNI-lin.nii.gz')

    # MNI space single-subject T1
    os.system('cp /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/'
                            + 'reg_nlin_TAL.nii.gz '
                            + data_path + '/imob/' + sub 
                            + '_reg_nlin_MNI.nii.gz')

    # motion paramaters
    os.system('cat /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/PARAMS/'
                            + 'motion.EA.01.1D > ' +
                  data_path + '/imob/' + sub + '_motion.1D')
    os.system('cat /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/PARAMS/'
                            + 'motion.EA.02.1D >> ' +
                  data_path + '/imob/' + sub + '_motion.1D')

    # copy out QC images of registration
    os.system('cp /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/'
                            + 'qc_reg_EPI_to_T1.pdf ' +
                  data_path + '/imob/' + sub + '_qc_reg_EPI_to_T1.pdf')
    os.system('cp /tmp/epitome/TEMP/SUBJ/FUNC/SESS01/'
                            + 'qc_reg_T1_to_MNI.pdf ' +
                  data_path + '/imob/' + sub + '_qc_reg_T1_to_MNI.pdf')

    # this file denotes participants who are finished
    os.system('touch ' + data_path + '/imob/' + sub + '_complete.log')

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

def main():
    """
    Essentially, analyzes the imitate observe data.

    1) Runs functional data through a custom epitome script.
    2) Extracts block onsets, durations, and parametric modulators from
       behavioual log files collected at the scanner.
    3) Writes out AFNI-formatted timing files as well as a GLM script per
       subject.
    4) Executes this script, producing beta-weights for each subject.
    5) ???
    6) Profit! 
    """
    # sets up relative paths (should be moved to a config.py file?)
    # removes /bin
    base_path = os.path.dirname(os.path.realpath(sys.argv[0]))[:-4]
    #base_path = '/projects/spins'
    assets_path = base_path + '/assets'
    data_path = base_path + '/data'
    code_path = base_path + '/code'

    # get list of subjects
    subjects = spn.utils.get_subjects(data_path)

    # loop through subjects
    for sub in subjects:

        if spn.utils.subject_type(sub) == 'phantom':
            continue
    
        # check if output already exists
        if os.path.isfile(data_path + '/imob/' + sub 
                                               + '_complete.log') == True:
            continue
    
        try:
            # pre-process the data
            process_functional_data(sub, data_path, code_path)
            
            # generate & run a first-level GLM script
            generate_analysis_script(sub, data_path, code_path)
            os.system('bash ' + data_path + '/imob/' + sub + '_glm_1stlevel_cmd.sh')

        except ValueError as ve:
            print('*** Skipping subject: ' + str(sub) + ' !!! ***')

if __name__ == "__main__":
    main()

    print(':D')

    #log = '444_SPN01_ZHH_P002-UCLAEmpAcc_part1.log'

    # find all subjects

    #fig.subplots_adjust(top=0.25)

    # extract ratings vector for actor
    # # find the timestamp in the response file -- [0][4] gets the column
    # timestamp = [0][4]
    # timestamp = timestamp - start

    #/projects/jdv/data/spins/behavioural
