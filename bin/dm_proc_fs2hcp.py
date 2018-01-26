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
import time
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


def ciftify_outputs_exist(subject_dir):
    """True if a late-stage output of ciftify_recon_all is found, else False"""
    subject = os.path.basename(subject_dir)
    test_file = os.path.join(subject_dir, 'MNINonLinear', '{}.164k_fs_LR.wb.spec'.format(subject))
    if os.path.isfile(test_file):
        return True
    else:
        return False

def make_error_log_dir(hcp_path):
    log_dir = os.path.join(hcp_path, 'logs')
    try:
        if not DRYRUN:
            os.mkdir(log_dir)
    except:
        pass
    return log_dir

def fs_outputs_exist(output_dir):
    """
    Will return false as long as a freesurfer 'recon-all.done" file exists in
    the 'scripts' folder exists. This indicates that freesurfer finished without errors
    """
    return os.path.exists(os.path.join(output_dir, 'scripts', 'recon-all.done'))

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
        error_message = "ciftify_recon_all failed: {}\n{}".format(command, out)
        logger.debug(error_message)

    command2 = 'cifti_vis_recon_all snaps --hcp-data-dir {} {}'.format(hcp_dir, subject)
    rtn, out = utils.run(command2)
    if rtn:
        error_message = "cifti_vis_recon_all snaps failed: {}\n{}".format(command2, out)
        logger.debug(error_message)

def create_indices_bm(config, study):
    hcp_dir = config.get_path('hcp')
    if os.path.exists(os.path.join(hcp_dir, 'qc_recon_all')):
        command = 'cifti_vis_recon_all index --hcp-data-dir {}'.format(hcp_dir)
        rtn, out = utils.run(command)
        if rtn:
            error_message = "qc index creation failed: {}\n{}".format(command, out)
            logger.debug(error_message)
    else:
        logger.debug('qc_recon_all directory does not exist, not generating index')


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

    freesurfer_dir = config.get_path('freesurfer')
    hcp_dir = config.get_path('hcp')
    logs_dir = make_error_log_dir(hcp_dir)

    if scanid:
        path = os.path.join(freesurfer_dir, scanid)
        try:
            run_hcp_convert(path, config, study)
        except Exception as e:
            logging.error(e)
            sys.exit(1)
        return

    qced_subjects = config.get_subject_metadata()

# running for batch mode

    new_subjects = []
    # find subjects where at least one expected output does not exist
    for subject in qced_subjects:
        subj_dir = os.path.join(hcp_dir, subject)
        if not ciftify_outputs_exist(subj_dir):
            if fs_outputs_exist(os.path.join(freesurfer_dir, subject)):
                new_subjects.append(subject)

    create_indices_bm(config, study)

    # submit a list of calls to ourself, one per subject
    commands = []
    if debug:
        debugopt = '--debug'
    else:
        debugopt = ''

    for subject in new_subjects:
        commands.append(" ".join([__file__, study, '--subject {} '.format(subject), debugopt]))

    if commands:
        logger.debug('queueing up the following commands:\n'+'\n'.join(commands))

    for i, cmd in enumerate(commands):
        job_name = 'dm_fs2hcp_{}_{}'.format(i, time.strftime("%Y%m%d-%H%M%S"))
        utils.submit_job(cmd, job_name, logs_dir,
            system = config.system, dryrun = dryrun)


if __name__ == '__main__':
    main()
