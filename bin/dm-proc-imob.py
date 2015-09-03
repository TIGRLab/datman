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

    + python
    + matlab
    + afni
    + fsl
    + epitome

    Requires dm-proc-freesurfer.py to be completed.

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
from datman.docopt import docopt

def process_functional_data(sub, datadir, tmp_path, tmpdict, script):
    # copy functional data into epitome-compatible structure
    try:
        niftis = filter(lambda x: 'nii.gz' in x, os.listdir(os.path.join(datadir, 'nii', sub)))
    except:
        print('ERROR: No "nii" folder found for {}.'.format(sub))
        raise ValueError

    try:
        T1_data = filter(lambda x: 'T1' == dm.utils.scanid.parse_filename(x)[1], niftis)
        T1_data.sort()
        T1_data = T1_data[0]
    except:
        print('ERROR: No T1s found for {}.'.format(sub))
        raise ValueError

    try:
        IM_data = filter(lambda x: 'IMI' == dm.utils.scanid.parse_filename(x)[1], niftis)
        if len(IM_data) == 1:
            IM_data = IM_data[0]
        else:
            print('MSG: Found multiple IM data, using newest: {}'.format(str(len(IM_data))))
            IM_data = IM_data[-1]
    except:
        print('ERROR: No IMITATE data found for {}.'.format(sub))
        raise ValueError

    try:
        OB_data = filter(lambda x: 'OBS' == dm.utils.scanid.parse_filename(x)[1], niftis)
        if len(OB_data) == 1:
            OB_data = OB_data[0]
        else:
            print('MSG: Found multiple OB data, using newest: {}'.format(str(len(OB_data))))
            OB_data = OB_data[-1]
    except:
        print('ERROR: No OBSERVE data found for {}.'.format(sub))
        raise ValueError

    if os.path.isfile('{}/imob/{}_preproc-complete.log'.format(datadir, sub)) == True:
        if VERBOSE:
             print('MSG: Subject {} has already been preprocessed.'.format(sub))
        raise ValueError

    tmpfolder = tempfile.mkdtemp(prefix='imob', dir=tmp_path)
    tmpdict[sub] = tmpfolder

    dm.utils.make_epitome_folders(tmpfolder, 2)
    epidir = os.path.join(tmpfolder, 'epitome/TEMP/SUBJ')
    dir_i = os.path.join(os.environ['SUBJECTS_DIR'], sub, 'mri')

    # T1: freesurfer data
    os.system('mri_convert --in_type mgz --out_type nii -odt float -rt nearest --input_volume {}/brain.mgz --output_volume {}/T1/SESS01/anat_T1_fs.nii.gz'.format(dir_i, epidir))
    os.system('3daxialize -prefix {tmpfolder}/TEMP/SUBJ/T1/SESS01/anat_T1_brain.nii.gz -axial {tmpfolder}/TEMP/SUBJ/T1/SESS01/anat_T1_fs.nii.gz'.format(epidir=epidir))

    os.system('mri_convert --in_type mgz --out_type nii -odt float -rt nearest --input_volume {}/aparc+aseg.mgz --output_volume {}/T1/SESS01/anat_aparc_fs.nii.gz'.format(dir_i, epidir))
    os.system('3daxialize -prefix {tmpfolder}/TEMP/SUBJ/T1/SESS01/anat_aparc_brain.nii.gz -axial {tmpfolder}/TEMP/SUBJ/T1/SESS01/anat_aparc_fs.nii.gz'.format(epidir=epidir))

    os.system('mri_convert --in_type mgz --out_type nii -odt float -rt nearest --input_volume {}/aparc.a2009s+aseg.mgz --output_volume {}/T1/SESS01/anat_aparc2009_fs.nii.gz'.format(dir_i, epidir))
    os.system('3daxialize -prefix {tmpfolder}/TEMP/SUBJ/T1/SESS01/anat_aparc2009_brain.nii.gz -axial {tmpfolder}/TEMP/SUBJ/T1/SESS01/anat_aparc2009_fs.nii.gz'.format(epidir=epidir))

    # functional data
    os.system('cp {}/nii/{}/{} {}/T1/SESS01/RUN01/T1.nii.gz'.format(datadir, sub, T1_data, epidir))
    os.system('cp {}/nii/{}/{} {}/FUNC/SESS01/RUN01/FUNC01.nii.gz'.format(datadir, sub, IM_data, epidir))
    os.system('cp {}/nii/{}/{} {}/FUNC/SESS01/RUN02/FUNC02.nii.gz'.format(datadir, sub, OB_data, epidir))

    # run preprocessing pipeline
    os.system('bash {} {} 4'.format(script, os.path.join(tmpfolder, 'epitome')))

def export_data(sub, tmpfolder, func_path):

    tmppath = os.path.join(tmpfolder, 'TEMP', 'SUBJ', 'FUNC', 'SESS01')    

    try:
        returncode, _, _ = dm.utils.run('cp {}/func_MNI-nonlin.DATMAN.01.nii.gz {}/imob/{}_func_MNI-nonlin.im.01.nii.gz'.format(tmppath, func_path, sub))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cp {}/func_MNI-nonlin.DATMAN.02.nii.gz {}/imob/{}_func_MNI-nonlin.ob.02.nii.gz'.format(tmppath, func_path, sub))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cp {}/anat_EPI_mask_MNI-nonlin.nii.gz {}/imob/{}_anat_EPI_mask_MNI.nii.gz'.format(tmppath, func_path, sub))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cp {}/reg_T1_to_TAL.nii.gz {}/imob/{}_reg_T1_to_MNI-lin.nii.gz'.format(tmppath, func_path, sub))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cp {}/reg_nlin_TAL.nii.gz {}/imob/{}_reg_nlin_MNI.nii.gz'.format(tmppath, func_path, sub))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cat {}/PARAMS/motion.DATMAN.01.1D > {}/imob/{}_motion.1D'.format(tmppath, func_path, sub))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cat {}/PARAMS/motion.DATMAN.02.1D >> {}/imob/{}_motion.1D'.format(tmppath, func_path, sub))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('touch {}/{}_preproc-complete.log'.format(func_path, sub))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('rm -r {}'.format(tmpdir))
        dm.utils.check_returncode(returncode)
    except:
        raise ValueError

    #TODO
    # os.system('cp {}/FUNC/SESS01/qc_reg_EPI_to_T1.pdf ' + 
    #              '{}/imob/{}_qc_reg_EPI_to_T1.pdf'.format(
    #                                                     epidir, datadir, sub))
    # os.system('cp {}/FUNC/SESS01/qc_reg_T1_to_MNI.pdf ' + 
    #              '{}/imob/{}_qc_reg_T1_to_MNI.pdf'.format(
    #                                                     epidir, datadir, sub))


def generate_analysis_script(sub, func_path, assets):
    """
    This writes the analysis script to replicate the methods in [insert paper 
    here]. It expects timing files to exist (these are static, and are generated 
    by 'imob-parse.py').

    Briefly, this is a standard rapid-event related design. We use 5 tent 
    functions to explain each event over a 15 second window (this is the 
    standard length of the HRF).

    """
    # first, determine input functional files
    niftis = filter(lambda x: 'nii.gz' in x and sub + '_func' in x, os.listdir(func_path))
    niftis.sort()
    input_data = ''
    for nifti in niftis:
        input_data = input_data + func_path + nifti + ' '

    # open up the master script, write common variables
    f = open('{}/{}_glm_1stlevel_cmd.sh'.format(func_path, sub), 'wb')
    f.write("""#!/bin/bash

# Imitate Observe GLM for {sub}.
3dDeconvolve \\
    -input {input_data} \\
    -mask {func_path}/{sub}_anat_EPI_mask_MNI.nii.gz \\
    -ortvec {func_path}/{sub}_motion.1D motion_paramaters \\
    -polort 4 \\
    -num_stimts 12 \\
    -local_times \\
    -jobs 8 \\
    -x1D {func_path}/{sub}_glm_1stlevel_design.mat \\
    -stim_label  1 IM_AN -stim_times  1 {assets}/IM_event-times_AN.1D \'TENT(0,15,5)\' \\
    -stim_label  2 IM_FE -stim_times  2 {assets}/IM_event-times_FE.1D \'TENT(0,15,5)\' \\
    -stim_label  3 IM_FX -stim_times  3 {assets}/IM_event-times_FX.1D \'TENT(0,15,5)\' \\
    -stim_label  4 IM_HA -stim_times  4 {assets}/IM_event-times_HA.1D \'TENT(0,15,5)\' \\
    -stim_label  5 IM_NE -stim_times  5 {assets}/IM_event-times_NE.1D \'TENT(0,15,5)\' \\
    -stim_label  6 IM_SA -stim_times  6 {assets}/IM_event-times_SA.1D \'TENT(0,15,5)\' \\
    -stim_label  7 OB_AN -stim_times  7 {assets}/OB_event-times_AN.1D \'TENT(0,15,5)\' \\
    -stim_label  8 OB_FE -stim_times  8 {assets}/OB_event-times_FE.1D \'TENT(0,15,5)\' \\
    -stim_label  9 OB_FX -stim_times  9 {assets}/OB_event-times_FX.1D \'TENT(0,15,5)\' \\
    -stim_label 10 OB_HA -stim_times 10 {assets}/OB_event-times_HA.1D \'TENT(0,15,5)\' \\
    -stim_label 11 OB_NE -stim_times 11 {assets}/OB_event-times_NE.1D \'TENT(0,15,5)\' \\
    -stim_label 12 OB_SA -stim_times 12 {assets}/OB_event-times_SA.1D \'TENT(0,15,5)\' \\
    -fitts {func_path}/{sub}_glm_1stlevel_explained.nii.gz \\
    -errts {func_path}/{sub}_glm_1stlevel_residuals.nii.gz \\
    -bucket {func_path}/{sub}_glm_1stlevel.nii.gz \\
    -cbucket {func_path}/{sub}_glm_1stlevel_coeffs.nii.gz \\
    -fout \\
    -tout \\
    -xjpeg {func_path}/{sub}_glm_1stlevel_matrix.jpg
""".format(input_data=input_data, func_path=func_path, assets=assets, sub=sub))
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
    tmp_path   = arguments['<tmppath>']
    script     = arguments['<script>']
    assets     = arguments['<assets>']

    data_path = dm.utils.define_folder(os.path.join(project, 'data'))
    nii_path = dm.utils.define_folder(os.path.join(data_path, 'nii'))
    func_path = dm.utils.define_folder(os.path.join(data_path, 'imob'))
    tmp_path = dm.utils.define_folder(tmp_path)
    _ = dm.utils.define_folder(os.path.join(project, 'logs'))
    log_path = dm.utils.define_folder(os.path.join(project, 'logs/ea'))

    list_of_names = []
    tmpdict = {}
    subjects = dm.utils.get_subjects(nii_path)

    # preprocess

    for sub in subjects:
        if dm.scanid.is_phantom(sub) == True: 
            continue
        if os.path.isfile(os.path.join(func_path,  '{}_preproc-complete.log'.format(sub))) == True:
            continue        
        try:
            name, tmpdict = process_functional_data(sub, data_path, tmp_path, script)
            list_of_names.append(name)    

        except ValueError as ve:
            continue

    if list_of_names == []:
        sys.exit()

    dm.utils.run_dummy_q(list_of_names)


    # export 
    for sub in tmpdict:
        if os.path.isfile(os.path.join(func_path, '{}_preproc-complete.log')) == True:
            continue
        try:
            export_data(sub, tmpdict[sub], func_path)
        except:
            print('ERROR: Failed to export {}'.format(sub))
            continue
        else:
            continue

    # analyze
    for sub in subjects:      
        if dm.scanid.is_phantom(sub) == True: 
            continue
        if os.path.isfile(os.path.join(data_path,  '{}_analysis-complete.log'.format(sub))) == True:
            continue
        try:
            generate_analysis_script(sub, data_path, assets)
            returncode, _, _ = dm.utils.run('bash {}/{}_glm_1stlevel_cmd.sh'.format(func_path, sub))
            dm.utils.check_returncode(returncode)
            returncode, _, _ = dm.utils.run('touch {}/{}_analysis-complete.log'.format(data_path, sub))
            dm.utils.check_returncode(returncode)

        except:
            print('ERROR: Failed to analyze IMOB data for {}.'.format(sub))
            pass

if __name__ == "__main__":
    main()
