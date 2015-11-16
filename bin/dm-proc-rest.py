#!/usr/bin/env python
"""
This pre-processes resting state data and extracts the mean time series from the defined
ROIs in MNI space (6 mm spheres). This data is returned as the time series, a full correlation
matrix, and a partial correlation matrix (all in .csv format).

Usage:
    dm-proc-rest.py [options] <project> <tmppath> <script> <atlas> <tags>...

Arguments:
    <project>           Full path to the project directory containing data/.
    <tmppath>           Full path to a shared folder to run
    <script>            Full path to an epitome-style script.
    <atlas>             Full path to a NIFTI atlas in MNI space.
    <tags>              DATMAN tags to run pipeline on.

Options:
    -v,--verbose        Verbose logging
    --debug             Debug logging

DETAILS

    1) Preprocesses fMRI data using the defined epitome-style script.
    2) Produces a CSV of the ROI time series from the MNI-space atlas NIFTI in assets/.
    3) Produces a correlation matrix of these same time series.

    Each subject is run through this pipeline if the outputs do not already exist.
    Outputs are placed in <project>/data/rest
    Logs in <project>/logs/rest

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
from random import choice
from glob import glob
from string import ascii_uppercase, digits
import numpy as np
from scipy import stats, linalg
import nibabel as nib
import StringIO as io
import matplotlib.pyplot as plt
import tempfile as tmp

import datman as dm
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

def proc_data(sub, data_path, log_path, tmp_path, tmpdict, tagdict, script, tags):
    """
    Copies functional data into epitome-compatible structure, then runs the
    associated epitome script on the data. Finally, we copy the outputs into
    the 'rest' directory.
    """

    nii_path = os.path.join(data_path, 'nii')
    t1_path = os.path.join(data_path, 't1')
    func_path = os.path.join(data_path, 'rest')

    # make tags lowercase
    tags = map(lambda x: x.lower(), tags)

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
        niftis = filter(lambda x: '.nii' or 'nii.gz' in x, os.listdir(
                                                os.path.join(nii_path, sub)))
    except:
        print('ERROR: No "nifti" folder found for ' + str(sub) + ', aborting!')
        raise ValueError

    try:
        rest_data = filter(lambda x: any(t in x.lower() for t in tags), niftis)

        if len(rest_data) == 1:
            rest_data = [rest_data]

        # keep track of the tags of the input files, as we will need the name the epitome outputs with them
        taglist = []
        for d in rest_data:
            taglist.append(dm.utils.scanid.parse_filename(d)[1])

    except:
        print('ERROR: No REST data found for ' + str(sub))
        raise ValueError

    try:
        # copy data into temporary epitome structure
        n_runs = len(rest_data)
        tmpfolder = tmp.mkdtemp(prefix='rest-', dir=tmp_path)

        # dicts to map from subject --> temp directory --> tag list (in order)
        tmpdict[sub] = tmpfolder
        tagdict[tmpfolder] = taglist

        dm.utils.make_epitome_folders(tmpfolder, n_runs)
        returncode, _, _ = dm.utils.run('cp {t1_path}/{t1_data} {tmpfolder}/TEMP/SUBJ/T1/SESS01/anat_T1_brain.nii.gz'.format(t1_path=t1_path, t1_data=t1_data, tmpfolder=tmpfolder))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cp {t1_path}/{aparc} {tmpfolder}/TEMP/SUBJ/T1/SESS01/anat_aparc_brain.nii.gz'.format(t1_path=t1_path, aparc=aparc, tmpfolder=tmpfolder))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cp {t1_path}/{aparc2009} {tmpfolder}/TEMP/SUBJ/T1/SESS01/anat_aparc2009_brain.nii.gz'.format(t1_path=t1_path, aparc2009=aparc2009, tmpfolder=tmpfolder))
        dm.utils.check_returncode(returncode)

        for i, d in enumerate(rest_data):
            returncode, _, _ = dm.utils.run('cp {nii_path}/{sub}/{d} {tmpfolder}/TEMP/SUBJ/FUNC/SESS01/RUN{i}/FUNC.nii.gz'.format(nii_path=nii_path, sub=sub, d=d, i='%02d' % (i+1), tmpfolder=tmpfolder))
            dm.utils.check_returncode(returncode)

        # submit to queue
        uid = ''.join(choice(ascii_uppercase + digits) for _ in range(6))
        cmd = 'bash {} {} 4 '.format(script, tmpfolder)
        name = 'dm_rest_{}_{}'.format(sub, uid)
        log = os.path.join(log_path, name + '.log')
        cmd = 'echo {cmd} | qsub -o {log} -S /bin/bash -V -q main.q -cwd -N {name} -l mem_free=3G,virtual_free=3G -j y'.format(cmd=cmd, log=log, name=name)
        dm.utils.run(cmd)

        return name, tmpdict, tagdict

    except:
        raise ValueError

def export_data(sub, tmpfolder, taglist, func_path):

    tmppath = os.path.join(tmpfolder, 'TEMP', 'SUBJ', 'FUNC', 'SESS01')
    print(taglist)
    try:
        # make directory
        out_path = dm.utils.define_folder(os.path.join(func_path, sub))

        # export data
        for i, t in enumerate(taglist):
            print('cp {tmppath}/func_MNI-nonlin.DATMAN.{i}.nii.gz {out_path}/{sub}_func_MNI-nonlin.{t}.{i}.nii.gz'.format(i='%02d' % (i+1), t=t, tmppath=tmppath, out_path=out_path, sub=sub))
            returncode, _, _ = dm.utils.run('cp {tmppath}/func_MNI-nonlin.DATMAN.{i}.nii.gz {out_path}/{sub}_func_MNI-nonlin.{t}.{i}.nii.gz'.format(i='%02d' % (i+1), t=t, tmppath=tmppath, out_path=out_path, sub=sub))
            dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cp {tmppath}/anat_EPI_mask_MNI-nonlin.nii.gz {out_path}/{sub}_anat_EPI_mask_MNI.nii.gz'.format(tmppath=tmppath, out_path=out_path, sub=sub))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cp {tmppath}/reg_T1_to_TAL.nii.gz {out_path}/{sub}_reg_T1_to_MNI-lin.nii.gz'.format(tmppath=tmppath, out_path=out_path, sub=sub))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cp {tmppath}/reg_nlin_TAL.nii.gz {out_path}/{sub}_reg_nlin_MNI.nii.gz'.format(tmppath=tmppath, out_path=out_path, sub=sub))
        dm.utils.check_returncode(returncode)
        returncode, _, _ = dm.utils.run('cat {tmppath}/PARAMS/motion.DATMAN.01.1D > {out_path}/{sub}_motion.1D'.format(tmppath=tmppath, out_path=out_path, sub=sub))
        dm.utils.check_returncode(returncode)

        #if os.path.isfile('{out_path}/{sub}_motion.1D'.format(out_path=out_path, sub=sub)) == False:
        #    print('Failed to export {sub}_motion.1D'.format(sub=sub))
        #    raise ValueError

        # mark as done, clean up
        dm.utils.run('touch {out_path}/{sub}_preproc-complete.log'.format(out_path=out_path, sub=sub))
        dm.utils.run('rm -r ' + tmpfolder)

    except:
        raise ValueError

def analyze_data(sub, atlas, func_path):
    """
    Extracts: time series, correlation / partial correlation matricies using labels defined
    in 'rsfc.labels' in assets/. This file should be formatted for 3dUndump.
    """
    if os.path.isfile(atlas) == False:
        raise ValueError

    # get an input file list
    filelist = glob('{func_path}/{sub}/{sub}_func_MNI*'.format(func_path=func_path, sub=sub))

    for f in filelist:

        # strips off extension and folder structure from input filename
        basename = '.'.join(os.path.basename(f).split('.')[:-2])

        dm.utils.run('3dresample -master {f} -prefix {func_path}/{sub}/{basename}_rois.nii.gz -inset {atlas}/shen_1mm_268_parcellation.nii.gz'.format(
                         f=f, func_path=func_path, basename=basename, sub=sub, atlas=atlas))
        rois, _, _, _ = dm.utils.loadnii('{func_path}/{sub}/{basename}_rois.nii.gz'.format(func_path=func_path, sub=sub, basename=basename))
        data, _, _, _ = dm.utils.loadnii('{}'.format(f))

        n_rois = len(np.unique(rois[rois > 0]))
        dims = np.shape(data)

        # loop through all ROIs, extracting mean timeseries.
        output = np.zeros((n_rois, dims[1]))

        for i, roi in enumerate(np.unique(rois[rois > 0])):
 	    idx = np.where(rois == roi)[0]

	    if len(idx) > 0:
	        output[i, :] = np.mean(data[idx, :], axis=0)

        # save the raw time series
        np.savetxt('{func_path}/{sub}/{basename}_roi-timeseries.csv'.format(func_path=func_path, sub=sub, basename=basename), output.transpose(), delimiter=',')

        # save the full correlation matrix
        corrs = np.corrcoef(output)
        np.savetxt('{func_path}/{sub}/{basename}_roi-corrs.csv'.format(func_path=func_path, sub=sub, basename=basename), corrs, delimiter=',')

        # save partial correlation matrix
        #pcorrs = partial_corr(output.transpose())
        #np.savetxt('{func_path}/{sub}/{sub}_roi-pcorrs.csv'.format(func_path=func_path, sub=sub), pcorrs, delimiter=',')

    dm.utils.run('touch {func_path}/{sub}/{sub}_analysis-complete.log'.format(func_path=func_path, sub=sub))

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
    atlas      = arguments['<atlas>']
    tags       = arguments['<tags>']

    # sets up paths
    data_path = dm.utils.define_folder(os.path.join(project, 'data'))
    nii_path = dm.utils.define_folder(os.path.join(data_path, 'nii'))
    t1_path = dm.utils.define_folder(os.path.join(data_path, 't1'))
    func_path = dm.utils.define_folder(os.path.join(data_path, 'rest'))
    tmp_path = dm.utils.define_folder(tmp_path)
    _ = dm.utils.define_folder(os.path.join(project, 'logs'))
    log_path = dm.utils.define_folder(os.path.join(project, 'logs/rest'))

    list_of_names = []
    tmpdict = {}
    tagdict = {}
    subjects = dm.utils.get_subjects(nii_path)

    # preprocess
    for sub in subjects:
        if dm.scanid.is_phantom(sub) == True:
            continue
        if os.path.isfile(os.path.join(func_path, '{sub}/{sub}_preproc-complete.log'.format(sub=sub))) == True:
            continue
        try:
            # pre-process the data
            name, tmpdict, tagdict = proc_data(sub, data_path, log_path, tmp_path, tmpdict, tagdict, script, tags)
            list_of_names.append(name)

        except ValueError as ve:
            continue

    if len(list_of_names) > 0:
        dm.utils.run_dummy_q(list_of_names)

    # export
    print('***EXPORTING DATA***')
    print('***WHY IS THE TAGDICT EMPTY???***')
    print('***TMPDICT***:')
    print(tmpdict)
    print('***TAGDICT***:')
    print(tagdict)
    for sub in tmpdict:
        if os.path.isfile(os.path.join(func_path, '{sub}/{sub}_preproc-complete.log'.format(sub=sub))) == True:
            continue
        try:
            export_data(sub, tmpdict[sub], tagdict[tmpdict[sub]], func_path)
        except:
            print('ERROR: Failed to export {}'.format(sub))
            continue
        else:
            continue

    # analyze
    for sub in subjects:
        if dm.scanid.is_phantom(sub) == True:
            continue
        if os.path.isdir(os.path.join(func_path, sub)) == False:
            continue
        if os.path.isfile(os.path.join(func_path, '{sub}/{sub}_analysis-complete.log'.format(sub=sub))) == True:
            continue
        try:
            analyze_data(sub, atlas, func_path)
        except ValueError as ve:
            print('ERROR: Failed to extract connectivity data from {}.'.format(sub))

if __name__ == "__main__":
    main()

