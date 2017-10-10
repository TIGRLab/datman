#!/usr/bin/env python
"""
Runs unring.py on nrrd files with the specified tags.

If run without --batch specified, will submit itself to the queue in batch mode.
In batch mode, will run each subject with no outputs serially (due to MATLAB
licenses).

Usage:
    dm_proc_unring.py [options] <study>

Arguments:
    <study>          study name defined in master configuration .yml file

Options:
    --batch          run all found files in serial
    --debug          debug logging
    --dry-run        don't do anything

DEPENDENCIES
    + unring.py
    + matlab
"""

from datman.docopt import docopt
import datman.utils as utils
import datman.config as cfg
import logging
import os, sys
import time

logging.basicConfig(level=logging.WARN, format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

NODE = os.uname()[1]

def select_inputs(inputs, expected_tags):
    """
    Filters the list of input files to only include those with tags defined in
    the study config.
    """
    accepted_inputs = []
    for tag in expected_tags:
        matching_inputs = filter(lambda x: tag in x, inputs)
        accepted_inputs.extend(matching_inputs)

    logger.debug('found the following inputs for unring.py:\n{}'.format(accepted_inputs))

    return(accepted_inputs)


def outputs_exist(output_dir, input_file):
    """Returns True if outputs exist in the target directory."""
    outputs = os.listdir(output_dir)

    if input_file in outputs:
        logger.debug('output {} found'.format(input_file))
        return True
    else:
        return False


def run_all(nrrd_dir, config, study):
    """Finds all non-phantom input nrrds and run unring.py in serial."""
    study_base = config.get_study_base(study)
    subjects = os.listdir(nrrd_dir)
    subjects = filter(lambda x: '_PHA_' not in x, subjects)
    unring_dir = utils.define_folder(os.path.join(study_base, config.site_config['paths']['unring']))
    tags = config.study_config['unring']['tags']

    for subject in subjects:
        output_dir = utils.define_folder(os.path.join(unring_dir, subject))
        inputs = os.listdir(os.path.join(nrrd_dir, subject))
        inputs = select_inputs(inputs, tags) # selects inputs with matching tag

        for input_file in inputs:

            # don't run if the outputs of unring already exist
            if outputs_exist(output_dir, input_file):
                continue

            # reset / remove error.log
            error_log = os.path.join(output_dir, 'error.log')
            if os.path.isfile(error_log):
                os.remove(error_log)

            output_fname = os.path.join(output_dir, input_file)
            input_fname = os.path.join(nrrd_dir, subject, input_file)
            cmd = 'unring.py {} {} -v'.format(input_fname, output_fname)
            logger.debug('running {}'.format(cmd))
            rtn, out = utils.run(cmd)
            if rtn:
                error_message = "unring.py failed: {}\n{}".format(cmd, out)
                logger.info(error_message)
                with open(error_log, 'wb') as f:
                    f.write('{}\n{}'.format(error_message, NODE))
                continue
            else:
                pass


def main():
    """
    Runs .nrrd data through unring.py.
    """
    arguments = docopt(__doc__)

    study  = arguments['<study>']
    batch  = arguments['--batch']
    debug  = arguments['--debug']
    dryrun = arguments['--dry-run']

    # configure logging
    logging.info('Starting')
    if debug:
        logger.setLevel(logging.DEBUG)

    # load config for study
    try:
        config = cfg.config(study=study)
    except ValueError:
        logger.error('study {} not defined'.format(study))
        sys.exit(1)

    study_base = config.get_study_base(study)

    for k in ['nrrd']:
        if k not in config.site_config['paths']:
            logger.error("paths:{} not defined in site config".format(k))
            sys.exit(1)

    nrrd_dir = os.path.join(study_base, config.site_config['paths']['nrrd'])

    # runs in serial (due to MATLAB dependencies)
    if batch:
        try:
            run_all(nrrd_dir, config, study)
        except Exception as e:
            logging.error(e)
            sys.exit(1)

    # default behaviour: submit self to queue in batch mode
    else:
        if debug:
            debugopt = '--debug'
        else:
            debugopt = ''

        cmd = 'python {} {} --batch {}'.format(__file__, study, debugopt)
        jobname = 'dm_unring_{}'.format(time.strftime("%Y%m%d-%H%M%S"))
        jobfile = '/tmp/{}'.format(jobname)
        logfile = '/tmp/{}.log'.format(jobname)
        errfile = '/tmp/{}.err'.format(jobname)

        with open(jobfile, 'wb') as fid:
            fid.write('#!/bin/bash\n')
            fid.write(cmd)

            rtn, out = utils.run('qsub -V -q main.q -o {} -e {} -N {} {}'.format(
                logfile, errfile, jobname, jobfile))

            if rtn:
                logger.error("Job submission failed. Output follows.")
                logger.error("stdout: {}".format(out))
                sys.exit(1)


if __name__ == "__main__":
    main()

