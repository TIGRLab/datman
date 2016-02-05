#!/usr/bin/env python
"""
This pre-processes resting state data and extracts the mean time series from the defined
ROIs in MNI space (6 mm spheres). This data is returned as the time series, a full correlation
matrix, and a partial correlation matrix (all in .csv format).

Usage:
    dm-proc-rest.py [options] <project> <script> <atlas> [<subject>...]

Arguments:
    <project>           Full path to the project directory containing data/.
    <script>            Full path to an epitome-style script.
    <atlas>             Full path to a NIFTI atlas in MNI space.
    <subject>           Subject name to run on, e.g. SPN01_CMH_0020_01. If not
                        provided, all subjects matching the given --tags will
                        be processed.

Options:
    --tags LIST         DATMAN tags to run pipeline on. (comma delimited) [default: RST]
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

from datman.docopt import docopt
from glob import glob
from random import choice
from scipy import stats, linalg
from string import ascii_uppercase, digits
import datman as dm
import logging
import numpy as np
import os
import shutil
import sys
import tempfile
import time

logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))


class MissingDataException(Exception):
    pass


class ProcessingException(Exception):
    pass


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
        for j in range(i + 1, p):
            idx = np.ones(p, dtype=np.bool)
            idx[i] = False
            idx[j] = False
            beta_i = linalg.lstsq(C[:, idx], C[:, j])[0]
            beta_j = linalg.lstsq(C[:, idx], C[:, i])[0]

            res_j = C[:, j] - C[:, idx].dot(beta_i)
            res_i = C[:, i] - C[:, idx].dot(beta_j)

            corr = stats.pearsonr(res_i, res_j)[0]
            P_corr[i, j] = corr
            P_corr[j, i] = corr

    return P_corr


def proc_data(sub, data, log_path, tmpfolder, script):
    """
    Copies functional data into epitome-compatible structure, then runs the
    associated epitome script on the data. Finally, we copy the outputs into
    the 'rest' directory.

    A ProcessingException is raised if there are any errors during preprocessing.
    """

    t1_data = data['T1']
    aparc = data['aparc']
    aparc2009 = data['aparc2009']
    rest_data = data['resting']
    taglist = data['tags']

    # setup and run preprocessing
    # copy data into temporary epitome structure
    dm.utils.make_epitome_folders(tmpfolder, len(rest_data))
    epi_t1_dir = '{}/TEMP/SUBJ/T1/SESS01'.format(tmpfolder)
    epi_func_dir = '{}/TEMP/SUBJ/FUNC/SESS01'.format(tmpfolder)

    try:
        shutil.copyfile(t1_data, '{}/anat_T1_brain.nii.gz'.format(epi_t1_dir))
        shutil.copyfile(aparc, '{}/anat_aparc_brain.nii.gz'.format(epi_t1_dir))
        shutil.copyfile(
            aparc2009, '{}/anat_aparc2009_brain.nii.gz'.format(epi_t1_dir))
        for i, d in enumerate(rest_data):
            shutil.copyfile(
                d, '{}/RUN{}/FUNC.nii.gz'.format(epi_func_dir, '%02d' % (i + 1)))
    except IOError, e:
        logger.exception("Exception when copying files to epitome temp folder")
        raise ProcessingException(
            "Problem copying files to epitome temp folder")

    cmd = '{} {} 4'.format(script, tmpfolder)
    logger.debug('exec: {}'.format(cmd))
    rtn, out, err = dm.utils.run(cmd)
    output = '\n'.join([out, err]).replace('\n', '\n\t')
    if rtn != 0:
        logger.error(output)
        raise ProcessingException("Trouble running preprocessing data")
    else:
        logger.info(output)

def export_data(sub, data, tmpfolder, func_path):
    tmppath = os.path.join(tmpfolder, 'TEMP', 'SUBJ', 'FUNC', 'SESS01')
    try:
        out_path = dm.utils.define_folder(os.path.join(func_path, sub))

        for i, t in enumerate(data['tags']):
            idx = '%02d' % (i + 1)
            shutil.copyfile(
                '{inpath}/func_MNI-nonlin.DATMAN.{i}.nii.gz'.format(
                    i=idx, inpath=tmppath),
                '{outpath}/{sub}_func_MNI-nonlin.{t}.{i}.nii.gz'.format(
                    i=idx, t=t, outpath=out_path, sub=sub))

        shutil.copyfile(
            '{}/anat_EPI_mask_MNI-nonlin.nii.gz'.format(tmppath),
            '{}/{}_anat_EPI_mask_MNI.nii.gz'.format(out_path, sub))
        shutil.copyfile(
            '{}/reg_T1_to_TAL.nii.gz'.format(tmppath),
            '{}/{}_reg_T1_to_MNI-lin.nii.gz'.format(out_path, sub))
        shutil.copyfile(
            '{}/reg_nlin_TAL.nii.gz'.format(tmppath),
            '{}/{}_reg_nlin_MNI.nii.gz'.format(out_path, sub))
        shutil.copyfile(
            '{}/PARAMS/motion.DATMAN.01.1D'.format(tmppath),
            '{}/{}_motion.1D'.format(out_path, sub))
    except IOError, e:
        logger.exception("Exception when copying files from temp folder")
        raise ProcessingException("Problem copying files from temp folder")

    open('{}/{}_preproc-complete.log'.format(out_path, sub), 'a').close()


def analyze_data(sub, atlas, func_path):
    """
    Extracts: time series, correlation / partial correlation matricies using labels defined
    in 'rsfc.labels' in assets/. This file should be formatted for 3dUndump.
    """

    # get an input file list
    filelist = glob(
        '{func_path}/{sub}/{sub}_func_MNI*'.format(func_path=func_path, sub=sub))

    for f in filelist:

        # strips off extension and folder structure from input filename
        basename = '.'.join(os.path.basename(f).split('.')[:-2])

        rtn, out, err = dm.utils.run(
            '3dresample -master {f} -prefix {func_path}/{sub}/{basename}_rois.nii.gz -inset {atlas}'.format(
                f=f, func_path=func_path, basename=basename, sub=sub, atlas=atlas))
        output = '\n'.join([out, err]).replace('\n', '\n\t')
        if rtn != 0:
            logger.error(output)
            raise ProcessingException("Error resampling atlas.")
        else:
            logger.info(output)

        rois, _, _, _ = dm.utils.loadnii(
            '{func_path}/{sub}/{basename}_rois.nii.gz'.format(func_path=func_path, sub=sub, basename=basename))
        data, _, _, _ = dm.utils.loadnii(f)

        n_rois = len(np.unique(rois[rois > 0]))
        dims = np.shape(data)

        # loop through all ROIs, extracting mean timeseries.
        output = np.zeros((n_rois, dims[1]))

        for i, roi in enumerate(np.unique(rois[rois > 0])):
            idx = np.where(rois == roi)[0]

            if len(idx) > 0:
                output[i, :] = np.mean(data[idx, :], axis=0)

        # save the raw time series
        np.savetxt('{func_path}/{sub}/{basename}_roi-timeseries.csv'.format(
            func_path=func_path, sub=sub, basename=basename), output.transpose(), delimiter=',')

        # save the full correlation matrix
        corrs = np.corrcoef(output)
        np.savetxt('{func_path}/{sub}/{basename}_roi-corrs.csv'.format(
            func_path=func_path, sub=sub, basename=basename), corrs, delimiter=',')

    open('{path}/{sub}/{sub}_analysis-complete.log'.format(path=func_path,
                                                           sub=sub), 'a').close()


def is_complete(projectdir, subject):
    complete_file = os.path.join(projectdir, 'data', 'rest', subject,
                                 '{sub}_analysis-complete.log'.format(sub=subject))
    return os.path.isfile(complete_file)


def get_required_data(projectdir, sub, tags):
    """Finds the necessary data for processing this subject.

    If the necessary data can't be found, a MissingDataException is
    raised. Otherwise, a dict is returned with:

    - T1 : path to the T1 data
    - aparc : path to the aparc atlas
    - aparc2009 : path to the aparc2009 atlas
    - resting : list of paths to the resting state scans
    - tags : parallel list of tags for each scan
    """

    nii_path = os.path.join(projectdir, 'data', 'nii')
    t1_path = os.path.join(projectdir, 'data', 'freesurfer', 't1')

    # find freesurfer data
    t1 = '{path}/{sub}_T1.nii.gz'.format(path=t1_path, sub=sub)
    aparc = '{path}/{sub}_APARC.nii.gz'.format(path=t1_path, sub=sub)
    aparc2009 = '{path}/{sub}_APARC2009.nii.gz'.format(path=t1_path, sub=sub)

    if not os.path.exists(t1):
        raise MissingDataException(
            'No T1 found for sub {}. Skipping.'.format(sub))

    if not os.path.exists(aparc):
        raise MissingDataException(
            'No aparc atlas found for sub {}. Skipping.'.format(sub))

    if not os.path.exists(aparc2009):
        raise MissingDataException(
            'No aparc 2009 atlas found for sub {}. Skipping.'.format(sub))

    # find resting state data
    rest_data = [glob('{path}/{sub}/*_{tag}_*.nii*'.format(
        path=nii_path, sub=sub, tag=tag)) for tag in tags]
    rest_data = reduce(lambda x, y: x + y, rest_data)  # merge lists

    if not rest_data:
        raise MissingDataException('No REST data found for ' + str(sub))

    logger.debug("Found REST data for subject {}: {}".format(sub, rest_data))

    # keep track of the tags of the input files, as we will need the name the
    # epitome outputs with them
    taglist = []
    for d in rest_data:
        taglist.append(dm.utils.scanid.parse_filename(d)[1])

    return {'T1': t1,
            'aparc': aparc,
            'aparc2009': aparc2009,
            'resting': rest_data,
            'tags': taglist}


def process_subject(project, data, sub, tags, atlas, script):
    data_path = dm.utils.define_folder(os.path.join(project, 'data'))
    func_path = dm.utils.define_folder(os.path.join(data_path, 'rest'))
    _ = dm.utils.define_folder(os.path.join(project, 'logs'))
    log_path = dm.utils.define_folder(os.path.join(project, 'logs/rest'))

    tempfolder = tempfile.mkdtemp(prefix='rest-')
    try:
        if os.path.isfile(os.path.join(func_path, sub, '{sub}_preproc-complete.log'.format(sub=sub))):
            logger.info(
                "Subject {} preprocessing already complete.".format(sub))
        else:
            logger.info("Preprocessing subject {}".format(sub))
            proc_data(sub, data, log_path, tempfolder, script)
            export_data(sub, data, tempfolder, func_path)

        if not os.path.isdir(os.path.join(func_path, sub)):
            logger.error(
                "Subject's rest folder not present after preproc.".format(sub))
            return False

        analyze_data(sub, atlas, func_path)
    except ProcessingException, e:
        logger.error(e.message)
        return False
    finally:
        if os.path.exists(tempfolder):
            shutil.rmtree(tempfolder)


def main():
    """
    Essentially, analyzes the resting-state data.

    1) Runs functional data through a defined epitome script.
    2) Extracts time series from the cortex using MRI-space ROIs.
    3) Generates a correlation matrix for each subject.
    4) Generates an experiment-wide correlation matrix.
    5) Generates a set of graph metrics for each subject.
    """

    arguments = docopt(__doc__)
    project = arguments['<project>']
    script = arguments['<script>']
    atlas = arguments['<atlas>']
    subjects = arguments['<subject>']
    tags = arguments['--tags'].split(',')
    verbose = arguments['--verbose']
    debug = arguments['--debug']

    if verbose:
        logger.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)

    # check inputs
    if not os.path.isfile(atlas):
        logger.error("Atlas {} does not exist".format(atlas))
        sys.exit(-1)

    if not os.path.isfile(script):
        logger.error("Epitome script {} does not exist".format(script))
        sys.exit(-1)

    # submit jobs if not working on single subject
    submit_mode = len(subjects) == 0
    logger.debug("Subjects: {}".format(subjects))
    logger.debug("Submit mode: {}".format(submit_mode))

    nii_path = os.path.join(project, 'data', 'nii')
    subjects = subjects or dm.utils.get_subjects(nii_path)

    for subject in subjects:
        if is_complete(project, subject):
            logger.info("Subject {} processed. Skipping.".format(subject))
            continue

        if dm.scanid.is_phantom(subject):
            logger.debug("Subject {} is a phantom. Skipping.".format(subject))
            continue

        try:
            data = get_required_data(project, subject, tags)
        except MissingDataException, e:
            logger.error(e.message)
            continue

        if submit_mode:
            opts = ''
            opts += verbose and ' --verbose' or ''
            opts += debug and ' --debug' or ''
            opts += tags and ' --tags=' + ','.join(tags) or ''

            cmd = "{me} {opts} {project} {script} {atlas} {subject}".format(
                me=__file__,
                opts=opts,
                project=project,
                script=script,
                atlas=atlas,
                subject=subject)
            job_name = 'dm_rest_{}'.format(subject)
            memopts = 'h_vmem=3G,mem_free=3G,virtual_free=3G'
            stamp = time.strftime("%Y%m%d-%H%M%S")
            logfile = '{name}-{stamp}.log'.format(name=job_name, stamp=stamp)
            logpath = os.path.join(project, 'logs', 'rest', logfile)
            qsub = 'qsub -V -N {name} -l {memopts} -o {logpath} -j y -b y {cmd}'.format(
                name=job_name,
                memopts=memopts,
                logpath=logpath,
                cmd=cmd)

            logger.debug('exec: {}'.format(qsub))
            dm.utils.run(qsub)
        else:
            process_subject(project, data, subject, tags, atlas, script)

if __name__ == "__main__":
    main()
