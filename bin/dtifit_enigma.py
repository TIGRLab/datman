#!/usr/bin/env python
'''
Will complete both dtifit and enigmaDTI pipelines unless otherwise specified.

There are two levels of tasks:
    Individual - Tasks that need to be completed for each subject individually.
    Group - Tasks that involve the subjects as a whole.
        Ex. Creating summary csv files and html pages

Will complete tasks for both levels unless otherwise specified.

Any given directories will overwrite datman study configuaration.
Datman folder structure will be ignored if nifti, dtifit, and enigma directories are given.

Usage:
    dm_proc_dti.py [options] [dtifit|enigma] <study>
    dm_proc_dti.py [options] [dtifit|enigma] <study> group
    dm_proc_dti.py [options] [dtifit|enigma] <study> individual [<subject_id>...]


Arguments:
    dtifit                              Will only complete dtifit pipeline tasks
    enigma                              Will only complete enigmaDTI pipeline tasks
    <study>                             Study to process
    group                               Will only complete group tasks such as summarizing csv files and creating html pages
    individual [<subject_id>...]        Will only complete individual subject tasks. If no subject ids are given, all will be run

Options:
    -n DIR, --nii-dir DIR               Input folder holding nii data within subject subfolders
    -d DIR, --dtifit-dir DIR            Output folder for dtifit data
    -e DIR, --enigma-dir DIR            Output folder for enigmaDTI data
    --reg-vol N                         Registration volume index. For dtifit. [default: 0]
    --fa-thresh N                       FA threshold for bet. For dtifit. [default: 0.3]
    --output-nVox                       Change output value from "Average" to "nVoxels". For
                                        enigma
    --DPA-tag DPA                       Tags for diffusion maps
    --DAP-tag DAP                       Tags for diffusion maps
    --walltime TIME                     A walltime for the dtifit/engima/post-engima stage
                                        depending on which stages will be run [default: 4:00:00]

    --log-to-server                     Log to server
    --debug                             Debug logging mode
    --dry-run                           Dry-run

DETAILS
Requires FSL, and imagemagick
'''
import datman.utils
import datman.config
import datman.scanid
import os, sys, pdb
import datetime
import tempfile, shutil
import glob
import logging, logging.handlers
from docopt import docopt

logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")

def create_command(subject, arguments):
    flags = ['dtifit_enigma.py']
    if arguments['dtifit']:
        flags += ['dtifit']
    elif arguments['enigma']:
        flags += ['enigma']
    for arg_flag in ['--nii-dir', '--dtifit-dir', '--enigma-dir',
                     '--DAP-tag', '--DPA-tag',
                     '--fa-thresh', '--reg-vol', '--walltime']:
        flags += [arg_flag, arguments[arg_flag]] if arguments[arg_flag] else []
    for flag in ['--debug', '--dry-run', '--log-to-server', '--output-nVox']:
        flags += [flag] if arguments[flag] else []

    flags += [arguments['<study>']]
    # if arguments['group']:
    #     flags += ['group']
    # elif arguments['individual']:
    #     flags += ['individual']
    #     flags += [" ".join(arguments['<subject_id>'])]
    flags += ['individual', subject]
    return " ".join(flags)

def submit_proc_dti(cd_path, subject, arguments, cfg):
    with datman.utils.cd(cd_path):
        cmd = create_command(subject, arguments)
        logger.debug('Queueing command: {}'.format(cmd))
        job_name = 'dm_proc_dti_{}_{}'.format(subject, time.strftime("%Y%m%d-%H%M%S"))
        datman.utils.submit_job(cmd, job_name, log_dir=LOG_DIR,
                                cpu_cores=1, walltime=arguments['--walltime'],
                                dryrun=False)

def create_dir(dir_path):
    if not os.path.isdir(dir_path):
        logging.info('Creating: {}'.format(dir_path))
        try:
            os.mkdir(dir_path)
        except OSError:
            logging.critical('Failed creating: {}. Exiting.'.format(dir_path), exc_info=True)
            sys.exit(1)

def check_dirs(dtifit, enigma, study, nii_dir, fit_dir, enig_dir, cfg):
    both_pipe = True if not (dtifit or enigma) else False

    # Check nii_dir
    if (dtifit or both_pipe):
        if nii_dir:
            if not os.path.isdir(nii_dir):
                logging.critical('Given nii dir does not exist. Exiting.')
                sys.exit(1)
        elif cfg:
            nii_dir = cfg.get_path('nii')
            if not os.path.isdir(nii_dir):
                logging.critical('Nii dir found through config does not exist.Exiting.')
                sys.exit(1)
        else:
            logging.critical('Nii dir or valid datman configuration required to continue. Exiting.')
            sys.exit(1)
    logging.info('nii_dir will be: {}'.format(nii_dir))

    #Check dtifit dir depending on pipeline
    if (fit_dir and enigma):
        if os.listdir(fit_dir) == []:
            logging.critical("Given dtifit dir is empty. Exiting.")
            sys.exit(1)
    elif (fit_dir and (dtifit or both_pipe)):
        create_dir(fit_dir)
    elif (cfg and enigma):
        fit_dir = cfg.get_path('dtifit')
        if os.listdir(fit_dir) == []:
            logging.critical('Dtifit dir found through config does not exist.Exiting.')
            sys.exit(1)
    elif (cfg and (dtifit or both_pipe)):
        fit_dir = cfg.get_path('dtifit')
        create_dir(fit_dir)
    elif enigma:
        logging.critical('Dtifit dir or valid datman configuration containing data is required to continue. If not available, run without enigma command to create. Exiting.')
        sys.exit(1)
    elif (dtifit or both_pipe):
        logging.critical('Dtifit dir or valid datman configuration required to continue. Exiting.')
        sys.exit(1)
    logging.info('dtifit dir will be: {}'.format(fit_dir))

    #Check enigmaDTI dir
    if (enigma or both_pipe):
        if enig_dir:
            create_dir(enig_dir)
        elif cfg:
            enig_dir = cfg.get_path('enigmaDTI')
            create_dir(enig_dir)
        else:
            logging.critical('EnigmaDTI dir or valid datman configuration required to continue. Exiting.')
            sys.exit(1)
    logging.info('enigma dir will be: {}'.format(enig_dir))

    return nii_dir, fit_dir, enig_dir

def add_file_handler(dir_path, pipeline):
    date = str(datetime.date.today())
    log_path = os.path.join(dir_path, "{}-{}.log".format(date, pipeline))
    fhandler = logging.FileHandler(log_path, "w")
    fhandler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("[%(name)s] %(levelname)s: %(message)s")
    fhandler.setFormatter(formatter)
    logger.getLogger('').addHandler(fhandler)

def setup_log_to_server(cfg):
    server_ip = cfg.get_key('LOGSERVER')
    server_handler = logging.handlers.SocketHandler(server_ip,
            logging.handlers.DEFAULT_TCP_LOGGING_PORT)
    server_handler.setLevel(logging.CRITICAL)
    logging.getLogger('').addHandler(server_handler)

def main():
    arguments = docopt(__doc__)
    dtifit = arguments['dtifit']
    enigma = arguments['enigma']
    study = arguments['<study>']
    group = arguments['group']
    indiv = arguments['individual']
    sub_ids = arguments ['<subject_id>']
    nii_dir = arguments['--nii-dir']
    fit_dir = arguments['--dtifit-dir']
    enig_dir = arguments['--enigma-dir']
    reg_vol = arguments['--reg-vol']
    fa_thresh = arguments['--fa-thresh']
    output_nVox = arguments['--output-nVox']
    dap_tag = arguments['--DAP-tag']
    dpa_tag = arguments['--DPA-tag']
    walltime = arguments['--walltime']
    log_to_server = arguments['--log-to-server']
    debug = arguments['--debug']
    dry_run = arguments['--dry-run']

    print arguments

    if debug:
        logging.getLogger('').setLevel(logging.DEBUG)

    if study:
        try:
            cfg = datman.config.config(study=study)
        except:
            cfg = None
            logger.info('Data in not in datman format. Will not be using datman configuarations')


    if (log_to_server and cfg):
        setup_log_to_server(cfg)

    nii_dir, fit_dir, enig_dir = check_dirs(dtifit, enigma, study, nii_dir, fit_dir, enig_dir, cfg)
    both_pipe = True if not (dtifit or enigma) else False
    both_task = True if not (indiv or group) else False

    if not sub_ids:
        sub_ids = datman.utils.get_subjects(nii_dir)

    qced_subjects = cfg.get_subject_metadata()


    tmp_dir = tempfile.mkdtemp(dir=fit_dir)

    for sub in sub_ids:
        if datman.scanid.is_phantom(sub):
            logging.info('Subject is phantom. Skipping: {}'.format(sub))
            continue

        # try:
        #     blacklisted_series = qced_subjects[sub]
        # except KeyError:
        #     logging.info('Subject has not been QCed. Skipping: {}'.format(sub))
        #     continue

        # if indiv and len(sub_ids) > 1:
        #     cd_path = fit_dir if dtifit else enig_dir
        #     submit_proc_dti(cd_path, sub, arguments, cfg)
        #     continue

        if dtifit or both_pipe:
            fit_qc_dir = os.path.join(fit_dir, "QC")
            create_dir(fit_qc_dir)
            bet_dir = os.path.join(fit_qc_dir, "BET")
            create_dir(bet_dir)
            dir_dir = os.path.join(fit_qc_dir, "directions")
            create_dir(dir_dir)
            sub_tmp_dir = os.path.join(tmp_dir, sub)
            create_dir(sub_tmp_dir)

            if indiv or both_task:
                sub_dir = os.path.join(nii_dir, sub)

                dti_files = datman.utils.get_files_with_tag(sub_dir, 'DTI', fuzzy=True)
                dti_files = filter(lambda x: x.endswith('.nii.gz'), dti_files)
                if not os.getenv('FSLDIR'):
                    logger.critical('FSLDIR environment variable is undefined. Exiting.')
                    sys.exit(1)

                for dti in dti_files:
                    ident, tag, series, description = datman.scanid.parse_filename(dti)
                    print dti + '\n'

                    series = int(series)

                    # try:
                    #     blacklisted_series.index(series)
                    #     logger.info("DTI series number in blacklist. Skipping: {}".format(os.path.basename(dti)))
                    #     continue
                    # except ValueError:
                    #     pass

                    if dpa_tag and dap_tag:
                        pas = glob.glob(os.path.join(sub_dir, '*{}*.nii.gz'.format(dpa_tag)))
                        aps = glob.glob(os.path.join(sub_dir, '*{}*.nii.gz'.format(dap_tag)))

                        get_series = lambda x: int(datman.scanid.parse_filename(x)[2])
                        print '\n' + min(pas, key=lambda x: abs(get_series(x) - series) if get_series(x) < series else sys.maxsize)
                        print min(aps, key=lambda x: abs(get_series(x) - series) if get_series(x) < series else sys.maxsize) + '\n'
                        for pa in pas:
                            print get_series(pa)
                        print ''
                        for ap in aps:
                            print get_series(ap)
                        print ''

    shutil.rmtree(tmp_dir)





if __name__ == "__main__":
    main()
