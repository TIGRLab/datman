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
    --walltime STR      The maximum wall time when running in batch mode.
                        [default: 36:00:00]
    --log-to-server     If set, all log messages will also be set to the logging
                        server configured in the site configuration file
    --debug
    --dry-run
"""
import os
import sys
import glob
import time
import logging
import logging.handlers

from datman.docopt import docopt
import datman.utils as utils
import datman.config
import datman.scan
import datman.scanid as scanid
import datman.fs_log_scraper as log_scraper

logging.basicConfig(level=logging.WARN,
        format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

DRYRUN = False

def main():
    global DRYRUN
    arguments = docopt(__doc__)
    study = arguments['<study>']
    subject = arguments['<subject>']
    use_server = arguments['--log-to-server']
    debug = arguments['--debug']
    DRYRUN = arguments['--dry-run']

    config = datman.config.config(study=study)

    if use_server:
        add_server_handler(config)
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    check_environment()

    if subject:
        run_pipeline(config, subject, arguments['<T1>'], arguments['<T2>'])
        return

    run_all_subjects(config, arguments)

def add_server_handler(config):
    server_ip = config.get_key('LOGSERVER')
    server_handler = logging.handlers.SocketHandler(server_ip,
            logging.handlers.DEFAULT_TCP_LOGGING_PORT)
    logger.addHandler(server_handler)

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
    dest_dir = utils.define_folder(os.path.join(base_dir, subject))
    with utils.cd(dest_dir):
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
    walltime = arguments['--walltime']

    subjects = config.get_subject_metadata()
    if blacklist_file:
        subjects = add_pipeline_blacklist(subjects, blacklist_file)

    hcp_fs_path = config.get_path('hcp_fs')
    logs = make_log_dir(hcp_fs_path)
    update_aggregate_log(hcp_fs_path, subjects)

    # Update FS log ?
    commands = []
    for subject in subjects:
        if is_completed(subject, hcp_fs_path):
            continue
        if is_started(subject, hcp_fs_path):
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
        cmd = create_command(config.study_name, subject, t1, t2, arguments)
        submit_job(cmd, subject, logs, walltime=walltime)

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
            logger.debug("Blacklisted item given for subject not in "
                    "checklist.csv. Ignoring entry {}".format(entry))
            continue
    return subjects

def make_log_dir(path):
    log_dir = os.path.join(path, 'logs')
    try:
        if not DRYRUN:
            os.mkdir(log_dir)
    except:
        pass
    return log_dir

def update_aggregate_log(pipeline_path, subjects):
    fs_output_folders = []
    for subject in subjects:
        output_dir = os.path.join(pipeline_path, subject)
        fs_dir = os.path.join(output_dir, 'T1w', subject)
        if os.path.exists(fs_dir):
            fs_output_folders.append(fs_dir)
    if not fs_output_folders:
        # No outputs yet, skip log scraping
        return
    scraped_data = log_scraper.scrape_logs(fs_output_folders, col_headers=True)
    agg_log = os.path.join(pipeline_path, 'aggregate_log.csv')

    if DRYRUN:
        return

    try:
        with open(agg_log, 'w') as log:
            log.writelines(scraped_data)
    except Exception as e:
        logger.error("Could not update aggregate log. Reason: {}".format(e.message))

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
    if args['--log-to-server']:
        cmd.append('--log-to-server')
    return " ".join(cmd)

def submit_job(cmd, subid, log_dir, walltime="36:00:00"):
    job_name = "dm_hcp_freesurfer_{}_{}".format(subid,
            time.strftime("%Y%m%d-%H%M%S"))

    rtn, out = utils.run("echo {} | qbatch -N {} --walltime {} "
            "--logdir {} -".format(cmd, job_name, walltime, log_dir),
            specialquote=False, dryrun=DRYRUN)

    if rtn:
        logger.error("Job submission failed.")
        if out:
            logger.error("stdout: {}".format(out))
        sys.exit(1)

if __name__ == '__main__':
    main()
