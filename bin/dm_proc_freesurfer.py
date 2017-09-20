#!/usr/bin/env python
"""
This runs freesurfer T1 images using the settings found in project_config.yml

Usage:
  dm_proc_freesurfer.py [options] <study>

Arguments:
    <study>             study name defined in master configuration .yml file

Options:
  --subject SUBJID      subject name to run on
  --parallel            Specifies that the freesurfer job should run in parallel,
                        only available in Freesurfer 6.
  --resubmit            Will resubmit a subject (or subjects if in batch mode)
                        that timed out on the queue. This means recon-all will
                        be run from the last stage that was in progress.
  --log-to-server       If set, all log messages are sent to the configured
                        logging server.
  --debug               debug logging
  --dry-run             don't do anything
"""
import os, sys
import glob
import time
import logging
import logging.handlers

from datman.docopt import docopt
import datman.scanid as sid
import datman.utils as utils
import datman.config as cfg
import datman.scan as dm_scan
import datman.fs_log_scraper as fs_scraper

logging.basicConfig(level=logging.WARN, format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

DRYRUN = False
PARALLEL = False
NODE = os.uname()[1]
LOG_DIR = None

def write_lines(output_file, lines):
    if DRYRUN:
        logger.debug("Dry-run set. Skipping write of {} to {}.".format(lines,
                output_file))
        return
    with open(output_file, 'w') as output_stream:
        output_stream.writelines(lines)

def submit_job(cmd, i, walltime="24:00:00"):
    if DRYRUN:
        return

    job_name = 'dm_freesurfer_{}_{}'.format(i, time.strftime("%Y%m%d-%H%M%S"))
    job_file = '/tmp/{}'.format(job_name)

    with open(job_file, 'wb') as fid:
        fid.write('#!/bin/bash\n')
        fid.write(cmd)

    rtn, out = utils.run("qsub -V -q main.q -N {} {}".format(
            job_name, job_file))

    if rtn:
        logger.error("Job submission failed.")
        if out:
            logger.error("stdout: {}".format(out))
        sys.exit(1)

def create_command(subject, arguments):
    study = arguments['<study>']
    debug_flag = ' --debug' if arguments['--debug'] else ''
    server_flag = ' --log-to-server' if arguments['--log-to-server'] else ''
    dryrun_flag = ' --dry-run' if DRYRUN else ''
    parallel_flag = ' --parallel' if PARALLEL else ''
    redo_flag = ' --resubmit' if arguments['--resubmit'] else ''

    options = "".join([debug_flag, server_flag, dryrun_flag, parallel_flag,
            redo_flag])

    cmd = "{} {} --subject {}{}".format(__file__, study, subject, options)
    return cmd

def submit_proc_freesurfer(fs_path, fs_subjects, arguments):
    # Change to freesurfer directory, because qbatch leaves .qbatch
    # folders in the current working directory
    with utils.cd(fs_path):
        for i, subject in enumerate(fs_subjects):
            cmd = create_command(subject, arguments)
            logger.debug("Queueing command: {}".format(cmd))
            submit_job(cmd, i)

def get_halted_subjects(fs_path, subjects):
    timed_out_msg = fs_scraper.FSLog._TIMEDOUT.format("")

    halted = []
    for subject in subjects:
        if sid.is_phantom(subject):
            continue
        fs_folder = os.path.join(fs_path, subject)
        try:
            log = fs_scraper.FSLog(fs_folder)
        except:
            pass
        else:
            if log.status.startswith(timed_out_msg):
                halted.append(subject)

    return halted

def get_new_subjects(config, qc_subjects):
    fs_subjects = []
    for subject in qc_subjects:
        if sid.is_phantom(subject):
            logger.debug("Subject {} is a phantom. Skipping.".format(subject))
            continue
        freesurfer_dir = utils.define_folder(config.get_path('freesurfer'))
        fs_subject_dir = os.path.join(freesurfer_dir, subject)
        if not outputs_exist(fs_subject_dir):
            fs_subjects.append(subject)
    return fs_subjects

def get_freesurfer_arguments(config, site):
    args = ['-all', '-qcache', '-notal-check']

    if PARALLEL:
        args.append('-parallel')

    # not compatible with freesurfer 6
    #try:
    #    nu_iter = get_freesurfer_setting(config, 'nu_iter')
    #    if isinstance(nu_iter, dict):
    #        site_iter = nu_iter[site]
    #    else:
    #        site_iter = nu_iter
    #    args.append('-nuiterations {}'.format(site_iter))
    #except KeyError:
    #   pass

    return " ".join(args)

def get_site_exportinfo(config, site):
    try:
        site_info = config.study_config['Sites'][site]['ExportInfo']
    except KeyError:
        logger.error("Can't retrieve export info for site {}".format(site))
        sys.exit(1)
    return site_info

def get_freesurfer_setting(config, setting):
    try:
        fs_setting = config.study_config['freesurfer'][setting]
    except KeyError:
        raise KeyError("Project config file's freesurfer settings missing "
                "setting: {}".format(setting))
    return fs_setting

def get_optional_images(subject, blacklist, config, error_log):
    optional_files = []
    for added_type in ['T2', 'FLAIR']:
        try:
            found_files = get_anatomical_images(added_type, added_type, subject, blacklist,
                    config, error_log)
        except KeyError:
            continue
        else:
            optional_files.extend(found_files)
    return optional_files

def make_arg_string(key, value):
    return "-{} {}".format(key, value)

def get_anatomical_images(key, cmd_line_arg, subject, blacklist, config, error_log):
    input_tags = get_freesurfer_setting(config, key)

    if type(input_tags) == str:
        input_tags = [input_tags]

    site_info = get_site_exportinfo(config, subject.site)

    inputs = []
    for tag in input_tags:
        n_expected = site_info[tag]['Count']
        candidates = filter(lambda nii: utils.splitext(nii.path)[0] not in blacklist,
                subject.get_tagged_nii(tag))

        # fail if the wrong number of inputs for any tag is found (implies
        # blacklisting is required)
        if len(candidates) != n_expected:
            error_message = "{}: {} {}'s found, expected {} for site {}".format(
                    subject.full_id, len(candidates), tag, n_expected,
                    subject.site)
            logger.debug(error_message)
            write_lines(error_log, ['{}\n{}'.format(error_message, NODE)])
        inputs.extend(candidates)

    return [make_arg_string(cmd_line_arg, series.path) for series in inputs]

def remove_IsRunning(scripts):
    scripts_regex = os.path.join(scripts, '*')
    isrunning_files = [item for item in glob.glob(scripts_regex)
                            if 'IsRunning' in item]
    if DRYRUN:
        logger.debug("Dry-run: skipping removal of {}".format(
                " ".join(isrunning_files)))
        return

    for found_file in isrunning_files:
        try:
            os.remove(found_file)
        except:
            pass

def outputs_exist(output_dir):
    """
    Will return false as long as a freesurfer 'scripts' folder exists. This
    prevents resubmission if a subject failed with an error or timed out,
    because in these cases manual clean up or rerunning with --resubmit is
    required to prevent freesurfer jobs from failing.
    """
    return os.path.exists(os.path.join(output_dir, 'scripts'))

def run_freesurfer(subject, blacklist, config, resubmit=False):
    """Finds the inputs for subject and runs freesurfer."""
    freesurfer_path = config.get_path('freesurfer')
    output_dir = os.path.join(freesurfer_path, subject.full_id)

    if outputs_exist(output_dir) and not resubmit:
        return

    # reset / remove error.log
    error_log = os.path.join(LOG_DIR, '{}_error.log'.format(subject.full_id))
    if os.path.isfile(error_log):
        os.remove(error_log)

    args = get_freesurfer_arguments(config, subject.site)

    scripts_dir = os.path.join(output_dir, 'scripts')
    if outputs_exist(scripts_dir):
        # If outputs exist and the script didnt return above, it means
        # 'resubmit' == True and the subject must be restarted
        remove_IsRunning(scripts_dir)
        input_files = []
    else:
        input_files = get_anatomical_images('tags', 'i', subject, blacklist, config,
                error_log)
        optional_files = get_optional_images(subject, blacklist, config,
                error_log)
        input_files.extend(optional_files)

    command = "recon-all {args} -subjid {subid} {inputs}".format(args=args,
            subid=subject.full_id, inputs=" ".join(input_files))

    rtn, out = utils.run(command, dryrun=DRYRUN)
    if rtn:
        error_message = 'freesurfer failed: {}\n{}'.format(command, out)
        logger.debug(error_message)
        write_lines(error_log, '{}\n{}'.format(error_message, NODE))

def get_site_standards(freesurfer_dir, args, subject_folder):
    logger.debug("Using subject {} to generate standards.".format(subject_folder))

    if not args:
        return None

    standard_log = fs_scraper.FSLog(subject_folder)

    standards = {'build': standard_log.build,
                 'kernel': standard_log.kernel,
                 'args': args}
    return standards

def choose_standard_subject(site_folders):
    standard_sub = None
    for subject in site_folders:
        # Loop until a subject with complete FS outputs is found
        if os.path.exists(os.path.join(subject, 'scripts/recon-all.done')):
            standard_sub = subject
            break
    return standard_sub

def get_freesurfer_folders(freesurfer_dir, qc_subjects):
    fs_data = {}
    for subject in qc_subjects:
        try:
            ident = sid.parse(subject)
        except sid.ParseException:
            logger.error("Subject {} from checklist does not match datman "
                    "convention. Skipping".format(subject))
            continue
        fs_path = os.path.join(freesurfer_dir, subject)
        if not os.path.exists(fs_path) or not os.listdir(fs_path):
            continue
        # Add to list of subjects for the site
        fs_data.setdefault(ident.site, []).append(fs_path)
    return fs_data

def update_aggregate_log(config, qc_subjects, destination):
    logger.info("Updating aggregate log")
    freesurfer_dir = config.get_path('freesurfer')
    site_fs_folders = get_freesurfer_folders(freesurfer_dir, qc_subjects)

    if not site_fs_folders:
        logger.info("No freesurfer output logs to scrape for project "
                "{}.".format(config.study_name))
        return

    header = 'Subject,Status,Start,End,Build,Kernel,Arguments,Nifti Inputs\n'
    log = []
    log.append(header)

    for site in site_fs_folders:
        log.append("Logs for site: {}\n".format(site))
        standard_sub = choose_standard_subject(site_fs_folders[site])
        if standard_sub is None:
            logger.info("{} does not have any subjects that have completed the "
                    "pipeline. Skipping".format(site))
            continue
        site_args = get_freesurfer_arguments(config, site)
        site_standards = get_site_standards(freesurfer_dir, site_args,
                standard_sub)
        site_logs = fs_scraper.scrape_logs(site_fs_folders[site],
                standards=site_standards)
        if not site_logs:
            logger.info("No log data found for site {}".format(site))
            continue
        log.extend(site_logs)

    write_lines(destination, log)

def update_aggregate_stats(config):
    logger.info("Updating aggregate stats")
    freesurfer_dir = config.get_path('freesurfer')
    enigma_ctx = os.path.join(config.system_config['DATMAN_ASSETSDIR'],
            'ENGIMA_ExtractCortical.sh')
    enigma_sub = os.path.join(config.system_config['DATMAN_ASSETSDIR'],
            'ENGIMA_ExtractSubcortical.sh')
    utils.run('{} {} {}'.format(enigma_ctx, freesurfer_dir,
            config.study_config['STUDY_TAG']), dryrun=DRYRUN)
    utils.run('{} {} {}'.format(enigma_sub, freesurfer_dir,
            config.study_config['STUDY_TAG']), dryrun=DRYRUN)

def get_blacklist(qc_subjects, scanid):
    # This function is here as bug prevention: If a subject ID is given that
    # isnt signed off in the checklist.csv this will catch the key error here
    # instead of later on after work may have been done
    try:
        blacklisted_series = qc_subjects[scanid]
    except KeyError:
        logger.error("{} has not been QC'd and signed off on in "
                "checklist.csv".format(scanid))
        sys.exit(1)
    return blacklisted_series

def check_input_paths(config):
    for k in ['nii', 'freesurfer']:
        if k not in config.site_config['paths']:
            logger.error("paths:{} not defined in site config".format(k))
            sys.exit(1)

def make_error_log_dir(freesurfer_path):
    # Error logs no longer placed in subject folders because it required that
    # the subject folder be created (so a log had somewhere to be written)
    # before the freesurfer job ran, but freesurfer wont run a subject
    # if the folder already exists.
    log_dir = os.path.join(freesurfer_path, 'logs')
    try:
        if not DRYRUN:
            os.mkdir(log_dir)
    except:
        pass
    return log_dir

def add_server_handler(config):
    server_ip = config.get_key('LOGSERVER')
    server_handler = logging.handlers.SocketHandler(server_ip,
            logging.handlers.DEFAULT_TCP_LOGGING_PORT)
    logger.addHandler(server_handler)

def load_config(study):
    try:
        config = cfg.config(study=study)
    except ValueError:
        logger.error('study {} not defined'.format(study))
        sys.exit(1)
    return config

def main():
    global DRYRUN, PARALLEL, LOG_DIR
    arguments = docopt(__doc__)
    study     = arguments['<study>']
    use_server = arguments['--log-to-server']
    scanid    = arguments['--subject']
    debug     = arguments['--debug']
    resubmit = arguments['--resubmit']
    PARALLEL = arguments['--parallel']
    DRYRUN    = arguments['--dry-run']
    # If you add an option/argument that needs to be propagated to subject jobs
    # after a batch submit make sure to add it to create_command()
    # If it needs to be propagated to recon-all add it to
    # get_freesurfer_arguments()

    config = load_config(study)

    if use_server:
        add_server_handler(config)
    if debug:
        logger.setLevel(logging.DEBUG)

    logger.info('Starting')
    check_input_paths(config)
    qc_subjects = config.get_subject_metadata()

    fs_path = config.get_path('freesurfer')
    LOG_DIR = make_error_log_dir(fs_path)

    if scanid:
        # single subject mode
        blacklisted_series = get_blacklist(qc_subjects, scanid)
        subject = dm_scan.Scan(scanid, config)

        if subject.is_phantom:
            sys.exit('Subject {} is a phantom, cannot be analyzed'.format(scanid))

        run_freesurfer(subject, blacklisted_series, config, resubmit)
        return

    # batch mode
    update_aggregate_stats(config)
    destination = os.path.join(fs_path, 'freesurfer_aggregate_log.csv')
    update_aggregate_log(config, qc_subjects, destination)

    fs_subjects = get_new_subjects(config, qc_subjects)
    logger.info("Submitting {} new subjects".format(len(fs_subjects)))

    if resubmit:
        # Filter out subjects that were just submitted to reduce search space
        remaining_subjects = filter(lambda x: x not in fs_subjects, qc_subjects)
        halted_subjects = get_halted_subjects(fs_path, remaining_subjects)
        logger.info("Resubmitting {} subjects".format(len(halted_subjects)))
        fs_subjects.extend(halted_subjects)

    submit_proc_freesurfer(fs_path, fs_subjects, arguments)

if __name__ == '__main__':
    main()
