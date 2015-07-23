#!/usr/bin/env python
"""
This pre-processes resting state data and extracts the mean time series from the defined
ROIs in MNI space (6 mm spheres). This data is returned as the time series, a full correlation
matrix, and a partial correlation matrix (all in .csv format). 

Usage:
    dm-proc-rest.py [options] <project> <tmppath> <script> <assets>

Arguments: 
    <project>           Full path to the project directory containing data/.
    <tmppath>           Full path to a shared folder to run 
    <script>            Full path to an epitome-style script.
    <assets>            Full path to an assets folder containing rsfc.labels (3dUndump format).

Options:
    -v,--verbose             Verbose logging
    --debug                  Debug logging

DETAILS

    1) Preprocesses fMRI data using the defined epitome-style script.
    2) Produces a CSV of the ROI time series from the 'rsfc.labels' file in 'assets/' (6mm sphere).
    3) Produces a correlation and partial correlation matrix of these same time series.

    Each subject is run through this pipeline if the outputs do not already exist.
    Outputs are placed in <project>/data/rest
    Logs in <project>/logs/rest

DEPENDENCIES

    + python
    + afni
    + fsl

    Requires dm-proc-freesurfer.py to be completed.

This message is printed with the -h, --help flags.
"""

import os, sys
import copy
from random import choice
from glob import glob
from string import ascii_uppercase, digits
import numpy as np
from scipy import stats, linalg
import nibabel as nib
import StringIO as io
import matplotlib.pyplot as plt
import datman as dm
import tempfile as tmp
from datman.docopt import docopt

def partial_corr(C):
    """
    Partial Correlation in Python (clone of Matlab's partialcorr)
    from https://gist.github.com/fabianp/9396204419c7b638d38f

    This uses the linear regression approach to compute the partial 
    correlation (might be slow for a huge number of variables). The 
    algorithm is detailed here:

        http://en.wikipedia.org/wiki/Partial_correlation#Using_linear_regression

    Taking X and Y two variables of interest and Z the matrix with all the variable minus {X, Y},
    the algorithm can be summarized as

        1) perform a normal linear least-squares regression with X as the target and Z as the predictor
        2) calculate the residuals in Step #1
        3) perform a normal linear least-squares regression with Y as the target and Z as the predictor
        4) calculate the residuals in Step #3
        5) calculate the correlation coefficient between the residuals from Steps #2 and #4; 

    The result is the partial correlation between X and Y while controlling for the effect of Z

    Returns the sample linear partial correlation coefficients between pairs of variables in C, controlling 
    for the remaining variables in C.


    Parameters
    ----------
    C : array-like, shape (n, p)
        Array with the different variables. Each column of C is taken as a variable


    Returns
    -------
    P : array-like, shape (p, p)
        P[i, j] contains the partial correlation of C[:, i] and C[:, j] controlling
        for the remaining variables in C.
    """
    
    C = np.asarray(C)
    p = C.shape[1]
    P_corr = np.zeros((p, p), dtype=np.float)
    for i in range(p):
        P_corr[i, i] = 1
        for j in range(i+1, p):
            idx = np.ones(p, dtype=np.bool)
            idx[i] = False
            idx[j] = False
            beta_i = linalg.lstsq(C[:, idx], C[:, j])[0]
            beta_j = linalg.lstsq(C[:, idx], C[:, i])[0]

            res_j = C[:, j] - C[:, idx].dot( beta_i)
            res_i = C[:, i] - C[:, idx].dot(beta_j)
            
            corr = stats.pearsonr(res_i, res_j)[0]
            P_corr[i, j] = corr
            P_corr[j, i] = corr
        
    return P_corr

def proc_data(sub, data_path, tmp_path, tmpdict, script):
    """
    Copies functional data into epitome-compatible structure, then runs the
    associated epitome script on the data. Finally, we copy the outputs into
    the 'rest' directory.
    """

    nii_path = os.path.join(data_path, 'nii')
    t1_path = os.path.join(data_path, 't1')
    rest_path = os.path.join(data_path, 'rest')
    
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
            print('MSG: Multiple resting-state data! Using most recent for {}'.format(sub)) 

        rest_data = rest_data[-1]

    except:
        print('ERROR: No REST data found for ' + str(sub))
        raise ValueError

    # copy data into temporary epitome structure
    tmpfolder = tmp.mkdtemp(prefix='rest-', dir=tmp_path)
    tmpdict[sub] = tmpfolder

    dm.utils.make_epitome_folders(tmpfolder, 1)
    dm.utils.run('cp {t1_path}/{t1_data} {tmpfolder}/TEMP/SUBJ/T1/SESS01/anat_T1_brain.nii.gz'.format(t1_path=t1_path, t1_data=t1_data, tmpfolder=tmpfolder))
    dm.utils.run('cp {t1_path}/{aparc} {tmpfolder}/TEMP/SUBJ/T1/SESS01/anat_aparc_brain.nii.gz'.format(t1_path=t1_path, aparc=aparc, tmpfolder=tmpfolder))
    dm.utils.run('cp {t1_path}/{aparc2009} {tmpfolder}/TEMP/SUBJ/T1/SESS01/anat_aparc2009_brain.nii.gz'.format(t1_path=t1_path, aparc2009=aparc2009, tmpfolder=tmpfolder))
    dm.utils.run('cp {nii_path}/{sub}/{rest_data} {tmpfolder}/TEMP/SUBJ/FUNC/SESS01/RUN01/FUNC01.nii.gz'.format(nii_path=nii_path, sub=sub, rest_data=rest_data, tmpfolder=tmpfolder))

    # submit to queue
    uid = ''.join(choice(ascii_uppercase + digits) for _ in range(6))
    cmd = 'bash {} {} 4 '.format(script, tmpfolder)
    name = 'datman_rest_{}_{}'.format(sub, uid)
    log = os.path.join(data_path, 'logs/rest')
    cmd = 'echo {cmd} | qsub -o {log} -S /bin/bash -V -q main.q -cwd -N {name} -l mem_free=3G,virtual_free=3G -j y'.format(cmd=cmd, log=log, name=name)
    dm.utils.run(cmd)

    return name, tmpdict

def check_returncode(returncode):
    if returncode != 0:
        raise ValueError

def export_data(sub, tmpfolder, rest_path):
    
    # check for existance of all ouputs before copy
    try:
        tmppath = os.path.join(tmpfolder, 'TEMP', 'SUBJ', 'FUNC', 'SESS01')
        print('cp {tmppath}/func_MNI-nonlin.DATMAN.01.nii.gz {rest_path}/{sub}_func_MNI-nonlin.01.nii.gz'.format(tmppath=tmppath, rest_path=rest_path, sub=sub))

        returncode, _, _ = dm.utils.run('cp {tmppath}/func_MNI-nonlin.DATMAN.01.nii.gz {rest_path}/{sub}_func_MNI-nonlin.01.nii.gz'.format(tmppath=tmppath, rest_path=rest_path, sub=sub))
        check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cp {tmppath}/anat_EPI_mask_MNI-nonlin.nii.gz {rest_path}/{sub}_anat_EPI_mask_MNI.nii.gz'.format(tmppath=tmppath, rest_path=rest_path, sub=sub))
        check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cp {tmppath}/reg_T1_to_TAL.nii.gz {rest_path}/{sub}_reg_T1_to_MNI-lin.nii.gz'.format(tmppath=tmppath, rest_path=rest_path, sub=sub))
        check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cp {tmppath}/reg_nlin_TAL.nii.gz {rest_path}/{sub}_reg_nlin_MNI.nii.gz'.format(tmppath=tmppath, rest_path=rest_path, sub=sub))
        check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cat {tmppath}/PARAMS/motion.DATMAN.01.1D > {rest_path}/{sub}_motion.1D'.format(tmppath=tmppath, rest_path=rest_path, sub=sub))
        check_returncode(returncode)
        returncode, _, _ = dm.utils.run('touch {rest_path}/{sub}_preproc-complete.log'.format(rest_path=rest_path, sub=sub))
        check_returncode(returncode)
        returncode, _, _ = dm.utils.run('rm -r ' + tmpfolder)
        check_returncode(returncode)

    except:
        raise ValueError
    # TODO
    #
    # # copy out QC images of registration
    # dm.utils.run('cp {tmpfolder}/TEMP/SUBJ/FUNC/SESS01/'
    #                         + 'qc_reg_EPI_to_T1.pdf ' +
    #               data_path + '/rest/' + sub + '_qc_reg_EPI_to_T1.pdf')
    # dm.utils.run('cp {tmpfolder}/TEMP/SUBJ/FUNC/SESS01/'
    #                         + 'qc_reg_T1_to_MNI.pdf ' +
    #               data_path + '/rest/' + sub + '_qc_reg_T1_to_MNI.pdf')


def analyze_data(sub, assets, rest_path):
    """
    Extracts: time series, correlation / partial correlation matricies using labels defined
    in 'rsfc.labels' in assets/. This file should be formatted for 3dUndump.
    """
    labelfile = os.path.join(assets, 'rsfc.labels')
    if os.path.isfile(labelfile) == False:
        raise ValueError

    dm.utils.run('3dUndump -master {rest_path}/{sub}_anat_EPI_mask_MNI.nii.gz -xyz -srad 6 -prefix {rest_path}/{sub}_rois.nii.gz {labels}'.format(rest_path=rest_path, sub=sub, labels=os.path.join(assets, 'rsfc.labels')))
    rois, _, _, _ = dm.utils.loadnii('{rest_path}/{sub}_rois.nii.gz'.format(rest_path=rest_path, sub=sub))
    data, _, _, _ = dm.utils.loadnii('{rest_path}/{sub}_func_MNI-nonlin.01.nii.gz'.format(rest_path=rest_path, sub=sub))

    n_rois = len(np.unique(rois[rois > 0]))
    dims = np.shape(data)

    output = np.zeros((n_rois, dims[1]))

    for i, roi in enumerate(np.unique(rois[rois > 0])):
        idx = np.where(rois == roi)[0]
        
        if len(idx) > 0:
            output[i, :] = np.mean(data[idx, :], axis=0)

    # save the raw time series
    np.savetxt('{rest_path}/{sub}_roi-timeseries.csv'.format(rest_path=rest_path, sub=sub), output.transpose(), delimiter=',')

    # save the full correlation matrix
    corrs = np.corrcoef(output)
    np.savetxt('{rest_path}/{sub}_roi-corrs.csv'.format(rest_path=rest_path, sub=sub), corrs, delimiter=',')
    
    # save partial correlation matrix
    pcorrs = partial_corr(output.transpose())
    np.savetxt('{rest_path}/{sub}_roi-pcorrs.csv'.format(rest_path=rest_path, sub=sub), pcorrs, delimiter=',') 

    dm.utils.run('touch {rest_path}/{sub}_analysis-complete.log'.format(rest_path=rest_path, sub=sub))

def main():
    """
    Essentially, analyzes the resting-state data.

    1) Runs functional data through a defined epitome script.
    2) Extracts time series from the cortex using MRI-space ROIs.
    3) Generates a correlation matrix for each subject.
    4) Generates an experiment-wide correlation matrix.
    5) Generates a set of graph metrics for each subject. 
    """

    global VERBOSE 
    global DEBUG
    arguments  = docopt(__doc__)
    project    = arguments['<project>']
    tmp_path   = arguments['<tmppath>']
    script     = arguments['<script>']
    assets     = arguments['<assets>']

    # sets up paths
    data_path = dm.utils.define_folder(os.path.join(project, 'data'))
    nii_path = dm.utils.define_folder(os.path.join(data_path, 'nii'))
    t1_path = dm.utils.define_folder(os.path.join(data_path, 't1'))
    rest_path = dm.utils.define_folder(os.path.join(data_path, 'rest'))
    tmp_path = dm.utils.define_folder(tmp_path)
    _ = dm.utils.define_folder(os.path.join(project, 'logs'))
    log_path = dm.utils.define_folder(os.path.join(project, 'logs/rest'))

    list_of_names = []
    tmpdict = {}
    subjects = dm.utils.get_subjects(nii_path)

    # loop through subjects
    for sub in subjects:

        if dm.scanid.is_phantom(sub) == True: 
            continue
        if os.path.isfile(os.path.join(rest_path,  '{}_preproc-complete.log'.format(sub))) == True:
            continue

        try:
            # pre-process the data
            name, tmpdict = proc_data(sub, data_path, tmp_path, tmpdict, script)
            list_of_names.append(name)

        except ValueError as ve:
            print('ERROR: Failed to preprocess {}'.format(sub))

    if list_of_names == []:
        sys.exit()

    # wait for queued items to complete
    dm.utils.run_dummy_q(list_of_names)

    # copy functionals, registrations, motion parameters to rest folder.
    for sub in subjects:
        if dm.scanid.is_phantom(sub) == True: 
            continue
        if os.path.isfile(os.path.join(rest_path,  sub + '_preproc-complete.log')) == False:
            if sub in tmpdict:
                try:
                    export_data(sub, tmpdict[sub], rest_path)
                except:
                    print('ERROR: Failed to export {}'.format(sub))
                    continue
            else:
                continue

        if os.path.isfile(os.path.join(rest_path,  sub + '_analysis-complete.log')) == False:
            try:
                analyze_data(sub, assets, rest_path)
            except ValueError as ve:
                print('ERROR: Failed to extract time-series and connectivity data from pre-processed data.')

if __name__ == "__main__":
    main()
