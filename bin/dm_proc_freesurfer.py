#!/usr/bin/env python
"""
This runs freesurfer T1 images using the settings found in project_config.yml

Usage:
  dm_proc_freesurfer.py [options] <study>

Arguments:
    <study>             study name defined in master configuration .yml file

Options:
  --subject SUBJID      subject name to run on
  --debug               debug logging
  --dry-run             don't do anything
"""
from datman.docopt import docopt
import datman.scanid as sid
import datman.utils as utils
import datman.config as cfg

import os, sys
import glob
import time
import logging

logging.basicConfig(level=logging.WARN, format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

NODE = os.uname()[1]

def outputs_exist(output_dir):
    """Returns True if all expected outputs exist, else False."""
    if os.path.isfile(os.path.join(output_dir, 'scripts/recon-all.done')):
        return True
    else:
        return False

def run_freesurfer(path, config, study):
    """Finds the inputs for subject and runs freesurfer."""

    study_base = config.get_study_base(study)
    subject = os.path.basename(path)
    site = sid.parse(subject).site
    nii_dir = os.path.join(study_base, config.site_config['paths']['nii'])
    freesurfer_dir = os.path.join(study_base, config.site_config['paths']['freesurfer'])

    # don't run if the outputs already exist
    output_dir = utils.define_folder(os.path.join(freesurfer_dir, subject))
    if outputs_exist(output_dir):
        continue

    # reset / remove error.log
    error_log = os.path.join(output_dir, 'error.log')
    if os.path.isfile(error_log):
        os.remove(error_log)

    # locate T1 data
    expected_tags = config.study_config['freesurfer']['tags']
    if type(expected_tags) == str:
        expected_tags = [expected_tags]

    files = glob.glob(os.path.join(nii_dir, subject) + '/*')
    anatomicals = []
    for tag in expected_tags:
        n_expected = config.study_config['Sites'][site]['ExportInfo'][tag]['Count']
        candidates = filter(lambda x: '_{}_'.format(tag) in x, files)

        # fail if the wrong number of inputs for any tag is found (implies blacklisting is required)
        if len(candidates) != n_expected:
            error_message = "{} {}'s found, expected {} for site {}".format(len(candidates), tag, n_expected, site)
            logger.debug(error_message)
            with open(error_log, 'wb') as f:
                f.write('{}\n{}'.format(error_message, NODE))
        anatomicals.extend(candidates)

    # run freesurfer
    command = 'recon-all -all -qcache -notal-check -subjid {} '.format(subject)
    if site in config.study_config['freesurfer']['nu_iter'].keys()
        command += '-nuiterations {} '.format(config.study_config['freesurfer']['nu_iter'][site])
    for anatomical in anatomicals:
        command += '-i {} '.format(anatomical)

    rtn, out = utils.run(command)
    if rtn:
        error_message = 'freesurfer failed: {}\n{}'.format(command, out)
        logger.debug(error_message)
        with open(error_log, 'wb') as f:
            f.write('{}\n{}'.format(error_message, NODE))

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

    # check for input paths
    for k in ['nii', 'freesurfer']:
        if k not in config.site_config['paths']:
            logger.error("paths:{} not defined in site config".format(k))
            sys.exit(1)

    study_base = config.get_study_base(study)
    nii_dir = os.path.join(study_base, config.site_config['paths']['nii'])

    # single subject mode
    if scanid:
        path = os.path.join(nii_dir, scanid)
        if '_PHA_' in scanid:
            sys.exit('Subject {} if a phantom, cannot be analyzed'.format(scanid))
        try:
            run_freesurfer(path, config, study)
        except Exception as e:
            logging.error(e)
            sys.exit(1)

    # batch mode
    else:

        # update aggregate stats
        enigma_ctx = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir, 'assets/ENGIMA_ExtractCortical.sh')
        enigma_sub = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir, 'assets/ENGIMA_ExtractSubcortical.sh')
        utils.run('{} {} {}'.format(enigma_ctx, freesurfer_dir, config.study_config['STUDY_TAG']))
        utils.run('{} {} {}'.format(enigma_sub, freesurfer_dir, config.study_config['STUDY_TAG']))

        # update checklist
        #checklist_file = os.path.normpath(output_dir + '/freesurfer-checklist.csv')
        #columns = ['id', 'T1_nii', 'date_ran','qc_rator', 'qc_rating', 'notes']
        #checklist = dm.proc.load_checklist(checklist_file, columns)
        #checklist = dm.proc.add_new_subjects_to_checklist(subjects, checklist, columns)

        subjects = []
        nii_dirs = glob.glob('{}/*'.format(nii_dir))

        # find subjects where at least one expected output does not exist
        for path in nii_dirs:
            subject = os.path.basename(path)

            if sid.is_phantom(subject):
                logger.debug("Subject {} is a phantom. Skipping.".format(subject))
                continue

            freesurfer_dir = utils.define_folder(os.path.join(study_base, config.site_config['paths']['freesurfer']))
            subj_dir = os.path.join(freesurfer_dir, subject)
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
                jobname = 'dm_freesurfer_{}_{}'.format(i, time.strftime("%Y%m%d-%H%M%S"))
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

if __name__ == '__main__':
    main()

