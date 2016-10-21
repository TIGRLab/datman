#!/usr/bin/env python
"""
This extracts the mean time series from the defined ROIs in MNI space (6 mm
spheres). This data is returned as the time series & a full correlation matrix,
in .csv format).

Usage:
    dm-proc-rest.py [options] <config>

Arguments:
    <config>            Configuration file

Options:
    --subject SUBJID    Subject ID to run
    --debug             Debug logging

DETAILS

    1) Produces a CSV of the ROI time series from the MNI-space atlas NIFTI in assets/.
    2) Produces a correlation matrix of these same time series.
"""

from datman.docopt import docopt
import datman as dm
import logging
import glob
import numpy as np
import os, sys
import time
import yaml

logging.basicConfig(level=logging.WARN, format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

class MissingDataException(Exception):
    raise

class ProcessingException(Exception):
    raise

def get_inputs(config, path, scanid):
    """
    Finds the epitome exports matching the connectivity tag specified in the
    settings file
    """
    inputs = []

    # get target epitome exports
    target_filetypes = config['fmri'][exp]['conn']
    if type(target_filetypes) == str:
        target_filetypes = [target_filetypes]

    # find the matching pre-processed output files
    candidates = glob.glob('{}/{}_*.nii.gz'.format(path, scanid))
    for filetype in target_filetypes:
        inputs.extend(filter(lambda x: filetype + '.nii.gz' in x, candidates))

    return inputs

def run_analysis(scanid, config):
    """
    Extracts: time series, correlation matricies using defined atlas.
    """
    fmri_dir = config['paths']['fmri']
    experiments = config['fmri'].keys()
    atlas = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir, 'assets/shen_2mm_268_parcellation.nii.gz')

    if not os.path.isfile(atlas):
        print('ERROR: atlas file {} not found'.format(atlas))
        sys.exit(1)

    for exp in experiments:
        path = os.path.join(fmri_dir, exp, scanid)

        # get filetypes to analyze, ignoring ROI files
        inputs = get_inputs(config, path, scanid)

        for filename in inputs:
            basename = os.path.basename(dm.utils.splitext(filename)[0])

            # if the final correlation matrix exists, skip processing
            if os.path.isfile(os.path.join(path, basename + '_roi-corrs.csv')):
                continue

            # generate ROI file in register with subject's data
            roi_file = os.path.join(path, basename + '_rois.nii.gz')
            if not os.path.isfile(roi_file):
                rtn, out, err = dm.utils.run('3dresample -master {} -prefix {} -inset {}'.format(filename, roi_file, atlas))
                output = '\n'.join([out, err]).replace('\n', '\n\t')
                if rtn != 0:
                    logger.error(output)
                    raise ProcessingException('Error resampling atlas {} to match {}.'.format(atlas, filename))
                else:
                    logger.info(output)

            rois, _, _, _ = dm.utils.loadnii(roi_file)
            data, _, _, _ = dm.utils.loadnii(filename)

            n_rois = len(np.unique(rois[rois > 0]))
            dims = np.shape(data)

            # loop through all ROIs, extracting mean timeseries.
            output = np.zeros((n_rois, dims[1]))

            for i, roi in enumerate(np.unique(rois[rois > 0])):
                idx = np.where(rois == roi)[0]

                if len(idx) > 0:
                    output[i, :] = np.mean(data[idx, :], axis=0)

            # save the raw time series
            np.savetxt(os.path.join(path, basename + '_roi-timeseries.csv'), output.transpose(), delimiter=',')

            # save the full correlation matrix
            corrs = np.corrcoef(output)
            np.savetxt(os.path.join(path, basename + '_roi-corrs.csv'), corrs, delimiter=',')

def main():

    arguments   = docopt(__doc__)
    config_file = arguments['<config>']
    scanid      = arguments['--subject']
    debug       = arguments['--debug']

    logging.info('Starting')
    if debug:
        logger.setLevel(logging.DEBUG)

    with open(config_file, 'r') as stream:
        config = yaml.load(stream)

    if 'fmri' not in config['paths']:
        print("ERROR: paths:fmri not defined in {}".format(config_file))
        sys.exit(1)

    fmri_dir = config['paths']['fmri']

    if scanid:
        path = os.path.join(fmri_dir, scanid)
        try:
            run_analysis(scanid, config)
        except ProcessingException as e:
            logger.error(e)
            sys.exit(1)

    # run in batch mode
    else:
        # look for subjects with at least one fmri type missing outputs
        subjects = []

        # loop through fmri experiments defined
        for exp in config['fmri'].keys():
            expected_files = config['fmri'][exp]['conn']
            fmri_dirs = glob.glob('{}/*'.format(os.path.join(fmri_dir, exp)))

            for subj_dir in fmri_dirs:
                candidates = glob.glob('{}/*'.format(subj_dir))
                for filetype in expected_files:
                    # add subject if outputs don't already exist
                    if not filter(lambda x: '{}_roi-corrs.csv'.format(filetype) in x, candidates)
                        subjects.append(os.path.basename(subj_dir))

        # collapse found subjects (do not double-count) and create a list of commands
        commands = []
        subjects = list(set(subjects))
        for subject in subjects:
            commands.append(" ".join([__file__, config_file, '--subject {}'.format(subject)]))

        if commands:
            logger.debug('queueing up the following commands:\n'+'\n'.join(commands))

            for cmd in commands:
                jobname = 'dm_rest_{}'.format(time.strftime("%Y%m%d-%H%M%S"))
                logfile = '/tmp/{}.log'.format(jobname)
                errfile = '/tmp/{}.err'.format(jobname)
                rtn, out, err = dm.utils.run('echo {} | qsub -V -q main.q -o {} -e {} -N {}'.format(cmd, logfile, errfile, jobname))

                if rtn != 0:
                    logger.error("Job submission failed. Output follows.")
                    logger.error("stdout: {}\nstderr: {}".format(out,err))
                    sys.exit(1)

if __name__ == "__main__":
    main()

