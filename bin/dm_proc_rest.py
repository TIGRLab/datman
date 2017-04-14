#!/usr/bin/env python
"""
This extracts the mean time series from the defined ROIs in MNI space (6 mm
spheres). This data is returned as the time series & a full correlation matrix,
in .csv format).

Usage:
    dm_proc_rest.py [options] <study>

Arguments:
    <study>             study name defined in master configuration .yml file

Options:
    --subject SUBJID    Subject ID to run
    --debug             Debug logging

DETAILS

    1) Produces a CSV of the ROI time series from the MNI-space atlas NIFTI in assets/.
    2) Produces a correlation matrix of these same time series.
"""

from datman.docopt import docopt
import datman.utils as utils
import datman.config as cfg
import logging
import glob
import numpy as np
import os, sys
import time
import yaml

logging.basicConfig(level=logging.WARN, format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

NODE = os.uname()[1]

def get_inputs(config, path, exp, scanid):
    """
    Finds the epitome exports matching the connectivity tag specified in the
    settings file
    """
    inputs = []

    # get target epitome exports
    target_filetypes = config.study_config['fmri'][exp]['conn']
    if type(target_filetypes) == str:
        target_filetypes = [target_filetypes]

    # find the matching pre-processed output files
    candidates = glob.glob('{}/{}_*.nii.gz'.format(path, scanid))
    for filetype in target_filetypes:
        inputs.extend(filter(lambda x: filetype + '.nii.gz' in x, candidates))

    # remove GLM outputs
    inputs = filter(lambda x: '_glm_' not in x, inputs)

    return inputs

def run_analysis(scanid, config, study):
    """
    Extracts: time series, correlation matricies using defined atlas.
    """
    study_base = config.get_study_base(study)
    fmri_dir = os.path.join(study_base, config.site_config['paths']['fmri'])
    experiments = config.study_config['fmri'].keys()
    atlas = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir, 'assets/shen_2mm_268_parcellation.nii.gz')

    if not os.path.isfile(atlas):
        print('ERROR: atlas file {} not found'.format(atlas))
        sys.exit(1)

    for exp in experiments:
        path = os.path.join(fmri_dir, exp, scanid)

        # get filetypes to analyze, ignoring ROI files
        inputs = get_inputs(config, path, exp, scanid)

        for filename in inputs:
            basename = os.path.basename(utils.splitext(filename)[0])

            # if the final correlation matrix exists, skip processing
            if os.path.isfile(os.path.join(path, basename + '_roi-corrs.csv')):
                continue

            # generate ROI file in register with subject's data
            roi_file = os.path.join(path, basename + '_rois.nii.gz')
            if not os.path.isfile(roi_file):
                rtn, out = utils.run('3dresample -master {} -prefix {} -inset {}'.format(filename, roi_file, atlas))
                if rtn:
                    logger.error('{}\n{}'.format(out, NODE))
                    raise Exception('Error resampling atlas {} to match {}.'.format(atlas, filename))
                else:
                    pass

            rois, _, _, _ = utils.loadnii(roi_file)
            data, _, _, _ = utils.loadnii(filename)

            n_rois = len(np.unique(rois[rois > 0]))
            dims = np.shape(data)

            # loop through all ROIs, extracting mean timeseries.
            output = np.zeros((n_rois, dims[1]))

            for i, roi in enumerate(np.unique(rois[rois > 0])):
                idx = np.where(rois == roi)[0]

                if len(idx) > 0:
                    output[i, :] = np.mean(data[idx, :], axis=0)

            # save the raw time series
            np.savetxt(os.path.join(path, basename + '_roi-timeseries.csv'), output, delimiter=',')

            # save the full correlation matrix
            corrs = np.corrcoef(output)
            np.savetxt(os.path.join(path, basename + '_roi-corrs.csv'), corrs, delimiter=',')

def main():

    arguments = docopt(__doc__)
    study     = arguments['<study>']
    scanid    = arguments['--subject']
    debug     = arguments['--debug']

    logging.info('Starting')
    if debug:
        logger.setLevel(logging.DEBUG)

    # load config for study
    try:
        config = cfg.config(study=study)
    except ValueError:
        logger.error('study {} not defined in master configuration file\n{}'.format(study, NODE))
        sys.exit(1)

    study_base = config.get_study_base(study)

    if 'fmri' not in config.site_config['paths']:
        logger.error("paths:fmri not defined in site configuration file\n{}".format(NODE))
        sys.exit(1)

    fmri_dir = os.path.join(study_base, config.site_config['paths']['fmri'])

    if scanid:
        path = os.path.join(fmri_dir, scanid)
        try:
            run_analysis(scanid, config, study)
        except Exception as e:
            logger.error(e)
            sys.exit(1)

    # run in batch mode
    else:
        # look for subjects with at least one fmri type missing outputs
        subjects = []

        # loop through fmri experiments defined
        for exp in config.study_config['fmri'].keys():
            expected_files = config.study_config['fmri'][exp]['conn']
            fmri_dirs = glob.glob('{}/*'.format(os.path.join(fmri_dir, exp)))

            for subj_dir in fmri_dirs:
                candidates = glob.glob('{}/*'.format(subj_dir))
                for filetype in expected_files:
                    # add subject if outputs don't already exist
                    if not filter(lambda x: '{}_roi-corrs.csv'.format(filetype) in x, candidates):
                        subjects.append(os.path.basename(subj_dir))
                        break

        # collapse found subjects (do not double-count) and create a list of commands
        commands = []
        subjects = list(set(subjects))
        for subject in subjects:
            commands.append(" ".join([__file__, study, '--subject {}'.format(subject)]))

        if commands:
            logger.debug('queueing up the following commands:\n'+'\n'.join(commands))

            for i, cmd in enumerate(commands):
                jobname = 'dm_rest_{}_{}'.format(i, time.strftime("%Y%m%d-%H%M%S"))
                jobfile = '/tmp/{}'.format(jobname)
                logfile = '/tmp/{}.log'.format(jobname)
                errfile = '/tmp/{}.err'.format(jobname)
                with open(jobfile, 'wb') as fid:
                    fid.write('#!/bin/bash\n')
                    fid.write(cmd)

                rtn, out = utils.run('qsub -V -q main.q -o {} -e {} -N {} {}'.format(
                    logfile, errfile, jobname, jobfile))
                if rtn:
                    logger.error("Job submission failed. Output follows. {}".format(NODE))
                    logger.error("stdout: {}".format(out))
                    sys.exit(1)

if __name__ == "__main__":
    main()
