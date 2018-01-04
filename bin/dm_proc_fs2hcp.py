#!/usr/bin/env python
"""
This will convert freesurfer outputs to hcp workbench-compatible format.

Usage:
  dm_proc_fs2hcp.py [options] <study>

Arguments:
    <study>            study name defined in master configuration .yml file

Options:
  --subject SUBJID     subject name to run on
  --debug              debug logging
  --dry-run            don't do anything
"""
from datman.docopt import docopt
import datman.scanid as sid
import datman.utils as utils
import datman.config as cfg
import logging
import logging.handlers


import glob
import os, sys
import datetime
import tempfile
import shutil
import filecmp
import difflib

logging.basicConfig(level=logging.WARN, format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

DRYRUN = False
PARALLEL = False
NODE = os.uname()[1]
LOG_DIR = None


def outputs_exist(subject_dir):
    """True if a late-stage output of fs2hcp.py is found, else False"""
    subject = os.path.basename(subject_dir)
    test_file = os.path.join(subject_dir, 'MNINonLinear', '{}.164k_fs_LR.wb.spec'.format(subject))
    if os.path.isfile(test_file):
        return True
    else:
        return False

def run_hcp_convert(path, config, study):
    """Runs fs2hcp on the input subject"""
    study_base = config.get_study_base(study)
    subject = os.path.basename(path)
    freesurfer_dir = config.get_path('freesurfer')
    hcp_dir =       config.get_path('hcp')
    output_dir = os.path.join(hcp_dir, subject)

    # run fs2hcp
    #command = 'fs2hcp --FSpath={} --HCPpath={} --subject={}'.format(freesurfer_dir, hcp_dir, subject)
    command = 'ciftify_recon_all --fs-subjects-dir {} --hcp-data-dir {} {}'.format(freesurfer_dir, hcp_dir, subject)
    rtn, out = utils.run(command)
    if rtn:
        error_message = "fs2hcp failed: {}\n{}".format(command, out)
        logger.debug(error_message)

    command2 = 'cifti_vis_recon_all snaps --hcp-data-dir {} {}'.format(hcp_dir, subject)
    rtn, out = utils.run(command2)
    if rtn:
        error_message = "fs2hcp failed: {}\n{}".format(command2, out)
        logger.debug(error_message)

def main():
    arguments = docopt(__doc__)
    study     = arguments['<study>']
    scanid    = arguments['--subject']
    debug     = arguments['--debug']
    dryrun    = arguments['--dry-run']

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

    for k in ['freesurfer', 'hcp']:
        if k not in config.site_config['paths']:
            logger.error("paths:{} not defined in site config".format(k))
            sys.exit(1)

    freesurfer_dir = os.path.join(study_base, config.site_config['paths']['freesurfer'])
    hcp_dir = os.path.join(study_base, config.site_config['paths']['hcp'])

    if scanid:
        path = os.path.join(freesurfer_dir, scanid)
        try:
            run_hcp_convert(path, config, study)
        except Exception as e:
            logging.error(e)
            sys.exit(1)

    # run in batch mode
    else:
        subjects = []
        freesurfer_dirs = glob.glob('{}/*'.format(freesurfer_dir))

        # find subjects where at least one expected output does not exist
        for path in nii_dirs:
            subject = os.path.basename(path)

            hcp_dir = utils.define_folder(os.path.join(study_base, config.site_config['paths']['hcp']))
            if not outputs_exist(subj_dir):
                subjects.append(subject)

        subjects = list(set(subjects))

        # submit a list of calls to ourself, one per subject
        commands = []
        if debug:
            debugopt = '--debug'
        else:
            debugopt = ''

        for subject in subjects:
            commands.append(" ".join([__file__, study, '--subject {} '.format(subject), debugopt]))

        if commands:
            logger.debug('queueing up the following commands:\n'+'\n'.join(commands))
            for i, cmd in enumerate(commands):
                jobname = 'dm_fs2hcp_{}_{}'.format(i, time.strftime("%Y%m%d-%H%M%S"))
                jobfile = '/tmp/{}'.format(jobname)
                logfile = '/tmp/{}.log'.format(jobname)
                errfile = '/tmp/{}.err'.format(jobname)
                with open(jobfile, 'wb') as fid:
                    fid.write('#!/bin/bash\n')
                    fid.write(cmd)

                rtn, out = utils.run('qsub -V -q main.q -o {} -e {} -N {} {}'.format(
                    logfile, errfile, jobname, jobfile))
                #rtn, out = utils.run('echo bash -l {}/{} {} | qbatch -N {} --logdir {} --walltime {} -'.format(bin_dir, script, subid, jobname, logs_dir, walltime))
                if rtn:
                    logger.error("Job submission failed. Output follows.")
                    logger.error("stdout: {}".format(out))
                    sys.exit(1)

if __name__ == '__main__':
    main()
