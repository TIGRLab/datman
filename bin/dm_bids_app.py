#!/usr/bin/env python

'''
Run BIDS-apps on DATMAN environment using JSON dictionaries to specify arguments
Note that this application will run subjects independently (unless longitudinal) to maximize parallelization.

Usage:
    dm_bids_app.py [options] [-e <EXCLUDE>]... [-s <SUBJECT>]...  <study> <out> <json>

Arguments:
    <study>                         Datman study nickname
    <out>                           Base directory for BIDS-app output
    <json>                          JSON key-value dictionary for BIDS-app argument information

Options:
    -s, --subject SUBJECT,...       Datman subject ID to process through BID-app [repeatable option]
    -q, --quiet                     Only display ERROR Messages
    -v, --verbose                   Display INFO/WARNING/ERROR Messages
    -d, --debug                     Display DEBUG/INFO/WARNING/ERROR Messages
    -r, --rewrite                   Overwrite if outputs already exist in BIDS output directory
    -d, --tmp-dir TMPDIR            Specify temporary directory
                                    [default : '/tmp/']
    -w, --walltime                  Specify a walltime to use for the qsub submission
                                    [default : '24:00:00']
    -l, --log LOGDIR                Specify additional bids-app log output directory
                                    Will output to LOGDIR/<SUBJECT>_<BIDS_APP>_log.txt
                                    Will always output to logs in the output with or without LOGDIR argument since it is needed
                                    for detecting whether a participant has already been run
                                    [default : None]
    -e, --exclude EXCLUDE,...       Tag to exclude from BIDS-app processing [repeatable option]
    --DRYRUN                        Perform a dry-run, script will be generated at tmp-dir


Notes on arguments:
    option exclude finds files in the temporary BIDS directory created using a *<TAG>* regex.

    JSON:
    Additionally, the following arguments will NOT be parsed correctly:
        --participant_label --> wrapper script handles this for you
        -w WORKDIR          --> tmp-dir/work becomes the workdir

    The number of threads requested by qsub (if using HPC) is determined by the number of threads
    indicated in the json file under bidsarg for the particular pipeline. This is done so the number
    of processors per node requested matches that of the expected amount of available cores for the bids-apps

Requirements:
    FSL - dm_to_bids.py requires it to run

Notes on BIDS-apps:

    FMRIPREP
        FMRIPREP freesurfer module combines longitudinal data in order to enhance surface reconstruction.
        However sometimes we want to maintain both reconstructions for temporally varying measures extracted from pial surfaces.
        Refer to datman.config.config, study config key KeepRecon. Where the value is true, original reconstructions will not be
        deleted and linked to the fmriprep output version

    FMRIPREP_CIFTIFY
        FMRIPREP_CIFTIFY utilizes previously existing fmriprep outputs to speed up the pipeline. Therefore if previous outputs exist it is suggested that
        <out> points to a directory containing fmriprep/freesurfer outputs in BIDS format

Currently supported workflows:
    1) FMRIPREP
    2) MRIQC
    3) FMRIPREP CIFTIFY

    Add ['longitudinal' : True] in top level of <json> in order to perform longitudinal analysis

'''

import os
import sys
import datman.config
import logging
import tempfile
import subprocess as proc
from docopt import docopt
import json
from functools import partial
import datman.scanid as scan_ident

logging.basicConfig(level=logging.WARN,
        format='[%(name)s %(levelname)s : %(message)s]')
logger = logging.getLogger(os.path.basename(__file__))


def get_bids_name(subject):
    '''
    Helper function to convert datman to BIDS name
    Arguments:
        subject                             Datman style subject ID

    '''

    try:
        ident = scan_ident.parse(subject)
    except scan_ident.ParseException:
        logger.error('Cannot parse {} invalid DATMAN name!'.format(subject))
        raise

    return ident.get_bids_name()


def configure_logger(quiet,verbose,debug):
    '''
    Configure logger settings for script session
    '''

    if quiet:
        logger.setLevel(logging.ERROR)
    elif verbose:
        logger.setLevel(logging.INFO)
    elif debug:
        logger.setLevel(logging.DEBUG)

    return

def get_datman_config(study):
    '''
    Wrapper for error handling datman config instantiation

    Arguments:
        study                   DATMAN style study ID
    Output:
        config                  datman.config.config object
    '''

    try:
        config = datman.config.config(study=study)
    except KeyError:
        logger.error('{} not a valid study ID!'.format(study))
        sys.exit(1)

    if study != config.study_name:
        logger.error('Study incorrectly entered as subject {}, please fix arguments!'.format(study))
        logger.error('Exiting...')
        sys.exit(1)
    else:
        return config


def filter_subjects(subjects,out_dir,bids_app):

    '''
    Filters out subjects that have successfully completed the BIDS-pipeline
    Utilizes default log output (always enabled)

    Arguments:
        subjects                List of candidate subjects to be processed through pipeline
        out_dir                 Base directory for where BIDS-app will output
        bids_app                Name of BIDS-app (all upper-case convention)
    '''

    #Base log directory 
    log_dir = os.path.join(out_dir,'bids_logs',bids_app.lower())
    log_file = os.path.join(log_dir,'{}_{}.log')
    run_list = [] 

    #Use error keyword to identify subjects needing to be re-run
    for s in subjects: 

        try:
            if 'error' in open(log_file.format(s,bids_app)).read().lower(): 
                run_list.append(s) 
                logger.debug('Re-running {} through {}'.format(s,bids_app))
        except IOError: 
            continue
        
    return run_list

    

def get_json_args(json_file):
    '''
    Read json file and return dictionary. Will fail if required arguments not found in JSON file.

    Arguments:
        json                Full path to JSON file

    Output:
        j_dict              JSON-derived dictionary
    '''

    with open(json_file,'r') as jfile:
        j_dict = json.loads(jfile.read().decode('utf-8'))

    #Format argument keys
    args = get_dict_args(j_dict['bidsargs'])

    #Combine non-bids keys with formatted bids arugment keys
    out_dict = { k : v for k,v in j_dict.items() if k != 'bidsargs'}
    out_dict.update({'bidsargs':args})

    return out_dict

def validate_json_args(jargs,test_dict):
    '''
    Validates json arguments, if missing raise informative exception
    '''

    req_keys = ['app','img','bidsargs']

    #First check required keys
    try:
        for k in req_keys:
            jargs[k]
    except KeyError:
        logger.error('Required key, {} not found in provided json!'.format(k))
        raise

    #Second check if valid_app found
    try:
        test_dict[jargs['app']]
    except KeyError:
        logger.error('BIDS-app {} not supported!'.format(jargs['app']))
        raise

    return True

def get_exclusion_cmd(exclude):
    '''
    Returns a deletion command for each tag in exclude

    Arguments:
        exclude                 List of string tags to be excluded from subject bids folder
    '''

    exclusion_cmd_list = ['find $BIDS -name *{tag}* -delete'.format(tag=tag) for tag in exclude]
    return exclusion_cmd_list

def get_dict_args(arg_dict):
    '''
    Format dictionary of key:value to --key:value if parameter, and --key:'' if boolean
    '''

    #Get key:value arguments and format keys
    args = {'--{}'.format(k.lower()) : v for k,v in arg_dict.items() if str(v).lower() != 'false'}
    args = {k : ('' if str(v).lower() == 'true' else str(v)) for k,v in args.items()}

    return args

def get_init_cmd(study,sgroup,tmp_dir,out_dir,simg,log_tag):
    '''
    Get initialization steps prior to running BIDS-apps

    Arguments:
        study                       DATMAN-style study shortname
        sgroup                      Output group identifier
        tmp_dir                     Location BIDS-App temporary directory
        out_dir                     Location of output directory
        simg                        Singularity image location
        log_cmd                     A redirect toward logging
    '''

    trap_cmd = '''

    function cleanup(){
        rm -rf $APPHOME
    }

    '''

    init_cmd = '''

    APPHOME=$(mktemp -d {home})
    BIDS=$APPHOME/bids
    WORK=$APPHOME/work
    SIMG={simg}
    SUB={sub}
    OUT={out}

    mkdir -p $BIDS
    mkdir -p $WORK

    echo $APPHOME {log_tag}

    trap cleanup EXIT

    '''.format(home=os.path.join(tmp_dir,'home.XXXXX'),
            simg=simg,
            sub=get_bids_name(sgroup).replace('sub-',''),
            out=out_dir,
            log_tag=log_tag.replace('&>>','&>')) #This bit is to ensure that logs are wiped prior to appending for easier error tracking on re-runs

    return [trap_cmd,init_cmd]

def get_nii_to_bids_cmd(study,sublist,log_tag):

    n2b_cmd = '''

    dm_to_bids.py {study} --bids-dir $BIDS {subject}  {log_tag}

    '''.format(study=study,subject=' '.join(sublist),log_tag=log_tag)

    return n2b_cmd

def fetch_fs_recon(fs_dir,out_dir,subject):
    '''
    Copies over freesurfer reconstruction to fmriprep pipeline output

    Arguments:
        fs_dir                              Directory to freesurfer $SUBJECTS_DIR
        subject                             Name of subject
        out_dir                             fmriprep output directory for subject
    '''

    fs_sub_dir = os.path.join(fs_dir,subject)
    sub_fmriprep_fs = os.path.join(out_dir,'freesurfer',get_bids_name(subject))

    if os.path.isdir(fs_sub_dir):
        logger.info('Located Freesurfer reconstruction files for {}, rsync to {} enabled'.format(
            subject,sub_fmriprep_fs))

        try:
            os.makedirs(sub_fmriprep_fs)
        except OSError:
            logger.warning('Failed to create directory, {} already exists!'.format(sub_fmriprep_fs))

        #Rsyc, dereference
        rsync_cmd = '''

        rsync -L -a {recon_dir}/ {out_dir}

        '''.format(recon_dir=fs_sub_dir,out_dir=sub_fmriprep_fs)

        return rsync_cmd
    else:
        logger.info('No freesurfer reconstruction files located for {}'.format(subject))
        return ''

def get_symlink_cmd(fs_dir,out_dir,subject):
    '''
    Returns commands to remove original freesurfer directory and link to fmriprep freesurfer directory

    Arguments:
        fs_dir                          Directory to freesurfer $SUBJECTS_DIR
        subject                         Name of subject
        out_dir                         fmriprep output directory
    '''

    sub_fmriprep_fs = os.path.join(out_dir,'freesurfer',get_bids_name(subject))
    fs_sub_dir = os.path.join(fs_dir,subject)

    remove_cmd = '\n rm -rf {} \n'.format(fs_sub_dir)
    symlink_cmd = 'ln -s {} {} \n'.format(sub_fmriprep_fs,fs_sub_dir)

    return [remove_cmd, symlink_cmd]

def get_existing_freesurfer(jargs,sub_dir,subject):

    '''
    Provide commands to fetch subject's freesurfer and symlink over
    Arguments:
        jargs                           Dictionary of bids app json file
        sub_dir                         Full path to subject's output directory
        subject                         Subject name (DATMAN-style ID)
    '''

    symlink_cmd_list = []
    fetch_cmd = ''

    #Indicates multiple subjects
    if len(subject) > 1:
        return (fetch_cmd,symlink_cmd_list)

    try:
        fetch_cmd = fetch_fs_recon(jargs['freesurfer-dir'],sub_dir,subject)
    except KeyError:
        logger.warning('freesurfer-dir not specified in JSON!')
        logger.warning('Will run fmriprep from scratch if freesurfer BIDS output does not exist in output-dir')
    else:
        if jargs['keeprecon'] and (fetch_cmd != ''):
            symlink_cmd_list = get_symlink_cmd(fs_dir,sub_dir,subject)

    return (fetch_cmd,symlink_cmd_list)

def get_fs_license(license_dir):

    '''
    Return a command creating a license directory and copying over a freesurfer license
    '''

    license_cmd = '''

    LICENSE=$APPHOME/li
    mkdir -p $LICENSE
    cp {fs_license} $LICENSE/license.txt

    '''.format(fs_license=license_dir)

    return license_cmd

def fmriprep_fork(jargs,log_tag,out_dir,sublist):
    '''
    FMRIPREP MODULE

    Generate a list of commands used to formulate the fmriprep job BASH script

    Arguments:
        jargs                           Dictionary derived from JSON file
        log_tag                         String tag for BASH stdout/err redirection to log
        out_dir                         Subject directory in output
        sublist                         List of DATMAN-style subject IDs

    Output:
        [list of commands]

    NOTE:
    If running longitudinal analysis (len(sublist) > 1), then we will not copy over freesurfer reconstructions
    since fmriprep cannot take advantage of previously existing reconstructions in that instance
    '''

    #Get freesurfer license
    try:
        license_cmd = get_fs_license(jargs['fs-license'])
    except KeyError:
        logger.error('Cannot find fs-license key! Required for fmriprep freesurfer module.')
        logger.error('Exiting...')
        raise

    #Attempt to get freesurfer directories
    fetch_cmd, symlink_cmd_list = get_existing_freesurfer(jargs,out_dir,sublist)

    #Get BIDS singularity call
    bids_cmd = fmriprep_cmd(jargs['bidsargs'],log_tag)

    #Copy license, fetch freesurfer, run BIDSapp then symlink if KeepRecon false
    return [license_cmd, fetch_cmd, bids_cmd] + symlink_cmd_list

def ciftify_fork(jargs,log_tag,out_dir,sublist):
    '''
    CIFTIFY MODULE

    Generate a list of commands used to formulate the fmriprep-ciftify job BASH script

    Arguments:
        jargs                           Dictionary derived from JSON file
        log_tag                         String tag for BASH stdout/err redirection to log
        out_dir                         Subject directory in output
        subject                         DATMAN-style subject name

    Output:
        [list of commands]
    '''

    #Find freesurfer license
    try:
        license_cmd = get_fs_license(jargs['fs-license'])
    except KeyError:
        logger.error('Cannot find fs-license key! Required for fmriprep freesurfer module.')
        logger.error('Exiting...')
        raise

    #If freesurfer output specified in json then get existing freesurfer outputs
    fetch_cmd, symlink_cmd_list = get_existing_freesurfer(jargs,out_dir,sublist)

    bids_args = jargs['bidsargs']
    append_args = [' '.join([k,v]) for k,v in bids_args.items()]

    #mkdir -p line a workaround for current ciftify_fmriprep container bug
    bids_cmd = '''

    mkdir -p $WORK/fmriprep_work

    singularity run -H $APPHOME -B $BIDS:/input -B $WORK:/work -B $OUT:/output -B $LICENSE:/li \\
    $SIMG \\
    /input /output participant --fmriprep-workdir /work/fmriprep_work \\
    --participant_label $SUB \\
    --verbose --fs-license /li/license.txt {args} {log_tag}  

    '''.format(args = ' '.join(append_args), log_tag=log_tag)

    return [license_cmd, fetch_cmd, bids_cmd] + symlink_cmd_list


def fmriprep_cmd(bids_args,log_tag):

    '''
    Formulates fmriprep bash script content to be written into job file

    Arguments:

        bids_args                           bidsargs in JSON file
        log_tag                             String tag for BASH stout/err redirection to log

    Output:
        bids_cmd                            Formatted singularity bids app call

    '''

    append_args = [' '.join([k,v]) for k,v in bids_args.items()]

    bids_cmd = '''

    singularity run -H $APPHOME -B $BIDS:/bids -B $WORK:/work -B $OUT:/out -B $LICENSE:/li \\
    $SIMG \\
    /bids /out participant -w /work \\
    --participant-label $SUB \\
    --fs-license-file /li/license.txt {args} {log_tag}

    '''.format(args = ' '.join(append_args), log_tag=log_tag)

    return bids_cmd

def mriqc_fork(jargs,log_tag,out_dir=None,sublist=None):
    '''
    MRIQC MODULE

    Formulates mriqc bash script content to be written into job file

    Arguments:
        jargs                               bidsargs in JSON file
        log_tag                             String tag for BASH stout/err redirection to log
        out_dir,subject                     Strategy pattern consequence

    Output:
        [list of commands to be written into job file]

    '''

    bids_args = jargs['bidsargs']
    append_args = [' '.join([k,v]) for k,v in bids_args.items()]

    mrqc_cmd = '''

    singularity run -H $APPHOME -B $BIDS:/bids -B $WORK:/work -B $OUT:/out \\
    $SIMG \\
    /bids /out participant -w /work \\
    --participant-label $SUB \\
    {args} {log_tag}

    '''.format(args = ' '.join(append_args), log_tag=log_tag)

    return [mrqc_cmd]


def write_executable(f, cmds):
    '''
    Helper function to write to an executable file with a list of ocmmands

    Arguments:
        f                               Full file path
        cmds                            List of commands to write on each line
    '''

    #BASH Interpeter + exit upon error
    header = '#!/bin/bash \n set -e \n'

    with open(f,'w') as cmdfile:
        cmdfile.write(header)
        cmdfile.writelines(cmds)

    os.chmod(f,0o775)
    logger.info('Successfully wrote commands to {}'.format(f))

    return

def submit_jobfile(job_file,subject,threads,queue,walltime):

    '''
    Submit BIDS-app jobfile to queue

    Arguments:
        job_file                    Path to BIDSapp job script to be submitted
        subject                     DATMAN style subject ID
        threads                     Number of threads assigned to each job
    '''

    #Thread argument if provided
    thread_arg = '-l nodes=1:ppn={threads},walltime={wtime}'.format(threads=threads,wtime=walltime) if \
    (threads and queue.lower() == 'pbs') else ''

    #Formulate command
    cmd = 'qsub {pbs} -V -N {subject} {job}'.format(pbs=thread_arg,subject=subject,job=job_file)
    logger.info('Submitting job with command: {}'.format(cmd))

    p = proc.Popen(cmd, stdin=proc.PIPE, stdout=proc.PIPE, shell=True)
    std, err = p.communicate()

    if p.returncode:
        logger.error('Failed to submit job, STDERR: {}'.format(err))
        sys.exit(1)

    logger.info('Removing jobfile...')
    os.remove(job_file)

def gen_log_redirect(log_dir,out_dir,subject,app_name):
    '''
    Convenient function to generate a stdout/stderr redirection to a log file

    Arguments:
        log_dir                             Directory to output log files if provided
        out_dir                             Main output directory
        subject                             Subject name
        app_name                            Name of BIDS-app

    Returns a BASH command tag that:
    1) Without a log_dir specified will only output to out_dir
    2) With a log_dir specified will output to both log_dir and out_dir
    '''

    #Make logging directory in output/bids_logs/app_name
    default_log = os.path.join(out_dir,'bids_logs',app_name.lower())
    try:
        os.makedirs(default_log)
    except OSError:

        #If failed, then check if path exists
        if os.path.exists(default_log):
            pass
        else:
            logger.error('Cannot create directory in {}! Please adjust permissions at target directory'.format(default_log))
            raise

    #Generate base command for default log output
    log_name = '{}_{}.log'.format(subject,app_name)
    base_redir = ' &>> {}'.format(os.path.join(default_log,log_name))

    #Optional log tag |& is equivalent to 2&>1 |, both stdout and stderr are directed
    try:
        log_tag = ' |& tee {} '.format(os.path.join(log_dir,log_name))
    except AttributeError:
        log_tag = ''
        logger.info('No log directories specified, will output only to {}'.format(default_log))

    return log_tag + base_redir


def get_requested_threads(jargs, thread_dict):
    '''
    Helper function to identify the requested number of threads in the bids app
    and map it appropriately to the qsub request
    '''

    expected_arg = thread_dict[jargs['app'].upper()]

    try:
        n_threads = jargs['bidsargs'][expected_arg]
    except KeyError:
        logger.warning('No thread arguments requested by json, BIDS-app will use ALL available cores')
        return None

    else:
        is_int = float(n_threads).is_integer()
        if not is_int:
            raise TypeError('Number of threads requested, {}, is not an integer!'.format(n_threads))
        else:
            return n_threads

def group_subjects(subjects,longitudinal):

    '''
    Arguments:
        subjects                    List of subject(s) to be grouped
        longitudinal                If enabled will output using longitudinal keys (DATMAN session ID without sess #)
                                    Else use standard keys (full datman session ID)

    Output:
    A dictionary which maps subject ID (full ID if cross-sectional, otherwise ID w/o session number) to lists of subjects
    '''

    #Choose a lambda function based on whether we want longitudinal grouping or not
    get_key = (lambda x: '_'.join(x.split('_')[:-1])) if longitudinal else (lambda x: x)

    #Create grouping dictionary
    group_dict = {get_key(s) : [] for s in subjects}
    [group_dict[get_key(s)].append(s) for s in subjects]

    return group_dict

def main():

    #Parse arguments
    arguments = docopt(__doc__)

    study               =   arguments['<study>']
    out                 =   arguments['<out>']
    bids_json           =   arguments['<json>']

    subjects            =   arguments['--subject']
    exclude             =   arguments['--exclude']

    quiet               =   arguments['--quiet']
    verbose             =   arguments['--verbose']
    debug               =   arguments['--debug']

    rewrite             =   arguments['--rewrite']
    tmp_dir             =   arguments['--tmp-dir'] or '/tmp/'
    log_dir             =   arguments['--log']

    DRYRUN              =   arguments['--DRYRUN']

    walltime            =   arguments['--walltime'] or '24:00:00'

    #Strategy pattern dictionary
    strat_dict = {
            'FMRIPREP' : fmriprep_fork,
            'MRIQC'    : mriqc_fork,
            'FMRIPREP_CIFTIFY' : ciftify_fork
            }
    thread_dict = {
            'FMRIPREP'  : '--nthreads',
            'MRIQC'     : '--n_procs',
            'FMRIPREP_CIFTIFY' : '--n_cpus'
            }

    #Configuration
    config = get_datman_config(study)
    configure_logger(quiet,verbose,debug)
    try:
        queue = config.site_config['SystemSettings'][os.environ['DM_SYSTEM']]['QUEUE']
    except KeyError as e:
        logger.error('Config exception, key not found: {}'.format(e))
        sys.exit(1)

    #JSON parsing, formatting, and validating
    jargs = get_json_args(bids_json)
    validate_json_args(jargs,strat_dict)
    try:
        jargs.update({'keeprecon' : config.get_key('KeepRecon')})
    except KeyError:
        jargs.update({'keeprecon':True})
    n_thread = get_requested_threads(jargs,thread_dict)

    #Get redirect command string and exclusion list
    log_cmd = partial(gen_log_redirect,log_dir=log_dir,out_dir=out)
    exclude_cmd_list = [''] if exclude else get_exclusion_cmd(exclude)

    #Get subjects and filter if not rewrite and group if longitudinal
    subjects = subjects or [s for s in os.listdir(config.get_path('nii')) if 'PHA' not in s]
    subjects = subjects if rewrite else filter_subjects(subjects, out, jargs['app'])
    logger.info('Running {}'.format(subjects))

    subjects = group_subjects(subjects, True if 'longitudinal' in jargs else False)

    #Process subject groups
    for s in subjects.keys():

        #Get subject directory and log tag
        log_tag = log_cmd(subject=s,app_name=jargs['app'])

        #Get commands
        init_cmd_list = get_init_cmd(study,s,tmp_dir,out,jargs['img'],log_tag)
        n2b_cmd = get_nii_to_bids_cmd(study,subjects[s],log_tag)
        bids_cmd_list = strat_dict[jargs['app']](jargs,log_tag,out,s)

        #Write commands to executable and submit
        master_cmd = init_cmd_list + [n2b_cmd] + exclude_cmd_list + bids_cmd_list +  ['\n cleanup \n']
        fd, job_file = tempfile.mkstemp(suffix='datman_BIDS_job',dir=tmp_dir)
        os.close(fd)
        write_executable(job_file,master_cmd)

        if not DRYRUN:
            submit_jobfile(job_file,s,n_thread,queue,walltime)

if __name__ == '__main__':
    main()
