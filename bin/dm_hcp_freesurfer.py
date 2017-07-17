#!/usr/bin/env python
"""
Runs the full HCP pipelines FreeSurfer pipeline. This generates myelin maps as
part of the outputs.

Usage:
    dm_hcp_freesurfer.py [options] <study>
    dm_hcp_freesurfer.py [options] <study> <subject> <T1> <T2>

Arguments:
    <study>         The name of a datman project. Will find and submit all
                    subjects that do not already have a complete set of outputs
    <subject>       The ID of a specific subject to run (instead of running in
                    batch mode)
    <T1>            The full path to a subject's T1 nifti
    <T2>            The full path to a subject's T2 nifti

Options:
    --t1-tag STR        The tag used to identify T1 files in batch mode.
                        [default: T1]
    --t2-tag STR        The tag used to identify T2 files in batch mode.
                        [default: T2]
    --blacklist FILE    The path to a blacklist specific to this pipeline. The
                        blacklist should be a list of file names to ignore (not
                        full paths), one file per line. Only files that may
                        match the T1 or T2 tag need to be blacklisted. Note that
                        the study specific blacklist will be consulted first
                        even if this option is not set.
    --debug
    --dry-run
"""
import os
import sys
import glob
import time
import logging

from datman.docopt import docopt
import datman.utils as utils
import datman.config
import datman.scan
import datman.scanid as scanid

logging.basicConfig(level=logging.WARN,
        format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

DRYRUN = False

def main():
    global DRYRUN
    arguments = docopt(__doc__)
    study = arguments['<study>']
    subject = arguments['<subject>']
    debug = arguments['--debug']
    DRYRUN = arguments['--dry-run']

    if debug:
        logger.setLevel(logging.DEBUG)

    check_environment()
    config = datman.config.config(study=study)

    if subject:
        run_pipeline(config, subject, arguments['<T1>'], arguments['<T2>'])
        return

    run_all_subjects(config, arguments)

def check_environment():
    try:
        utils.check_dependency_configured('FSL', shell_cmd='fsl',
                env_vars=['FSLDIR'])
        utils.check_dependency_configured('FreeSurfer', shell_cmd='recon-all',
                env_vars=['FREESURFER_HOME'])
        utils.check_dependency_configured('Connectome-Workbench',
                shell_cmd='wb_command')
        utils.check_dependency_configured('HCP pipelines', env_vars=['HCPPIPEDIR',
                'HCPPIPEDIR_Config', 'HCPPIPEDIR_FS', 'HCPPIPEDIR_Global',
                'HCPPIPEDIR_PostFS', 'HCPPIPEDIR_PreFS', 'HCPPIPEDIR_Templates'])
    except EnvironmentError as e:
        logger.error(e.message)
        sys.exit(1)

def run_pipeline(config, subject, t1, t2):
    if not input_exists(t1) or not input_exists(t2):
        sys.exit(1)
    base_dir = utils.define_folder(config.get_path('hcp_fs'))
    hcp_pipeline = "hcp-freesurfer.sh {} {} {} {}".format(base_dir, subject,
            t1, t2)
    rtn, out = utils.run(hcp_pipeline, dryrun=DRYRUN)
    if rtn:
        logger.error("hcp-freesurfer.sh exited with non-zero status code. "
                "Output: {}".format(out))

def input_exists(anat_input):
    if not os.path.exists(anat_input):
        logger.error("Input file does not exist: {}".format(anat_input))
        return False
    return True

def run_all_subjects(config, arguments):
    t1_tag = arguments['--t1-tag']
    t2_tag = arguments['--t2-tag']
    blacklist_file = arguments['--blacklist']

    subjects = config.get_subject_metadata()
    if blacklist_file:
        subjects = add_pipeline_blacklist(subjects, blacklist_file)

    # Update FS log ?
    commands = []
    for subject in subjects:
        if is_completed(subject, config.get_path('hcp_fs')):
            continue
        if is_started(subject, config.get_path('hcp_fs')):
            logger.debug("{} has partial outputs and may still be running. "
                    "Skipping".format(subject))
            continue

        scan = datman.scan.Scan(subject, config)
        blacklisted_files = subjects[subject]
        try:
            t1 = get_anatomical_file(scan, t1_tag, blacklisted_files)
            t2 = get_anatomical_file(scan, t2_tag, blacklisted_files)
        except ValueError as e:
            logger.error("Skipping subject. Reason: {}".format(e.message))
            continue
        cmd = create_command(config.study, subject, t1, t2, arguments)
        submit_job(cmd, subject)

def add_pipeline_blacklist(subjects, blacklist_file):
    if not os.path.exists(blacklist_file):
        logger.error("The given pipeline specific blacklist does not exist: "
                "{}".format(blacklist_file))
        sys.exit(1)

    try:
        with open(blacklist_file, 'r') as blacklist_data:
            blacklist = blacklist_data.readlines()
    except IOError:
        logger.error("Cannot read blacklist {}".format(blacklist_file))
        sys.exit(1)

    for entry in blacklist:
        entry = os.path.basename(entry)
        entry = entry.replace('.nii', '').replace('.gz', '').strip()
        try:
            ident, tag, _, _ = scanid.parse_filename(entry)
        except scanid.ParseException:
            logger.debug("Cannot parse blacklist entry: {}. "
                    "Skipping.".format(entry))
            continue

        subid = ident.get_full_subjectid_with_timepoint()
        try:
            subjects[subid].append(entry)
        except IndexError:
            logger.debug("Blacklisted item given for subject not signed off on "
                    "in study's checklist.csv. Ignoring entry {}".format(entry))
            continue
    return subjects

def is_completed(subject, pipeline_dir):
    fs_scripts = os.path.join(pipeline_dir, subject, 'MNINonLinear',
            'fsaverage_LR32k')
    myelin_maps = glob.glob(os.path.join(fs_scripts, '*MyelinMap*'))
    if myelin_maps:
        return True
    return False

def is_started(subject, pipeline_dir):
    base_dir = os.path.join(pipeline_dir, subject)
    mni = os.path.join(base_dir, 'MNINonLinear')
    t1w = os.path.join(base_dir, 'T1w')
    t2w = os.path.join(base_dir, 'T2w')
    for path in [mni, t1w, t2w]:
        if os.path.exists(path):
            return True
    return False

def get_anatomical_file(scan, tag, blacklist):
    anat_files = scan.get_tagged_nii(tag)

    anat_files = filter(lambda x: x.file_name.replace(x.ext, '') not in blacklist,
            anat_files)

    if not anat_files:
        raise ValueError("No files with tag {} found for {}".format(tag,
                scan.full_id))

    if len(anat_files) > 1:
        raise ValueError("Multiple files with tag {} found for {}. Please blacklist "
                "all but one".format(tag, scan.full_id))

    return anat_files[0].path

def create_command(study, subject, t1, t2, args):
    cmd = [os.path.basename(__file__), study, subject, t1, t2]
    if args['--debug']:
        cmd.append('--debug')
    if args['--dry-run']:
        cmd.append('--dry-run')
    return " ".join(cmd)

def submit_job(cmd, subid, walltime="24:00:00"):
    job_name = "dm_hcp_freesurfer_{}_{}".format(subid,
            time.strftime("%Y%m%d-%H%M%S"))

    rtn, out = utils.run("echo {} | qbatch -N {} --walltime {} -".format(cmd,
            job_name, walltime), dryrun=DRYRUN)

    if rtn:
        logger.error("Job submission failed.")
        if out:
            logger.error("stdout: {}".format(out))
        sys.exit(1)

if __name__ == '__main__':
    main()
