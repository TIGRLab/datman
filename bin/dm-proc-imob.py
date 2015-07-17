#!/usr/bin/env python
"""
This analyzes imitate observe behavioural data.It could be generalized
to analyze any rapid event-related design experiment fairly easily.

Usage:
    dm-proc-imob.py [options] <project> <script> <assets>

Arguments: 
    <project>           Full path to the project directory containing data/.
    <script>            Full path to an epitome-style script.
    <assets>            Full path to an assets folder containing 
                                              EA-timing.csv, EA-vid-lengths.csv.

Options:
    -v,--verbose             Verbose logging
    --debug                  Debug logging

DETAILS

    1) Preprocesses MRI data.
    2) Produces an AFNI-compatible GLM file with the event timing. 
    3) Runs the GLM analysis at the single-subject level.

    Each subject is run through this pipeline if the outputs do not already exist.

DEPENDENCIES

    + matlab
    + afni

This message is printed with the -h, --help flags.
"""

import os, sys
import copy
import tempfile
import numpy as np
import nibabel as nib
import StringIO as io
import matplotlib.pyplot as plt
import datman as dm

from docopt import docopt


def process_functional_data(sub, datadir, script):
    # copy functional data into epitome-compatible structure
    try:
        niftis = filter(lambda x: 'nii.gz' in x, 
                            os.listdir(os.path.join(datadir, 'nii', sub)))
    except:
        print('ERROR: No "nii" folder found for {}.'.format(sub))
        raise ValueError

    try:
        T1_data = filter(lambda x: 'T1' == dm.utils.guess_tag(x), niftis)
        T1_data.sort()
        T1_data = T1_data[0]
    except:
        print('ERROR: No T1s found for {}.'.format(sub))
        raise ValueError

    try:
        IM_data = filter(lambda x: 'IMI' == dm.utils.guess_tag(x), niftis)
        if len(IM_data) == 1:
            IM_data = IM_data[0]
        else:
            print('MSG: Found multiple IM data, using newest: {}'.format(str(len(IM_data))))
            IM_data = IM_data[-1]
    except:
        print('ERROR: No IMITATE data found for {}.'.format(sub))
        raise ValueError

    try:
        OB_data = filter(lambda x: 'OBS' == dm.utils.guess_tag(x), niftis)
        if len(OB_data) == 1:
            OB_data = OB_data[0]
        else:
            print('MSG: Found multiple OB data, using newest: {}'.format(str(len(OB_data))))
            OB_data = OB_data[-1]
    except:
        print('ERROR: No OBSERVE data found for {}.'.format(sub))
        raise ValueError

    if os.path.isfile('{}/imob/{}_complete.log'.format(datadir, sub)) == True:
        if VERBOSE:
             print('MSG: Subject {} has already been preprocessed.'.format(sub))
        raise ValueError

    tmpdir = tempfile.mkdtemp(dir='/tmp')
    dm.utils.make_epitome_folders(os.path.join(tmpdir, 'epitome'), 2)
    epidir = os.path.join(tmpdir, 'epitome/TEMP/SUBJ')

    os.system('cp {}/nii/{}/{} {}/T1/SESS01/RUN01/T1.nii.gz'.format(datadir, sub, T1_data, epidir))
    os.system('cp {}/nii/{}/{} {}/FUNC/SESS01/RUN01/FUNC01.nii.gz'.format(datadir, sub, IM_data, epidir))
    os.system('cp {}/nii/{}/{} {}/FUNC/SESS01/RUN02/FUNC02.nii.gz'.format(datadir, sub, OB_data, epidir))

    # run preprocessing pipeline
    os.system('bash {} {} 4'.format(script, os.path.join(tmpdir, 'epitome')))

    # copy outputs into data folder
    if os.path.isdir('{}/imob'.format(datadir)) == False:
        os.system('mkdir {}/imob'.format(datadir))

    os.system('cp {}/FUNC/SESS01/func_MNI-nonlin.DATMAN.01.nii.gz {}/imob/{}_func_MNI-nonlin.im.01.nii.gz'.format(epidir, datadir, sub))
    os.system('cp {}/FUNC/SESS01/func_MNI-nonlin.DATMAN.02.nii.gz {}/imob/{}_func_MNI-nonlin.ob.02.nii.gz'.format(epidir, datadir, sub))
    os.system('cp {}/FUNC/SESS01/anat_EPI_mask_MNI-nonlin.nii.gz {}/imob/{}_anat_EPI_mask_MNI.nii.gz'.format(epidir, datadir, sub))
    os.system('cp {}/FUNC/SESS01/reg_T1_to_TAL.nii.gz {}/imob/{}_reg_T1_to_MNI-lin.nii.gz'.format(epidir, datadir, sub))
    os.system('cp {}/FUNC/SESS01/reg_nlin_TAL.nii.gz {}/imob/{}_reg_nlin_MNI.nii.gz'.format(epidir, datadir, sub))
    os.system('cat {}/FUNC/SESS01/PARAMS/motion.DATMAN.01.1D > {}/imob/{}_motion.1D'.format(epidir, datadir, sub))
    os.system('cat {}/FUNC/SESS01/PARAMS/motion.DATMAN.02.1D >> {}/imob/{}_motion.1D'.format(epidir, datadir, sub))
    # os.system('cp {}/FUNC/SESS01/qc_reg_EPI_to_T1.pdf ' + 
    #              '{}/imob/{}_qc_reg_EPI_to_T1.pdf'.format(
    #                                                     epidir, datadir, sub))
    # os.system('cp {}/FUNC/SESS01/qc_reg_T1_to_MNI.pdf ' + 
    #              '{}/imob/{}_qc_reg_T1_to_MNI.pdf'.format(
    #                                                     epidir, datadir, sub))
    os.system('touch {}/imob/{}_preproc-complete.log'.format(datadir, sub))
    os.system('rm -r {}'.format(tmpdir))

def generate_analysis_script(sub, datadir, assets):
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
                    os.listdir(os.path.join(datadir, 'imob')))
    niftis.sort()
    input_data = ''
    for nifti in niftis:
        input_data = input_data + datadir + '/imob/' + nifti + ' '

    # open up the master script, write common variables
    f = open('{}/imob/{}_glm_1stlevel_cmd.sh'.format(datadir, sub), 'wb')
    f.write("""#!/bin/bash

# Imitate Observe GLM for {sub}.
3dDeconvolve \\
    -input {input_data} \\
    -mask {datadir}/imob/{sub}_anat_EPI_mask_MNI.nii.gz \\
    -ortvec {datadir}/imob/{sub}_motion.1D motion_paramaters \\
    -polort 4 \\
    -num_stimts 12 \\
    -local_times \\
    -jobs 8 \\
    -x1D {datadir}/imob/{sub}_glm_1stlevel_design.mat \\
    -stim_times 1 {assets}/IM_event-times_AN.1D \'TENT(0,15,5)\' \\
    -stim_label 1 IM_AN \\
    -stim_times 2 {assets}/IM_event-times_FE.1D \'TENT(0,15,5)\' \\
    -stim_label 2 IM_FE \\
    -stim_times 3 {assets}/IM_event-times_FX.1D \'TENT(0,15,5)\' \\
    -stim_label 3 IM_FX \\
    -stim_times 4 {assets}/IM_event-times_HA.1D \'TENT(0,15,5)\' \\
    -stim_label 4 IM_HA \\
    -stim_times 5 {assets}/IM_event-times_NE.1D \'TENT(0,15,5)\' \\
    -stim_label 5 IM_NE \\
    -stim_times 6 {assets}/IM_event-times_SA.1D \'TENT(0,15,5)\' \\
    -stim_label 6 IM_SA \\
    -stim_times 7 {assets}/OB_event-times_AN.1D \'TENT(0,15,5)\' \\
    -stim_label 7 OB_AN \\
    -stim_times 8 {assets}/OB_event-times_FE.1D \'TENT(0,15,5)\' \\
    -stim_label 8 OB_FE \\
    -stim_times 9 {assets}/OB_event-times_FX.1D \'TENT(0,15,5)\' \\
    -stim_label 9 OB_FX \\
    -stim_times 10 {assets}/OB_event-times_HA.1D \'TENT(0,15,5)\' \\
    -stim_label 10 OB_HA \\
    -stim_times 11 {assets}/OB_event-times_NE.1D \'TENT(0,15,5)\' \\
    -stim_label 11 OB_NE \\
    -stim_times 12 {assets}/OB_event-times_SA.1D \'TENT(0,15,5)\' \\
    -stim_label 12 OB_SA \\
    -fitts {datadir}/imob/{sub}_glm_1stlevel_explained.nii.gz \\
    -errts {datadir}/imob/{sub}_glm_1stlevel_residuals.nii.gz \\
    -bucket {datadir}/imob/{sub}_glm_1stlevel.nii.gz \\
    -cbucket {datadir}/imob/{sub}_glm_1stlevel_coeffs.nii.gz \\
    -fout \\
    -tout \\
    -xjpeg {datadir}/imob/{sub}_glm_1stlevel_matrix.jpg
""".format(input_data=input_data, datadir=datadir, assets=assets, sub=sub))
    f.close()

def main():
    """
    Loops through subjects, preprocessing using supplied script, and runs a
    first-level GLM using AFNI (tent functions, 15 s window) on all subjects.
    """
    global VERBOSE 
    global DEBUG
    arguments  = docopt(__doc__)
    project    = arguments['<project>']
    script     = arguments['<script>']
    assets     = arguments['<assets>']

    datadir = os.path.join(project, 'data')

    try:
        subjects = dm.utils.get_subjects(os.path.join(datadir, 'nii'))
    except:
        print('ERROR: No "nii" folder found for {}.'.format(project))
        sys.exit()

    # loop through subjects
    for sub in subjects:
        if dm.utils.subject_type(sub) == 'phantom':
            continue
    
        # check if output already exists
        if os.path.isfile('{}/imob/{}_preproc-complete.log'.format(datadir, sub)) == False:
            try:
                process_functional_data(sub, datadir, script)    

            except ValueError as ve:
                print('ERROR: Failed to pre-process functional data for {}.'.format(sub))
                pass

        if os.path.isfile('{}/imob/{}_analysis-complete.log'.format(datadir, sub)) == False:
            try:
                generate_analysis_script(sub, datadir, assets)
                os.system('bash {}/imob/{}_glm_1stlevel_cmd.sh'.format(datadir, sub))
                os.system('touch {}/imob/{}_analysis-complete.log'.format(datadir, sub))

            except ValueError as ve:
                print('ERROR: Failed to analyze data for {}.'.format(sub))
                pass

if __name__ == "__main__":
    main()
