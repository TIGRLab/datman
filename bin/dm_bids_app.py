#!/usr/bin/env python

'''
Run BIDS-apps on DATMAN environment using JSON dictionaries to specify arguments

Usage: 
    dm_bids_app.py [options] [-e <EXCLUDE>]... [-s <SUBJECT>]...  <study> <out> <json>  

Arguments: 
    <study>                         Datman study nickname
    <out>                           Base directory for BIDS output
    <json>                          JSON key-value dictionary for BIDS-app argument information

Options: 
    -s, --subject SUBJECT,...       Datman subject ID to process through BID-app [repeatable option]
    -q, --quiet                     Only display ERROR Messages 
    -v, --verbose                   Display INFO/WARNING/ERROR Messages 
    -d, --debug                     Display DEBUG/INFO/WARNING/ERROR Messages
    -r, --rewrite                   Overwrite if outputs already exist in BIDS output directory 
    -d, --tmp-dir TMPDIR            Specify temporary directory 
                                    [default : '/tmp/']
    -l, --log LOGDIR                Specify bids-app log output directory. 
                                    Will output to /logs/<SUBJECT>_<BIDS_APP>_log.txt 
                                    [default : None]
    -e, --exclude EXCLUDE,...       Tag to exclude from BIDS-app processing [repeatable option]       
    --DRYRUN                        Perform a dry-run, script will be generated at tmp-dir

Notes on arguments: 
    [option] exclude finds files in the temporary BIDS directory created using a *<TAG>* regex. 

    JSON:
    Additionally, the following arguments will NOT be parsed correctly: 
        --participant_label --> wrapper script handles this for you
        -w WORKDIR          --> tmp-dir/work becomes the workdir

    The number of threads requested by qsub (if using HPC) is determined by the number of threads
    indicated in the json file under bidsarg for the particular pipeline. This is done so the number
    of processors per node requested matches that of the expected amount of available cores for the bids-apps

Requirements: 
    FSL - nii_to_bids.py requires it to run 

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
        sub_num = subject.split('_')[2] 
    except IndexError: 
        logger.error('Subject {}, invalid subject name!'.format(subject))
        logger.error('Subject should have STUDY_SITE_SUB#_... format, exiting...')
        raise

    return 'sub-' + sub_num 

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


def filter_subjects(subjects,out_dir): 

    '''
    Filter out subjects that have alrady been previously run through the BIDS-app pipeline 

    Arguments: 
        subjects                List of candidate subjects to be processed through pipeline
        out_dir                 Base directory for where BIDS-app will output
    '''

    criteria = lambda x: not os.path.isdir(os.path.join(out_dir,x)) 
    return [s for s in subjects if criteria(s)] 

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
    args = {'--{}'.format(k) : v for k,v in arg_dict.items() if str(v).lower() != 'false'}
    args = {k : ('' if str(v).lower() == 'true' else str(v)) for k,v in args.items()}

    return args

def get_init_cmd(study,subject,tmp_dir,sub_dir,simg,log_tag):
    '''
    Get initialization steps prior to running BIDS-apps

    Arguments: 
        study                       DATMAN-style study shortname
        subject                     DATMAN-style subject name
        tmp_dir                     Location BIDS-App temporary directory
        sub_dir                     Location of output directory 
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

    '''.format(home=os.path.join(tmp_dir,'home.XXXXX'),simg=simg,
            sub=get_bids_name(subject),out=sub_dir,log_tag=log_tag)

    return [trap_cmd,init_cmd]

def get_nii_to_bids_cmd(study,subject,log_tag): 

    n2b_cmd = '''

    dm_to_bids.py {study} {subject} --bids-dir $BIDS {log_tag}

    '''.format(study=study,subject=subject,log_tag=log_tag) 

    return n2b_cmd

def fetch_fs_recon(fs_dir,sub_dir,subject): 
    '''
    Copies over freesurfer reconstruction to fmriprep pipeline output

    Arguments: 
        fs_dir                              Directory to freesurfer $SUBJECTS_DIR
        subject                             Name of subject 
        sub_dir                             fmriprep output directory for subject 
    '''

    fs_sub_dir = os.path.join(fs_dir,subject) 
    sub_fmriprep_fs = os.path.join(sub_dir,'freesurfer',get_bids_name(subject)) 

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

def get_symlink_cmd(fs_dir,sub_dir,subject): 
    '''
    Returns commands to remove original freesurfer directory and link to fmriprep freesurfer directory 

    Arguments: 
        fs_dir                          Directory to freesurfer $SUBJECTS_DIR 
        subject                         Name of subject
        sub_dir                         fmriprep output directory for subject 
    '''

    sub_fmriprep_fs = os.path.join(sub_dir,'freesurfer',get_bids_name(subject))  
    fs_sub_dir = os.path.join(fs_dir,subject) 

    remove_cmd = '\n rm -rf {} \n'.format(fs_sub_dir) 
    symlink_cmd = 'ln -s {} {} \n'.format(sub_fmriprep_fs,fs_sub_dir) 

    return [remove_cmd, symlink_cmd]

def get_existing_freesurfer(jargs,sub_dir,subject,): 

    '''
    Provide commands to fetch subject's freesurfer and symlink over 
    Arguments: 
        jargs                           Dictionary of bids app json file
        sub_dir                         Full path to subject's output directory 
        subject                         Subject name (DATMAN-style ID) 
    '''
    
    symlink_cmd_list = [] 
    fetch_cmd = '' 

    try: 
        fetch_cmd = fetch_fs_recon(jargs['freesurfer-dir'],sub_dir,subject) 
    except KeyError: 
        logger.warning('freesurfer-dir not specified in JSON, will run fmriprep from scratch')
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

def fmriprep_fork(jargs,log_tag,sub_dir,subject): 
    '''
    FMRIPREP MODULE 

    Generate a list of commands used to formulate the fmriprep job BASH script

    Arguments: 
        jargs                           Dictionary derived from JSON file
        log_tag                         String tag for BASH stdout/err redirection to log
        sub_dir                         Subject directory in output
        subject                         DATMAN-style subject name 

    Output: 
        [list of commands]
    '''

    #Get freesurfer license 
    try: 
        license_cmd = get_fs_license(jargs['fs-license'])
    except KeyError: 
        logger.error('Cannot find fs-license key! Required for fmriprep freesurfer module.') 
        logger.error('Exiting...') 
        raise

    #Attempt to get freesurfer directories 
    fetch_cmd, symlink_cmd_list = get_existing_freesurfer(jargs,sub_dir,subject)

    #Get BIDS singularity call
    bids_cmd = fmriprep_cmd(jargs['bidsargs'],log_tag) 
    
    #Copy license, fetch freesurfer, run BIDSapp then symlink if KeepRecon false
    return [license_cmd, fetch_cmd, bids_cmd] + symlink_cmd_list

def ciftify_fork(jargs,log_tag,sub_dir,subject): 
    '''
    CIFTIFY MODULE 

    Generate a list of commands used to formulate the fmriprep-ciftify job BASH script

    Arguments: 
        jargs                           Dictionary derived from JSON file
        log_tag                         String tag for BASH stdout/err redirection to log
        sub_dir                         Subject directory in output
        subject                         DATMAN-style subject name 

    Output: 
        [list of commands]
    '''


    #TODO: (1) how does ciftify take advantage of previous fmriprep outputs

    #Find freesurfer license
    try: 
        jargs['fs-license'] 
    except KeyError: 
        logger.error('Cannot find fs-license key! Required for fmriprep freesurfer module.') 
        logger.error('Exiting...') 
        raise

    #Check for an existing fmriprep folder, if exists add it as a binding command to the singularity container at out/fmriprep
    binding_cmd = ''  
    try:
        binding_cmd = '-B {}:/out/fmriprep'.format(jargs['fmriprep-dir'])
    except KeyError: 
        logger.warning('Could not find fmriprep-dir argument in JSON, will perform ciftify-fmriprep from scratch')
        logger.info('Attempting to look for previous freesurfer reconstructions')
        fetch_cmd, symlink_cmd_list = get_existing_freesurfer(jargs,sub_dir,subject) 

    #Generate ciftify singularity call 

    #Transfer over files 


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

def mriqc_fork(jargs,log_tag,sub_dir=None,subject=None): 
    '''
    MRIQC MODULE

    Formulates mriqc bash script content to be written into job file

    Arguments: 
        jargs                               bidsargs in JSON file
        log_tag                             String tag for BASH stout/err redirection to log
        sub_dir,subject                     Strategy pattern consequence

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

def submit_jobfile(job_file,subject,threads,queue):

    '''
    Submit BIDS-app jobfile to queue 

    Arguments: 
        job_file                    Path to BIDSapp job script to be submitted
        subject                     DATMAN style subject ID 
        threads                     Number of threads assigned to each job 
    '''

    #Thread argument if provided
    thread_arg = '-l nodes=1:ppn={threads},walltime=24:00:00'.format(threads=threads) if \
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

def gen_log_redirect(log_dir,subject,app_name): 
    '''
    Convenient function to generate a stdout/stderr redirection to a log file 
    '''
        
    log_tag = '_{}_log.txt'.format(app_name) 
    return ' &>> {}'.format(os.path.join(log_dir,subject + '_dm_bids_app' + log_tag))

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

    log_cmd = (lambda subject,app_name: '') if not log_dir else partial(gen_log_redirect,log_dir=log_dir)
    exclude_cmd_list = [''] if exclude else get_exclusion_cmd(exclude) 

    #Get subjects 
    subjects = subjects or [s for s in os.listdir(config.get_path('nii')) if 'PHA' not in s] 
    subjects = subjects if rewrite else filter_subjects(subjects,out)
    logger.info('Running {}'.format(subjects)) 

    #Process subjects 
    for subject in subjects: 
        
        #Get subject directory and log tag
        sub_dir = os.path.join(out,subject) 
        log_tag = log_cmd(subject=subject,app_name=jargs['app']) 
        try: 
            os.makedirs(sub_dir) 
        except OSError: 
            logger.warning('Subject directory already exists at {}'.format(os.path.join(out,subject)))
        
        #Get commands 
        init_cmd_list = get_init_cmd(study,subject,tmp_dir,sub_dir,jargs['img'],log_tag)
        n2b_cmd = get_nii_to_bids_cmd(study,subject,log_tag) 
        bids_cmd_list = strat_dict[jargs['app']](jargs,log_tag,sub_dir,subject)
        
        #Write commands to executable and submit
        master_cmd = init_cmd_list + [n2b_cmd] + exclude_cmd_list + bids_cmd_list +  ['\n cleanup \n']
        fd, job_file = tempfile.mkstemp(suffix='datman_BIDS_job',dir=tmp_dir) 
        os.close(fd) 
        write_executable(job_file,master_cmd) 

        if not DRYRUN: 
            submit_jobfile(job_file,subject,n_thread,queue)
        
if __name__ == '__main__':
    main()
