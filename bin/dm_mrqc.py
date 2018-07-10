#!/usr/bin/env python 

'''
Runs MRIQC Singularity container on datman studies or individual sessions 

Usage: 
    dm_fmriprep [options] <study> 
    dm_fmriprep [options] <study> [<subject_1> ... <subject_n> ] 

Arguments: 
    <study>                         Datman study nickname to be processed by MRIQC
    <subjects>                      List of space-separated datman-style subject IDs

Options: 
    -i, --singularity-image IMAGE           Full path to a MRIQC singularity image [default = '/archive/code/containers/MRIQC/poldrack*mriqc*.img']
    -q, --quiet                             Log only error messages 
    -v, --verbose                           Display informative logging information 
    -d, --debug                             Debug all logging information 
    -o, --out-dir                           Specify a custom output directory for results 
    -r, --rewrite                           Overwrite if MRIQC outputs already exist at --out-dir
    -t, --threads                           Specify the number of threads available to MRIQC (WILL OVERRIDE JSON CONFIGURATION - to make it flexible on varying systems)
    -d, --tmp-dir TMPDIR                    Base directory for MRIQC intermediate ouputs

    -j, --json                              [For MRQC options] - specify a JSON file which will be used to map options into MRQC easily

-----------------------------------------------------------------------------------------------------------------------------------------

NOTES ON JSON: 
If specified, json file is of format: 
{
    'opt_1': 'STRING_VALUE',
    'opt_2': NUMERIC_VALUE,

    #If option is boolean (true/false no parameter)
    'opt_3': 'True/False'
}    


For a full list of potential arguments check out: http://mriqc.readthedocs.io/en/latest/running.html

--json parsing will not validate inputs, that's up to you ;) 

The following arguments WILL NOT be parsed properly from the json file: [-w WORKDIR, --participant_label PARTICIPANT_LABEL {participant,group} [{participant,group}...]]
-w WORKDIR is referenced by --tmp-dir 
--participant_label PARTICIPANT_LABEL since the wrapper script select participants for you to speed up nii_to_bids conversion 

--------------------------------------------------------------------------------------------------------------------------------------------

Requirements: 
    FSL (fslroi) - for nii_to_bids.py

VERSION: TESTING
'''

import os
import sys
import datman.config
import logging
import tempfile
import subprocess as proc
from docopt import docopt 
import json

logging.basicConfig(level = logging.WARN, 
        format='[%(name)s] %(levelname)s %(message)s')
logger = logging.getLogger(os.path.basename(__file__)) 

#Defaults to use 
DEFAULT_SIMG = '/archive/code/containers/MRIQC/poldracklab_mriqc_0.11.0-2018-06-05-1e4ac9792325.img'

def get_bids_name(subject): 
    '''
    Helper function to convert datman to BIDS name 
    Arguments: 
        subject             Datman style subject ID
    '''

    return 'sub-' + subject.split('_')[1] + subject.split('_')[-2]

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
    '''

    try: 
        config = datman.config.config(study=study) 
    except KeyError: 
        logger.error('{} not a valid study ID'.format(study)) 
        sys.exit(1) 

    return config

def filter_processed(subjects,out_dir): 
    '''
    FIlter out subjects that have been previously run through MRIQC

    Arguments: 
        subjects                List of candidate subjects to be processed through the pipeline
        out_dir                 Base directory for where MRIQC outputs will be placed

    Outputs: 
        List of subjects meeting the following criteria: 
            1) Not already processed via fmriprep
            2) Not a phantom (TODO: Modify this to allow for phantom)
    '''


    criteria = lambda x: not os.path.isdir(os.path.join(out_dir,x,'mriqc')) 
    return [s for s in subjects if criteria(s)] 

def gen_pbs_directives(num_threads, subject): 
    '''
    Writes PBS directives into job_file 
    '''

    pbs_directives = '''

    # PBS -l ppn={threads},walltime=24:00:00
    # PBS -V
    # PBS -N fmriprep_{name} 
    
    cd $PBS_O_WORKDIR
    '''.format(threads=num_threads,name=subject) 

    return [pbs_directives] 


#TODO: PARSE ARGUMENTS MORE EFFICIENTLY - MAYBE PORT TO FMRIPREP
def gen_jobcmd(study,subject,simg,sub_dir,tmp_dir,mriqc_args): 
    '''
    Generates a list of commands for setting up and running MRIQC singularity container 

    Arguments: 
        study           DATMAN study shortname
        subject         DATMAN-style subject name 
        simg            Full path to singularity container image
        sub_dir         Full path to MRIQC output directory for subject 
        tmp_dir         Path to store temporary job script and MRIQC working environment 
        mriqc_args      MRIQC argument dictionary
    '''

    #Clean up function in case of crash
    trap_func = '''

    function cleanup(){
        rm -rf $MRHOME
    }

    '''

    init_cmd = '''

    MRHOME=$(mktemp -d {home}) 
    BIDS=$MRHOME/bids
    WORK=$MRHOME/work
    SIMG={simg}
    SUB={sub} 
    OUT={out} 

    mkdir -p $BIDS
    mkdir -p $WORK

    '''.format(home=os.path.join(tmp_dir,'home.XXXXX'),simg=simg,sub=get_bids_name(subject),out=sub_dir)

    #Convert DATMAN to BIDS
    niibids_cmd = '''

    nii_to_bids.py {study} {subject} --bids-dir $BIDS

    '''

    mrqc_cmd = '''
    
    #trap cleanup EXIT
    singularity run -B $BIDS:/bids -B $WORK:/work -B $OUT:/out -B \\
    $SIMG \\
    /bids /out -w /work \\
    participant --participant-label $SUB \\
    {argdict}

    '''.format(argdict = ' '.join[k + ' ' + v for k,v in mriqc_args.items()])

    return [trap_func, init_cmd, niibids_cmd, mrqc_cmd]

def write_executable(f,cmds): 
    '''
    Helper script to write an executable file

    Arguments:
        f               Full file path
        cmds            List of commands to write
    '''

    header = '#!/bin/bash \n'

    with open(f,'w') as cmdfile:
        cmdfile.write(header)
        cmdfile.writelines(cmds)

    os.chmod(f,0o775)
    logger.info('Successfully wrote commands to {}'.format(f)) 

def submit_jobfile(job_file, augment_cmd=''):

    '''
    Submit mriqc job

    Arguments:
        job_file            Path to mriqc job script to be submitted
        augment_cmd         Optional command that appends additional options to qsub
    '''

    #Formulate command
    cmd = 'qsub {job} '.format(job=job_file) + augment_cmd

    #Submit jobfile and delete after successful submission 
    logger.info('Submitting job with command: {}'.format(cmd)) 
    p = proc.Popen(cmd, stdin=proc.PIPE, stdout=proc.PIPE, shell=True) 
    std, err = p.communicate() 

    if p.returncode:
        logger.error('Failed to submit job, STDERR: {}'.format(err)) 
        sys.exit(1) 

    logger.info('Removing jobfile...') 
    os.remove(job_file)

def get_mriqc_args(json_file,num_threads): 

    '''
    Pulls list of arguments to directly input into MRQC as a chain of commands    
    Returns list of MRQC arguments formatted as --key:value dictionary

    Checks json if avilable and num_threads (overrides json!)
    '''
    
    #Placeholder key-value to input nothing
    args = {'':''} 

    #Use json if available
    if json_file: 
        with open(json_file,'r') as jfile: 
            j = {'--'+k:v for k,v in json.read(jfile) if str(v).lower() != 'false'}
    args.update(j) 

    #Use num_threads if available
    if num_threads: 
        args.update({'--n_cpus' : num_threads})

    #Final filtering, convert True --> '' since its parameterless
    args = {k:'' for k,v in args if str(v).lower() == 'true'}

    logger.debug('Successfully extracted MRIQC argument dict: {}'.format(args)) 
    return args
    

def main(): 

    arguments = docopt(__doc__) 

    study           =   arguments['<study>'] 
    subjects        =   arguments['<subjects>'] 

    singularity_img =   arguments['--singularity-image'] 

    out_dir         =   arguments['--out-dir'] 
    tmp_dir         =   arguments['--tmp-dir'] 
    
    debug           =   arguments['--debug'] 
    verbose         =   arguments['--verbose'] 
    rewrite         =   arguments['--rewrite'] 
    num_threads     =   arguments['--num_threads'] 

    json_file       =   arguments['--json']

    #Configuration block
    configure_logger(quiet,verbose,debug) 
    config = get_datman_config(study) 
    system = config.site_config['SystemSettings'][config.system]['QUEUE'] 
    DEFAULT_OUT = os.path.join(config.get_study_base(),'pipelines','mriqc') 

    #Optional variable processing
    singularity_img = singularity_img if singularity_img else DEFAULT_SIMG
    out_dir = out_dir if out_dir else DEFAULT_OUT
    tmp_dir = tmp_dir if tmp_dir else '/tmp/' 

    #MRIQC argument extraction
    mrqc_args = get_mriqc_args(json_file,num_threads)
    ppn = mrqc_args['--n_cpus'] if '--n_cpus' in mrqc_args else None 

    #Subject filtering
    if not subjects: 
        subjects = [s for s in os.listdir(config.get_path('nii')) if 'PHA' not in s] 

    if not rewrite: 
        subjects = filter_processed(subjects,out_dir) 

    #Processing
    for subjects in subjects: 

        sub_dir = os.path.join(out_dir,subject) 
        try: 
            os.makedirs(sub_dir) 
        except OSError: 
            logger.warning('Subject directory already exists, outputting mriqc to {}'.format(sub_dir)) 

        #Generate job file in temporary directory and close (cause tempfile.mkstemp is dumb) 
        fd,job_file = tempfile.mkstemp(suffix='mriqc_job',dir=tmp_dir) 
        os.close(fd) 

        #Generate schedular specific calls 
        pbs_directives = [''] 
        if system == 'pbs': 
            pbs_directives = gen_pbs_directives(ppn,subject) 
            augment_cmd = '' 
        elif system == 'sge': 
            augment_cmd = ' -V -l ppn={}'.format(ppn) if ppn else '' 
            augment_cmd += ' -N mriqc_{}'.format(subject) 

        mriqc_cmd = gen_jobcmd(study,subject,singularity_img,sub_dir,tmp_dir,mrqc_args)

        #Formulate final command list
        master_cmd = pbs_directives + mriqc_cmd #+ ['\n cleanup \n']
        write_executable(job_file,master_cmd) 
        #submit_jobfile(job_file,augment_cmd)
    

