#!/usr/bin/env python
"""
This analyzes imitate observe behavioural data.It could be generalized
to analyze any rapid event-related design experiment fairly easily.

Usage:
    dm_proc_imob.py [options] <study>

Arguments:
    <study>             Name of study in system-wide configuration file.

Options:
    --subject SUBJID    If given, run on a single subject
    --debug             Debug logging

DETAILS

    1) Produces AFNI and FSL-compatible GLM timing files.
    2) Runs an AFNI GLM analysis at the single-subject level.

    Each subject is run through this pipeline if the outputs do not already exist.
    Requires dm-proc-fmri.py to be complete for each subject.

DEPENDENCIES
    + afni
"""
import datman.utils as utils
import datman.config as cfg
from datman.docopt import docopt
import glob
import logging
import os, sys
import tempfile
import time
import yaml

logging.basicConfig(level=logging.WARN, format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

def check_complete(directory, subject):
    """Checks to see if the output files have been created.
    Returns True if the files exist
    """
    expected_files = ['{}_glm_IM_1stlvl_MNI-nonlin.nii.gz',
                      '{}_glm_OB_1stlvl_MNI-nonlin.nii.gz']

    for filename in expected_files:
        if not os.path.isfile(os.path.join(directory, subject, filename.format(subject))):
            return False

    return True

def generate_analysis_script(subject, inputs, input_type, config, study):
    """
    This writes the analysis script to replicate the methods in [insert paper
    here]. It expects timing files to exist (these are static, and are generated
    by 'imob-parse.py').

    Briefly, this is a standard rapid-event related design. We use 5 tent
    functions to explain each event over a 15 second window (this is the
    standard length of the HRF).

    Returns the path to the script that was generated or None if there was an
    error.
    """
    assets =  os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir, 'assets')
    study_base = config.get_study_base(study)
    subject_dir = os.path.join(study_base, config.site_config['paths']['fmri'], 'imob', subject)
    script = '{subject_dir}/{subject}_glm_1stlevel_{input_type}.sh'.format(
        subject_dir=subject_dir, subject=subject, input_type=input_type)

    IM_data = filter(lambda x: '_IMI_' in x, inputs[input_type])[0]
    OB_data = filter(lambda x: '_OBS_' in x, inputs[input_type])[0]

    f = open(script, 'wb')
    f.write("""#!/bin/bash

#
# Contrasts: emotional faces vs. fixation, emotional faces vs. neutral faces.
# use the 'bucket' dataset (*_1stlevel.nii.gz) for group level analysis.
#

# Imitate GLM for {subject}.
3dDeconvolve \\
    -input {IM_data} \\
    -mask {subject_dir}/anat_EPI_mask_MNI-nonlin.nii.gz \\
    -ortvec {subject_dir}/PARAMS/motion.datman.01.1D motion_paramaters \\
    -polort 4 \\
    -num_stimts 6 \\
    -local_times \\
    -jobs 4 \\
    -x1D {subject_dir}/{subject}_glm_IM_1stlevel_design_{input_type}.mat \\
    -stim_label 1 IM_AN -stim_times 1 {assets}/IM_event-times_AN.1D \'BLOCK(1,1)\' \\
    -stim_label 2 IM_FE -stim_times 2 {assets}/IM_event-times_FE.1D \'BLOCK(1,1)\' \\
    -stim_label 3 IM_FX -stim_times 3 {assets}/IM_event-times_FX.1D \'BLOCK(1,1)\' \\
    -stim_label 4 IM_HA -stim_times 4 {assets}/IM_event-times_HA.1D \'BLOCK(1,1)\' \\
    -stim_label 5 IM_NE -stim_times 5 {assets}/IM_event-times_NE.1D \'BLOCK(1,1)\' \\
    -stim_label 6 IM_SA -stim_times 6 {assets}/IM_event-times_SA.1D \'BLOCK(1,1)\' \\
    -gltsym 'SYM: -1*IM_FX +0*IM_NE +0.25*IM_AN +0.25*IM_FE +0.25*IM_HA +0.25*IM_SA' \\
    -glt_label 1 emot-fix \\
    -gltsym 'SYM: +0*IM_FX -1*IM_NE +0.25*IM_AN +0.25*IM_FE +0.25*IM_HA +0.25*IM_SA' \\
    -glt_label 2 emot-neut \\
    -fitts   {subject_dir}/{subject}_glm_IM_1stlvl_explained_{input_type}.nii.gz \\
    -errts   {subject_dir}/{subject}_glm_IM_1stlvl_residuals_{input_type}.nii.gz \\
    -bucket  {subject_dir}/{subject}_glm_IM_1stlvl_{input_type}.nii.gz \\
    -cbucket {subject_dir}/{subject}_glm_IM_1stlvl_allcoeffs_{input_type}.nii.gz \\
    -fout -tout -xjpeg {subject_dir}/{subject}_glm_IM_1stlevel_design_{input_type}.jpg

# Obserse GLM for {subject}.
3dDeconvolve \\
    -input {OB_data} \\
    -mask {subject_dir}/anat_EPI_mask_MNI-nonlin.nii.gz \\
    -ortvec {subject_dir}/PARAMS/motion.datman.02.1D motion_paramaters \\
    -polort 4 \\
    -num_stimts 6 \\
    -local_times \\
    -jobs 4 \\
    -x1D {subject_dir}/{subject}_glm_OB_1stlevel_design_{input_type}.mat \\
    -stim_label 1 OB_AN -stim_times 1 {assets}/OB_event-times_AN.1D \'BLOCK(1,1)\' \\
    -stim_label 2 OB_FE -stim_times 2 {assets}/OB_event-times_FE.1D \'BLOCK(1,1)\' \\
    -stim_label 3 OB_FX -stim_times 3 {assets}/OB_event-times_FX.1D \'BLOCK(1,1)\' \\
    -stim_label 4 OB_HA -stim_times 4 {assets}/OB_event-times_HA.1D \'BLOCK(1,1)\' \\
    -stim_label 5 OB_NE -stim_times 5 {assets}/OB_event-times_NE.1D \'BLOCK(1,1)\' \\
    -stim_label 6 OB_SA -stim_times 6 {assets}/OB_event-times_SA.1D \'BLOCK(1,1)\' \\
    -gltsym 'SYM: -1*OB_FX +0*OB_NE +0.25*OB_AN +0.25*OB_FE +0.25*OB_HA +0.25*OB_SA' \\
    -glt_label 1 emot-fix \\
    -gltsym 'SYM: +0*OB_FX -1*OB_NE +0.25*OB_AN +0.25*OB_FE +0.25*OB_HA +0.25*OB_SA' \\
    -glt_label 2 emot-neut \\
    -fitts   {subject_dir}/{subject}_glm_OB_1stlvl_explained_{input_type}.nii.gz \\
    -errts   {subject_dir}/{subject}_glm_OB_1stlvl_residuals_{input_type}.nii.gz \\
    -bucket  {subject_dir}/{subject}_glm_OB_1stlvl_{input_type}.nii.gz \\
    -cbucket {subject_dir}/{subject}_glm_OB_1stlvl_allcoeffs_{input_type}.nii.gz \\
    -fout -tout -xjpeg {subject_dir}/{subject}_glm_OB_1stlevel_design_{input_type}.jpg

""".format(IM_data=IM_data, OB_data=OB_data, subject_dir=subject_dir, assets=assets,
           subject=subject, input_type=input_type))
    f.close()

    return script

def get_inputs(files, config):
    """
    finds the inputs for the imob experiment (one IMI and one OBS file,
    respectively) for each epitome stage seperately.
    """
    inputs = {}
    for exported in config.study_config['fmri']['imob']['glm']:
        candidates = filter(lambda x: '{}.nii.gz'.format(exported) in x, files)
        tagged_candidates = []

        for tag in config.study_config['fmri']['imob']['tags']:
            tagged_candidates.extend(filter(lambda x: '_{}_'.format(tag) in x, candidates))

        if len(tagged_candidates) == 2:
            inputs[exported] = tagged_candidates
        else:
            raise Exception(candidates)

    return inputs

def main():
    """
    Loops through subjects, preprocessing using supplied script, and runs a
    first-level GLM using AFNI (tent functions, 15 s window) on all subjects.
    """
    arguments = docopt(__doc__)
    study     = arguments['<study>']
    subject   = arguments['--subject']
    debug     = arguments['--debug']

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
    imob_dir = os.path.join(study_base, config.site_config['paths']['fmri'], 'imob')

    # process a single subject
    if subject:

        # get required inputs from each
        files = glob.glob(os.path.join(imob_dir, subject) + '/*.nii.gz')
        inputs = get_inputs(files, config)

        # check if subject has already been processed
        if check_complete(imob_dir, subject):
            logger.info('{} already analysed'.format(subject))
            sys.exit(0)

        # first level GLM for inputs
        for input_type in inputs.keys():
            script = generate_analysis_script(subject, inputs, input_type, config, study)
            rtn, out = utils.run('chmod 754 {script}; {script}'.format(script=script))
            if rtn:
                logger.error('Failed to analyze {}\n{}'.format(subject, out))
                sys.exit(1)

    # process all subjects
    else:
        commands = []
        for path in glob.glob('{}/*'.format(imob_dir)):
            subject = os.path.basename(path)

            # add subject if any of the expected outputs do not exist
            files = glob.glob(os.path.join(imob_dir, subject) + '/*.nii.gz')
            try:
                inputs = get_inputs(files, config)
            except:
                logger.debug('Invalid inputs for {}'.format(subject))
                continue
            expected = inputs.keys()

            for exp in expected:
                if not filter(lambda x: '{}_glm_IM_1stlvl_{}'.format(subject, exp) in x, files):
                    commands.append(" ".join([__file__, study, '--subject {}'.format(subject)]))
                    break

        if commands:
            logger.debug("queueing up the following commands:\n"+'\n'.join(commands))
            #fd, path = tempfile.mkstemp()
            #os.write(fd, '\n'.join(commands))
            #os.close(fd)
            for cmd in commands:
                jobname = "dm_imob_{}".format(time.strftime("%Y%m%d-%H%M%S"))
                logfile = '/tmp/{}.log'.format(jobname)
                errfile = '/tmp/{}.err'.format(jobname)
                rtn, out = utils.run('echo {} | qsub -V -q main.q -o {} -e {} -N {}'.format(cmd, logfile, errfile, jobname))
                #rtn, out, err = utils.run('qbatch -i --logdir {logdir} -N {name} --walltime {wt} {cmds}'.format(logdir = log_path, name = jobname, wt = walltime, cmds = path))

                if rtn:
                    logger.error("Job submission failed. Output follows.")
                    logger.error("stdout: {}".format(out))
                    sys.exit(1)

if __name__ == "__main__":
    main()

