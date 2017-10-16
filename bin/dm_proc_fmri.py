#!/usr/bin/env python
"""
This pre-processes fmri data using the settings found in project_config.yml
If subject is not defined, this runs in batch mode for all subjects.

Usage:
    dm_proc_fmri.py [options] <study>

Arguments:
    <study>          study name defined in master configuration .yml file

Options:
    --subject SUBJID subject name to run on
    --debug          debug logging
    --dry-run        don't do anything

DEPENDENCIES
    + python
    + afni
    + fsl
    + epitome
"""

from datman.docopt import docopt
import datman.scanid as sid
import datman.utils as utils
import datman.config as cfg
import yaml
import logging
import os, sys
import glob
import shutil
import tempfile
import time

logging.basicConfig(level=logging.WARN, format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

NODE = os.uname()[1]

def check_inputs(config, tag, path, expected_tags):
    """
    Ensures we have the same number of input files as we have defined in
    ExportInfo.
    """
    if not expected_tags:
        raise Exception('expected tag {} not found in {}'.format(tag, path))
    n_found = len(expected_tags)

    site = sid.parse_filename(expected_tags[0])[0].site
    tag_info = config.get_tags(site)

    try:
        if tag in tag_info:
            n_expected = tag_info.get(tag, 'Count')
        elif tag in config.study_config['Sites'][site]['links'].keys():
            n_expected = config.study_config['Sites'][site]['links'][tag]['Count']
        else:
            raise Exception
    except:
        raise Exception('tag {} not defined in Sites:site:ExportInfo or Sites:site:links'.format(tag))


    if n_found != n_expected:
        raise Exception('number of files found with tag {} was {}, expected {}'.format(tag, n_found, n_expected))

def export_directory(source, destination):
    """
    Copies a folder from a source to a destination, throwing an error if it fails.
    If the destination folder already exists, it will be removed and replaced.
    """
    if os.path.isdir(destination):
        try:
            shutil.rmtree(destination)
        except:
            raise Exception("failed to remove existing folder {}".format(destination))
    try:
        shutil.copytree(source, destination)
        logger.debug("exporting {} to {}".format(source, destination))
    except:
        raise Exception("failed to export {} to {}".format(source, destination))

def export_file(source, destination):
    """
    Copies a file from a source to a destination, throwing an error if it fails.
    """
    if not os.path.isfile(destination):
        try:
            shutil.copyfile(source, destination)
        except IOError, e:
            raise Exception('Problem exporting {} to {}'.format(source, destination))

def export_file_list(pattern, files, output_dir):
    """
    Copies, from a list of files, all files containing some substring into
    an output directory.
    """
    matches = filter(lambda x: pattern in x, files)
    for match in matches:
        output = os.path.join(output_dir, os.path.basename(match))
        try:
            export_file(match, output)
        except:
            pass

def outputs_exist(output_dir, expected_names):
    """
    Returns True if all expected outputs exist in the target directory,
    otherwise, returns false.
    """
    files = glob.glob(output_dir + '/*')
    found = 0

    for output in expected_names:
        if filter(lambda x: output in x, files):
            found += 1

    if found == len(expected_names):
        logger.debug('outputs found for output directory {}'.format(output_dir))
        return True

    return False

def run_epitome(path, config, study):
    """
    Finds the appropriate inputs for input subject, builds a temporary epitome
    folder, runs epitome, and finally copies the outputs to the fmri_dir.
    """
    study_base = config.get_study_base(study)
    subject = os.path.basename(path)
    nii_dir = os.path.join(study_base, config.site_config['paths']['nii'])
    t1_dir = os.path.join(study_base, config.site_config['paths']['hcp'])
    fmri_dir = utils.define_folder(os.path.join(study_base, config.site_config['paths']['fmri']))
    experiments = config.study_config['fmri'].keys()

    # run file collection --> epitome --> export for each study
    logger.debug('experiments found {}'.format(experiments))
    for exp in experiments:
        logger.debug('running experiment {}'.format(exp))
        # collect the files needed for each experiment
        expected_names = config.study_config['fmri'][exp]['export']
        expected_tags = config.study_config['fmri'][exp]['tags']
        output_dir = utils.define_folder(os.path.join(fmri_dir, exp, subject))

        # don't run if the outputs of epitome already exist
        if outputs_exist(output_dir, expected_names):
            continue

        # reset / remove error.log
        error_log = os.path.join(output_dir, 'error.log')
        if os.path.isfile(error_log):
            os.remove(error_log)

        failed = False

        if type(expected_tags) == str:
            expected_tags = [expected_tags]

        # locate functional data
        files = glob.glob(path + '/*')
        functionals = []
        for tag in expected_tags:
            candidates = filter(lambda x: tag in x, files)
            candidates = utils.filter_niftis(candidates)
            candidates.sort()
            logger.debug('checking functional inputs {}'.format(candidates))
            try:
                check_inputs(config, tag, path, candidates)
            except Exception as m:
                error_message = 'Did not find the correct number of fMRI inputs:\n{}'.format(m)
                logger.debug(error_message)
                with open(error_log, 'wb') as f:
                    f.write('{}\n{}'.format(error_message, NODE))
                failed = True
                break
            functionals.extend(candidates)

        # locate anatomical data
        anat_path = os.path.join(t1_dir, os.path.basename(path), 'T1w')
        files = glob.glob(anat_path + '/*')
        anatomicals = []
        for anat in ['aparc+aseg.nii.gz', 'aparc.a2009s+aseg.nii.gz', 'T1w_brain.nii.gz']:
            if not filter(lambda x: anat in x, files):
                error_message = 'expected anatomical {} not found in {}'.format(anat, anat_path)
                logger.debug(error_message)
                with open(error_log, 'wb') as f:
                    f.write('{}\n{}'.format(error_message, NODE))
                failed = True
                break
            anatomicals.append(os.path.join(anat_path, anat))

        # don't run epitome if all of the inputs do not exist
        if failed:
            continue

        # create and populate epitome directory
        epi_dir = tempfile.mkdtemp()
        utils.make_epitome_folders(epi_dir, len(functionals))
        epi_t1_dir = '{}/TEMP/SUBJ/T1/SESS01'.format(epi_dir)
        epi_func_dir = '{}/TEMP/SUBJ/FUNC/SESS01'.format(epi_dir)

        try:
            shutil.copyfile(anatomicals[0], '{}/anat_aparc_brain.nii.gz'.format(epi_t1_dir))
            shutil.copyfile(anatomicals[1], '{}/anat_aparc2009_brain.nii.gz'.format(epi_t1_dir))
            shutil.copyfile(anatomicals[2], '{}/anat_T1_brain.nii.gz'.format(epi_t1_dir))
            for i, d in enumerate(functionals):
                shutil.copyfile(d, '{}/RUN{}/FUNC.nii.gz'.format(epi_func_dir, '%02d' % (i + 1)))
        except IOError as e:
            error_message = 'unable to copy files to {}\n{}'.format(epi_dir, e)
            logger.error(error_message)
            with open(error_log, 'wb') as f:
                f.write('{}\n{}'.format(error_message, NODE))
            continue

        # collect command line options
        dims = config.study_config['fmri'][exp]['dims']
        tr = config.study_config['fmri'][exp]['tr']
        delete = config.study_config['fmri'][exp]['del']
        pipeline =  config.study_config['fmri'][exp]['pipeline']

        pipeline = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir, 'assets/{}'.format(pipeline))
        if not os.path.isfile(pipeline):
            raise Exception('invalid pipeline {} defined!'.format(pipeline))

        # run epitome
        command = '{} {} {} {} {}'.format(pipeline, epi_dir, delete, tr, dims)
        rtn, out = utils.run(command)
        if rtn:
            error_message = "epitome script failed: {}\n{}".format(command, out)
            logger.debug(error_message)
            with open(error_log, 'wb') as f:
                f.write('{}\n{}'.format(error_message, NODE))
            continue
        else:
            pass

        # export fmri data
        epitome_outputs = glob.glob(epi_func_dir + '/*')
        for name in expected_names:
            try:
                matches = filter(lambda x: 'func_' + name in x, epitome_outputs)
                matches.sort()

                # attempt to export the defined epitome stages for all runs
                if len(matches) != len(functionals):
                    error_message = 'epitome output {} not created for all inputs'.format(name)
                    logger.error(error_message)
                    with open(error_log, 'wb') as f:
                        f.write('{}\n{}'.format(error_message, NODE))
                    continue
                for i, match in enumerate(matches):
                    func_basename = utils.splitext(os.path.basename(functionals[i]))[0]
                    func_output = os.path.join(output_dir, func_basename + '_{}.nii.gz'.format(name))
                    export_file(match, func_output)

                # export all anatomical / registration information
                export_file_list('anat_', epitome_outputs, output_dir)
                export_file_list('reg_',  epitome_outputs, output_dir)
                export_file_list('mat_',  epitome_outputs, output_dir)

                # export PARAMS folder
                export_directory(os.path.join(epi_func_dir, 'PARAMS'), os.path.join(output_dir, 'PARAMS'))

            except ProcessingError as p:
                error_message = 'error exporting: {}'.format(p)
                logger.error(error_message)
                with open(error_log, 'wb') as f:
                    f.write('{}\n{}'.format(error_message, NODE))
                continue

        # remove temporary directory
        shutil.rmtree(epi_dir)

def main():
    """
    Runs fmri data through the specified epitome script.
    """
    arguments = docopt(__doc__)

    study  = arguments['<study>']
    scanid = arguments['--subject']
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

    for k in ['nii', 'fmri', 'hcp']:
        if k not in config.site_config['paths']:
            logger.error("paths:{} not defined in site config".format(k))
            sys.exit(1)

    for x in config.study_config['fmri'].iteritems():
        for k in ['dims', 'del', 'pipeline', 'tags', 'export', 'tr']:
            if k not in x[1].keys():
                logger.error("fmri:{}:{} not defined in configuration file".format(x[0], k))
                sys.exit(1)

    nii_dir = os.path.join(study_base, config.site_config['paths']['nii'])

    if scanid:
        path = os.path.join(nii_dir, scanid)
        if '_PHA_' in scanid:
            sys.exit('Subject {} if a phantom, cannot be analyzed'.format(scanid))
        try:
            run_epitome(path, config, study)
        except Exception as e:
            logging.error(e)
            sys.exit(1)

    # run in batch mode
    else:
        subjects = []
        nii_dirs = glob.glob('{}/*'.format(nii_dir))

        # find subjects where at least one expected output does not exist
        for path in nii_dirs:
            subject = os.path.basename(path)

            if sid.is_phantom(subject):
                logger.debug("Subject {} is a phantom. Skipping.".format(subject))
                continue

            fmri_dir = utils.define_folder(os.path.join(study_base, config.site_config['paths']['fmri']))
            for exp in config.study_config['fmri'].keys():
                expected_names = config.study_config['fmri'][exp]['export']
                subj_dir = os.path.join(fmri_dir, exp, subject)
                if not outputs_exist(subj_dir, expected_names):
                    subjects.append(subject)
                    break

        subjects = list(set(subjects))

        # submit a list of calls to ourself, one per subject
        commands = []
        if debug:
            debugopt = '--debug'
        else:
            debugopt = ''

        for subject in subjects:
            commands.append(" ".join(['python ', __file__, study, '--subject {} '.format(subject), debugopt]))

        if commands:
            logger.debug('queueing up the following commands:\n'+'\n'.join(commands))
            for i, cmd in enumerate(commands):
                jobname = 'dm_fmri_{}_{}'.format(i, time.strftime("%Y%m%d-%H%M%S"))
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
