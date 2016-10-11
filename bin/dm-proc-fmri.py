#!/usr/bin/env python
"""
This pre-processes fmri data using the settings found in project_config.yml
If subject is not defined, this runs in batch mode for all subjects.

Usage:
    dm-proc-fmri.py [options] <config>

Arguments:
    <config>         configuration .yml file

Options:
    --subject SUBJID subject name to run on
    -v,--verbose     verbose logging
    --debug          debug logging
    --dry-run        don't do anything

DEPENDENCIES
    + python
    + afni
    + fsl
    + epitome
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

logging.basicConfig(level=logging.WARN, format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

class MissingDataException(Exception):
    pass


class ProcessingException(Exception):
    pass

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

def check_inputs(config, path, expected_tags):
    """
    Ensures we have the same number of input files as we have defined in
    ExportInfo.
    """
    if not candidates:
        print('ERROR: expected tag {} not found in {}'.format(tag, path))
        sys.exit(1)
    n_found = len(candidates)

    site = dm.scanid.parse_filename(candidates[0])[0].site
    n_expected = config['Sites'][site]['ExportInfo'][tag]['Count']

    if n_found != n_expected:
        print('ERROR: number of files found with tag {} was {}, expected {}'.format(tag, n_found, n_expected))
        sys.exit(1)

def run_epitome(path, config):
    """
    Finds the appropriate inputs for input subject, builds a temporary epitome
    folder, runs epitome, and finally copies the outputs to the fmri_dir.
    """

    nii_dir = config['paths']['nii']
    t1_dir = config['paths']['hcp']
    fmri_dir = dm.utils.define_folder(config['paths']['fmri'])
    experiments = config['fmri'].keys()

    # collect the files needed for each experiment
    for exp in experiments:
        expected_names = config['fmri'][exp]['export']
        expected_tags = config['fmri'][exp]['tags']

        if type(expected_tags) == str:
            expected_tags = [expected_tags]

        # locate functional data
        files = glob.glob(path + '/*')
        functionals = []
        for tag in expected_tags:
            candidates = filter(lambda x: tag in x, files)
            candidates.sort()
            check_inputs(config, path, candidates)
            functionals.extend(candidates)

        # locate anatomical data
        anat_path = os.path.join(t1_dir, os.path.basename(path), 'T1w')
        files = glob.glob(anat_path + '/*')
        anatomicals = []
        for anat in ['aparc+aseg.nii.gz', 'aparc.a2009s+aseg.nii.gz', 'T1w_brain.nii.gz']:
            if not filter(lambda x: anat in x, files):
                print('ERROR: expected anatomical {} not found in {}'.format(anat, anat_path))
                sys.exit(1)
            anatomicals.append(os.path.join(anat_path, anat))

        # locate outputs
        files = glob.glob(os.path.join(fmri_dir, exp) + '/*')
        found = 0
        for output in expected_names:
            if filter(lambda x: output in x, files):
                found += 1
        if found == len(expected_names):
            sys.exit('All expected outputs found, exiting')

        # create and populate epitome directory
        epi_dir = tempfile.mkdtemp()
        dm.utils.make_epitome_folders(epi_dir, len(rest_data))
        epi_t1_dir = '{}/TEMP/SUBJ/T1/SESS01'.format(tmpfolder)
        epi_func_dir = '{}/TEMP/SUBJ/FUNC/SESS01'.format(tmpfolder)

        try:
            shutil.copyfile(anatomicals[0], '{}/anat_aparc_brain.nii.gz'.format(epi_t1_dir))
            shutil.copyfile(anatomicals[1], '{}/anat_aparc2009_brain.nii.gz'.format(epi_t1_dir))
            shutil.copyfile(anatomicals[2], '{}/anat_T1_brain.nii.gz'.format(epi_t1_dir))
            for i, d in enumerate(functionals):
                shutil.copyfile(d, '{}/RUN{}/FUNC.nii.gz'.format(epi_func_dir, '%02d' % (i + 1)))
        except IOError, e:
            raise ProcessingException("Problem copying files to epitome temp folder")

        # collect command line options
        dims = config['fmri'][exp]['dims']
        tr = config['fmri'][exp]['tr']
        delete = config['fmri'][exp]['del']
        pipeline =  config['fmri'][exp]['type']

        if pipeline == 'rest':
            pipeline = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir, 'assets/rest.sh'
        elif pipeline == 'task':
            pipeline = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir, 'assets/task.sh'
        else:
            print('ERROR: invalid pipeline {} defined!'.format(pipeline))
            sys.exit(1)
        command = '{} {} {} {} {}'.format(pipeline, epi_dir, delete, tr, dims)

        # run the command
        rtn, out, err = dm.utils.run(command, dryrun=True)
        output = '\n'.join([out, err]).replace('\n', '\n\t')
        if rtn != 0:
            print(output)
            raise ProcessingException("Trouble running preprocessing data")
        else:
            print(output)

        # export outputs

        # remove temporary directory
        shutil.rmtree(epi_dir)

def main():
    """
    Runs fmri data through the specified epitome script.
    """
    arguments = docopt(__doc__)

    config_file = arguments['<config>']
    scanid      = arguments['--subject']
    verbose     = arguments['--verbose']
    debug       = arguments['--debug']
    dryrun      = arguments['--dry-run']

    if verbose:
        logger.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)

    if not os.path.isfile(script.split(' ')[0]):
        logger.error("Epitome script {} does not exist".format(script.split(' ')[0]))
        sys.exit(1)

    with open(config_file, 'r') as stream:
        config = yaml.load(stream)

    for k in ['nii', 'fmri', 'hcp']:
        if k not in config['paths']:
            print("ERROR: paths:{} not defined in {}".format(k, config_file))
            sys.exit(1)

    for x in config['fmri'].iteritems():
        for k in ['dims', 'del', 'type', 'tags', 'export', 'tr']:
            if k not in x[1].keys():
                print("ERROR: fmri:{}:{} not defined in {}".format(x[0], k, config_file))

    nii_dir = config['paths']['nii']

    if scanid:
        path = os.path.join(nii_dir, scanid)
        if '_PHA_' in scanid:
            sys.exit('Subject {} if a phantom, cannot be analyzed'.format(scanid))
        run_epitome(path, config)

    commands = []
    for subject in
    for subject in (subjects or dm.utils.get_subjects(nii_path)):
        if is_complete(outputdir, subject):
            logger.info("Subject {} already processed. Skipping.".format(subject))
            continue

        if dm.scanid.is_phantom(subject):
            logger.debug("Subject {} is a phantom. Skipping.".format(subject))
            continue

        try:
            data = get_required_data(data_path, fsdir, subject, tags)
        except MissingDataException, e:
            logger.error(e.message)
            continue

        # if this command was called with an explicit list of subjects, process
        # them now
        if subjects:
            logger.info("Processing subject {}".format(subject))
            if not dryrun:
                process_subject(func_path, log_path, data, subject, tags, atlas, script)


        # otherwise, submit a list of calls to ourself, one per subject
        else:
            opts = '{verbose} {debug} {tags}'.format(
                verbose = (verbose and ' --verbose' or ''),
                debug = (debug and ' --debug' or ''),
                tags = (tags and ' --tags=' + ','.join(tags) or ''))

            commands.append(" ".join([__file__, opts, datadir, fsdir,
                outputdir, script, atlas, subject]))

    if commands:
        logger.debug("queueing up the following commands:\n"+'\n'.join(commands))
        jobname = "dm_rest_{}".format(time.strftime("%Y%m%d-%H%M%S"))
        log_path = dm.utils.define_folder(os.path.join(outputdir, 'logs'))

        fd, path = tempfile.mkstemp()
        os.write(fd, '\n'.join(commands))
        os.close(fd)

        rtn, out, err = dm.utils.run('qbatch -i --logdir {logdir} -N {name} --walltime {wt} {cmds}'.format(
            logdir = log_path,
            name = jobname,
            wt = walltime,
            cmds = path), dryrun = dryrun)

        if rtn != 0:
            logger.error("Job submission failed. Output follows.")
            logger.error("stdout: {}\nstderr: {}".format(out,err))
            sys.exit(1)

if __name__ == "__main__":
    main()

