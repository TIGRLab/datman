#!/usr/bin/env python
"""
This analyzes imitate observe behavioural data.It could be generalized
to analyze any rapid event-related design experiment fairly easily.

Usage:
    dm-proc-imob.py [options] <project> <tmppath> <script> <assets>

Arguments: 
    <project>           Full path to the project directory containing data/.
    <tmppath>           Full path to a shared folder to run 
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
from random import choice
from string import ascii_uppercase, digits

import datman as dm
from datman.docopt import docopt

def process_functional_data(sub, data_path, log_path, tmp_path, tmpdict, script):

    nii_path = os.path.join(data_path, 'nii')
    t1_path = os.path.join(data_path, 't1')
    imob_path = os.path.join(data_path, 'imob')

    # freesurfer
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

    # functional data
    try:
        niftis = filter(lambda x: 'nii.gz' in x, os.listdir(os.path.join(nii_path, sub)))
    except:
        print('ERROR: No "nii" folder found for ' + str(sub))
        raise ValueError

    try:
        IM_data = filter(lambda x: 'IMI' == dm.utils.scanid.parse_filename(x)[1], niftis)
        if len(IM_data) == 1:
            IM_data = IM_data[0]
        elif len(IM_data) > 1:
            print('MSG: Found multiple IM data for {}, using newest'.format(sub))
            IM_data = IM_data[-1]
        else:
            raise ValueError
    except:
        print('ERROR: No IM data for {}.'.format(sub))
        raise ValueError

    try:
        OB_data = filter(lambda x: 'OBS' == dm.utils.scanid.parse_filename(x)[1], niftis)
        if len(OB_data) == 1:
            OB_data = OB_data[0]
        elif len(OB_data) > 1:
            print('MSG: Found multiple OB data for {}, using newest.'.format(sub))
            OB_data = OB_data[-1]
        else:
            raise ValueError
    except:
        print('ERROR: No OB data found for {}.'.format(sub))
        raise ValueError

    if os.path.isfile('{}/{}_preproc-complete.log'.format(imob_path, sub)) == True:
        if VERBOSE:
             print('MSG: Subject {} has already been preprocessed.'.format(sub))
        raise ValueError

    try:
        tmpfolder = tempfile.mkdtemp(prefix='imob-', dir=tmp_path)
        tmpdict[sub] = tmpfolder
        dm.utils.make_epitome_folders(tmpfolder, 2)
        
        returncode, _, _ = dm.utils.run('cp {}/{} {}/TEMP/SUBJ/T1/SESS01/anat_T1_brain.nii.gz'.format(t1_path, t1_data, tmpfolder))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cp {}/{} {}/TEMP/SUBJ/T1/SESS01/anat_aparc_brain.nii.gz'.format(t1_path, aparc, tmpfolder))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cp {}/{} {}/TEMP/SUBJ/T1/SESS01/anat_aparc2009_brain.nii.gz'.format(t1_path, aparc2009, tmpfolder))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cp {}/{}/{} {}/TEMP/SUBJ/FUNC/SESS01/RUN01/FUNC01.nii.gz'.format(nii_path, sub, IM_data, tmpfolder))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cp {}/{}/{} {}/TEMP/SUBJ/FUNC/SESS01/RUN02/FUNC02.nii.gz'.format(nii_path, sub, OB_data, tmpfolder))
        dm.utils.check_returncode(returncode)

        # submit to queue
        uid = ''.join(choice(ascii_uppercase + digits) for _ in range(6))
        cmd = 'bash {} {} 4 '.format(script, tmpfolder)
        name = 'dm_imob_{}_{}'.format(sub, uid)
        log = os.path.join(log_path, name + '.log')
        cmd = 'echo {cmd} | qsub -o {log} -S /bin/bash -V -q main.q -cwd -N {name} -l mem_free=3G,virtual_free=3G -j y'.format(cmd=cmd, log=log, name=name)
        dm.utils.run(cmd)

        return name, tmpdict

    except:
        raise ValueError

def export_data(sub, tmpfolder, func_path):

    tmppath = os.path.join(tmpfolder, 'TEMP', 'SUBJ', 'FUNC', 'SESS01')    

    try:
        # make directory
        out_path = dm.utils.define_folder(os.path.join(func_path, sub))

        # export data
        dm.utils.run('cp {tmppath}/func_MNI-nonlin.DATMAN.01.nii.gz {out_path}/{sub}_func_MNI-nonlin.IM.01.nii.gz'.format(tmppath=tmppath, out_path=out_path, sub=sub))
        dm.utils.run('cp {tmppath}/func_MNI-nonlin.DATMAN.02.nii.gz {out_path}/{sub}_func_MNI-nonlin.OB.02.nii.gz'.format(tmppath=tmppath, out_path=out_path, sub=sub))
        dm.utils.run('cp {tmppath}/anat_EPI_mask_MNI-nonlin.nii.gz {out_path}/{sub}_anat_EPI_mask_MNI.nii.gz'.format(tmppath=tmppath, out_path=out_path, sub=sub))
        dm.utils.run('cp {tmppath}/reg_T1_to_TAL.nii.gz {out_path}/{sub}_reg_T1_to_MNI-lin.nii.gz'.format(tmppath=tmppath, out_path=out_path, sub=sub))
        dm.utils.run('cp {tmppath}/reg_nlin_TAL.nii.gz {out_path}/{sub}_reg_nlin_MNI.nii.gz'.format(tmppath=tmppath, out_path=out_path, sub=sub))

        # check outputs
        outputs = ('nonlin.IM.01', 'nonlin.OB.02', 'nlin_MNI', 'MNI-lin', 'mask_MNI')
        for out in outputs:
            if len(filter(lambda x: out in x, os.listdir(out_path))) == 0:
                print('ERROR: Failed to export {}'.format(out))
                raise ValueError

        dm.utils.run('cat {tmppath}/PARAMS/motion.DATMAN.01.1D > {out_path}/{sub}_motion.1D'.format(tmppath=tmppath, out_path=out_path, sub=sub))
        dm.utils.run('cat {tmppath}/PARAMS/motion.DATMAN.02.1D >> {out_path}/{sub}_motion.1D'.format(tmppath=tmppath, out_path=out_path, sub=sub))

        if os.path.isfile('{out_path}/{sub}_motion.1D'.format(out_path=out_path, sub=sub)) == False:
            print('Failed to export {}_motion.1D'.format(sub))
            raise ValueError

        dm.utils.run('touch {out_path}/{sub}_preproc-complete.log'.format(out_path=out_path, sub=sub))
        dm.utils.run('rm -r {}'.format(tmpfolder))
        
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
    IM_data = filter(lambda x: 'nii.gz' in x and sub + '.IM.' in x, os.listdir(os.path.join(func_path, sub)))
    OB_data = filter(lambda x: 'nii.gz' in x and sub + '.OB.' in x, os.listdir(os.path.join(func_path, sub)))

    IM_data = os.path.join(func_path, sub, IM_data)
    OB_data = os.path.join(func_path, sub, OB_data)

    # open up the master script, write common variables
    f = open('{func_path}/{sub}/{sub}_glm_1stlevel_cmd.sh'.format(func_path=func_path, sub=sub), 'wb')
    f.write("""#!/bin/bash
#
# Contrasts: emotional faces vs. fixation, emotional faces vs. neutral faces.
# use the 'bucket' dataset (*_1stlevel.nii.gz) for group level analysis.
#

# Imitate GLM for {sub}.
3dDeconvolve \\
    -input {IM_data} \\
    -mask {func_path}/{sub}/{sub}_anat_EPI_mask_MNI.nii.gz \\
    -ortvec {func_path}/{sub}/{sub}_motion.1D motion_paramaters \\
    -polort 4 \\
    -num_stimts 6 \\
    -local_times \\
    -jobs 8 \\
    -x1D {func_path}/{sub}/{sub}_glm_1stlevel_design.mat \\
    -stim_label 1 IM_AN -stim_times 1 {assets}/IM_event-times_AN.1D \'TENT(0,15,5)\' \\
    -stim_label 2 IM_FE -stim_times 2 {assets}/IM_event-times_FE.1D \'TENT(0,15,5)\' \\
    -stim_label 3 IM_FX -stim_times 3 {assets}/IM_event-times_FX.1D \'TENT(0,15,5)\' \\
    -stim_label 4 IM_HA -stim_times 4 {assets}/IM_event-times_HA.1D \'TENT(0,15,5)\' \\
    -stim_label 5 IM_NE -stim_times 5 {assets}/IM_event-times_NE.1D \'TENT(0,15,5)\' \\
    -stim_label 6 IM_SA -stim_times 6 {assets}/IM_event-times_SA.1D \'TENT(0,15,5)\' \\
    -glt_label 1 emot-fix  -gltsym 'SYM: -1*IM_FX +0*IM_NE +0.25*IM_AN +0.25*IM_FE +0.25*IM_HA +0.25*IM_SA' \\
    -glt_label 2 emot-neut -gltsym 'SYM: +0*IM_FX -1*IM_NE +0.25*IM_AN +0.25*IM_FE +0.25*IM_HA +0.25*IM_SA' \\
    -fitts   {func_path}/{sub}/{sub}_glm_IM_1stlvl_explained.nii.gz \\
    -errts   {func_path}/{sub}/{sub}_glm_IM_1stlvl_residuals.nii.gz \\
    -bucket  {func_path}/{sub}/{sub}_glm_IM_1stlvl.nii.gz \\
    -cbucket {func_path}/{sub}/{sub}_glm_IM_1stlvl_allcoeffs.nii.gz \\
    -fout -tout -xjpeg {func_path}/{sub}/{sub}_glm_1stlevel_matrix.jpg

# Obserse GLM for {sub}.
3dDeconvolve \\
    -input {OB_data} \\
    -mask {func_path}/{sub}/{sub}_anat_EPI_mask_MNI.nii.gz \\
    -ortvec {func_path}/{sub}/{sub}_motion.1D motion_paramaters \\
    -polort 4 \\
    -num_stimts 6 \\
    -local_times \\
    -jobs 8 \\
    -x1D {func_path}/{sub}/{sub}_glm_1stlevel_design.mat \\
    -stim_label 1 OB_AN -stim_times 1 {assets}/OB_event-times_AN.1D \'TENT(0,15,5)\' \\
    -stim_label 2 OB_FE -stim_times 2 {assets}/OB_event-times_FE.1D \'TENT(0,15,5)\' \\
    -stim_label 3 OB_FX -stim_times 3 {assets}/OB_event-times_FX.1D \'TENT(0,15,5)\' \\
    -stim_label 4 OB_HA -stim_times 4 {assets}/OB_event-times_HA.1D \'TENT(0,15,5)\' \\
    -stim_label 5 OB_NE -stim_times 5 {assets}/OB_event-times_NE.1D \'TENT(0,15,5)\' \\
    -stim_label 6 OB_SA -stim_times 6 {assets}/OB_event-times_SA.1D \'TENT(0,15,5)\' \\
    -glt_label 1 emot-fix  -gltsym 'SYM: -1*IM_FX +0*IM_NE +0.25*IM_AN +0.25*IM_FE +0.25*IM_HA +0.25*IM_SA' \\
    -glt_label 2 emot-neut -gltsym 'SYM: +0*IM_FX -1*IM_NE +0.25*IM_AN +0.25*IM_FE +0.25*IM_HA +0.25*IM_SA' \\
    -fitts   {func_path}/{sub}/{sub}_glm_OB_1stlvl_explained.nii.gz \\
    -errts   {func_path}/{sub}/{sub}_glm_OB_1stlvl_residuals.nii.gz \\
    -bucket  {func_path}/{sub}/{sub}_glm_OB_1stlvl.nii.gz \\
    -cbucket {func_path}/{sub}/{sub}_glm_OB_1stlvl_allcoeffs.nii.gz \\
    -fout -tout -xjpeg {func_path}/{sub}/{sub}_glm_1stlevel_matrix.jpg


""".format(IM_data=IM_data, OB_data=OB_data, func_path=func_path, assets=assets, sub=sub))
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
    log_path = dm.utils.define_folder(os.path.join(project, 'logs/imob'))

    list_of_names = []
    tmpdict = {}
    subjects = dm.utils.get_subjects(nii_path)

    # preprocess

    for sub in subjects:
        if dm.scanid.is_phantom(sub) == True: 
            continue
        if os.path.isfile(os.path.join(func_path, '{sub}/{sub}_preproc-complete.log'.format(sub=sub))) == True:
            continue        
        try:
            name, tmpdict = process_functional_data(sub, data_path, log_path, tmp_path, tmpdict, script)
            list_of_names.append(name)    

        except ValueError as ve:
            continue

    if len(list_of_names) > 0:
        dm.utils.run_dummy_q(list_of_names)

    # export 
    for sub in tmpdict:
        if os.path.isfile(os.path.join(func_path, '{sub}/{sub}_preproc-complete.log'.format(sub=sub))) == True:
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
        if os.path.isfile(os.path.join(func_path, '{sub}/{sub}_analysis-complete.log'.format(sub=sub))) == True:
            continue
        try:
            generate_analysis_script(sub, func_path, assets)
            returncode, _, _ = dm.utils.run('bash {func_path}/{sub}/{sub}_glm_1stlevel_cmd.sh'.format(func_path=func_path, sub=sub))
            dm.utils.check_returncode(returncode)
            dm.utils.run('touch {func_path}/{sub}/{sub}_analysis-complete.log'.format(func_path=func_path, sub=sub))
            
        except:
            print('ERROR: Failed to analyze IMOB data for {}.'.format(sub))
            pass

if __name__ == "__main__":
    main()
