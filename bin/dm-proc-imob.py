#!/usr/bin/env python
"""
This analyzes imitate observe behavioural data.It could be generalized
to analyze any rapid event-related design experiment fairly easily.

Usage:
    dm-proc-imob.py [options] <config>

Arguments:
    <config>            Configuration file.

Options:
    --subject SUBJID    If given, run on a single subject
    -v,--verbose        Verbose logging
    --debug             Debug logging

DETAILS

    1) Produces AFNI and FSL-compatible GLM timing files.
    2) Runs an AFNI GLM analysis at the single-subject level.

    Each subject is run through this pipeline if the outputs do not already exist.
    Requires dm-proc-fmri.py to be complete for each subject.

DEPENDENCIES

    + python
    + afni
    + fsl
"""

from datman.docopt import docopt
from glob import glob
from random import choice
from string import ascii_uppercase, digits
import datman as dm
import logging
import os
import shutil
import sys
import tempfile
import time

logging.basicConfig(level=logging.WARN, format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

def generate_analysis_script(sub, func_path, assets):
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
    # first, determine input functional files
    IM_data = glob('{path}/{sub}/*.IM.*.nii.gz'.format(path=func_path, sub=sub))
    OB_data = glob('{path}/{sub}/*.OB.*.nii.gz'.format(path=func_path, sub=sub))
    if not (IM_data or OB_data):
        logger.error("Missing IM or OB imob data for sub {}. Skipping.".format(sub))
        return None

    IM_data = IM_data[0]
    OB_data = OB_data[0]

    # open up the master script, write common variables
    script = '{func_path}/{sub}/{sub}_glm_1stlevel_cmd.sh'.format(func_path=func_path, sub=sub)

    f = open(script, 'wb')
    f.write("""#!/bin/bash

#
# Contrasts: emotional faces vs. fixation, emotional faces vs. neutral faces.
# use the 'bucket' dataset (*_1stlevel.nii.gz) for group level analysis.
#

# Imitate GLM for {sub}.
3dDeconvolve \\
    -input {IM_data} \\
    -mask {func_path}/{sub}/{sub}_anat_EPI_mask_MNI.nii.gz \\
    -ortvec {func_path}/{sub}/{sub}_motion.1D motion_paramaters \\
    -polort 4 \\
    -num_stimts 6 \\
    -local_times \\
    -jobs 8 \\
    -x1D {func_path}/{sub}/{sub}_glm_IM_1stlevel_design.mat \\
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
    -fitts   {func_path}/{sub}/{sub}_glm_IM_1stlvl_explained.nii.gz \\
    -errts   {func_path}/{sub}/{sub}_glm_IM_1stlvl_residuals.nii.gz \\
    -bucket  {func_path}/{sub}/{sub}_glm_IM_1stlvl.nii.gz \\
    -cbucket {func_path}/{sub}/{sub}_glm_IM_1stlvl_allcoeffs.nii.gz \\
    -fout -tout -xjpeg {func_path}/{sub}/{sub}_glm_IM_1stlevel_design.jpg

# Obserse GLM for {sub}.
3dDeconvolve \\
    -input {OB_data} \\
    -mask {func_path}/{sub}/{sub}_anat_EPI_mask_MNI.nii.gz \\
    -ortvec {func_path}/{sub}/{sub}_motion.1D motion_paramaters \\
    -polort 4 \\
    -num_stimts 6 \\
    -local_times \\
    -jobs 8 \\
    -x1D {func_path}/{sub}/{sub}_glm_OB_1stlevel_design.mat \\
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
    -fitts   {func_path}/{sub}/{sub}_glm_OB_1stlvl_explained.nii.gz \\
    -errts   {func_path}/{sub}/{sub}_glm_OB_1stlvl_residuals.nii.gz \\
    -bucket  {func_path}/{sub}/{sub}_glm_OB_1stlvl.nii.gz \\
    -cbucket {func_path}/{sub}/{sub}_glm_OB_1stlvl_allcoeffs.nii.gz \\
    -fout -tout -xjpeg {func_path}/{sub}/{sub}_glm_OB_1stlevel_design.jpg

""".format(IM_data=IM_data, OB_data=OB_data, func_path=func_path, assets=assets, sub=sub))
    f.close()

    return script

def main():
    """
    Loops through subjects, preprocessing using supplied script, and runs a
    first-level GLM using AFNI (tent functions, 15 s window) on all subjects.
    """
    arguments  = docopt(__doc__)
    datadir    = arguments['<datadir>']
    fsdir      = arguments['<fsdir>']
    outputdir  = arguments['<outputdir>']
    script     = arguments['<script>']
    assets     = arguments['<assets>']
    sub        = arguments['<subject>']
    walltime   = arguments['--walltime']
    verbose    = arguments['--verbose']
    debug      = arguments['--debug']
    dryrun     = arguments['--dry-run']

    if verbose:
        logger.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)

    data_path = dm.utils.define_folder(datadir)
    nii_path = dm.utils.define_folder(os.path.join(data_path, 'nii'))
    func_path = dm.utils.define_folder(outputdir)
    log_path = dm.utils.define_folder(os.path.join(outputdir, 'logs'))

    # process a single subject
    if sub:
        if dm.scanid.is_phantom(sub):
            logger.debug("Scan {} is a phantom. Skipping".format(sub))
            sys.exit(0)
        if os.path.isfile(os.path.join(func_path, '{sub}/{sub}_preproc-complete.log'.format(sub=sub))):
            logger.debug("Scan {} has already been preprocessed. Skipping".format(sub))
        else:
            try:
                logger.info("Preprocessing subject {}".format(sub))
                tmp_path = tempfile.mkdtemp()
                tempdir = process_functional_data(sub, nii_path, fsdir, func_path, log_path, tmp_path, script)
                export_data(sub, tempdir, func_path)
            except Exception, e:
                logger.exception("Error during preprocessing. Exiting")
                sys.exit(1)

        # analyze
        if os.path.isfile(os.path.join(func_path, '{sub}/{sub}_analysis-complete.log'.format(sub=sub))):
            logger.debug("Scan {} has already been analyzed. Skipping".format(sub))
        else:
            try:
                logger.info("Analyzing subject {}".format(sub))
                script = generate_analysis_script(sub, func_path, assets)
                if script:
                    returncode, _, _ = dm.utils.run('bash {}'.format(script))
                    dm.utils.check_returncode(returncode)
                    dm.utils.run('touch {func_path}/{sub}/{sub}_analysis-complete.log'.format(func_path=func_path, sub=sub))
            except:
                logger.exception('Failed analyze {}'.format(sub))
                sys.exit(1)

    # process all subjects
    else:
        commands = []
        for sub in dm.utils.get_subjects(nii_path):
            if dm.scanid.is_phantom(sub):
                logger.debug("Scan {} is a phantom. Skipping".format(sub))
                continue
            if os.path.isfile('{func_path}/{sub}/{sub}_analysis-complete.log'.format(func_path=func_path, sub=sub)):
                continue

            opts = (verbose and ' -v' or '') + (debug and ' --debug' or '')
            commands.append(" ".join([__file__, opts, datadir, fsdir,
                outputdir, script, assets, sub]))

        if commands:
            logger.debug("queueing up the following commands:\n"+'\n'.join(commands))
            jobname = "dm_imob_{}".format(time.strftime("%Y%m%d-%H%M%S"))
            fd, path = tempfile.mkstemp()
            os.write(fd, '\n'.join(commands))
            os.close(fd)

            # using qbatch -i (individual jobs) rather than the default array
            # job to work around interaction between epitome scripts and PBS
            # tempdir names.
            #
            # Specifically, PBS makes a parent tempdir for array jobs that
            # include the array element in the name, like so:
            #    /tmp/150358[1].mgmt2.scc.camh.net/tmp1H2Une
            #
            # Epitome scripts do not properly escape the DIR_DATA when used, so
            # references to this path do not parse correctly (square brackets
            # being patterns in bash).
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
