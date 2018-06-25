#!/usr/bin/env python 

'''
Runs fmriprep minimal processing pipeline on datman studies or individual sessions 

Usage: 
    dm_fmriprep [options] <study> [<subjects>...] 

Arguments:
    <study>                 datman study nickname to be processed by fmriprep 
    <subjects>              List of space-separated datman-style subject IDs

Options: 
    -i, --singularity-image     Specify a custom fmriprep singularity image to use [default='/archive/code/containers/FMRIPREP/poldrack*fmriprep*.img']
    -q, --quiet                 Only show WARNING/ERROR messages
    -v, --verbose               Display lots of logging information
    -d, --debug                 Display all logging information 
    -o, --out-dir               Location of where to output fmriprep outputs [default = /config_path/<study>/pipelines/fmriprep]
    -r, --rewrite               Overwrite if fmriprep pipeline outputs already exist in output directory
    --fs-license-dir            Freesurfer license path [default = /opt/quaratine/freesurfer/6.0.0/build/license.txt]

Requirements: 
    FSL (fslroi)
'''

import os 
import sys
import datman.config
import logging
import tempfile
import subprocess as proc
import pdb

from docopt import docopt

logging.basicConfig(level = logging.WARN, 
        format='[%(name)s] %(levelname)s : %(message)s')
logger = logging.getLogger(os.path.basename(__file__))


#Defaults
DEFAULT_FS_LICENSE = '/opt/quarantine/freesurfer/6.0.0/build/license.txt'
DEFAULT_SIMG = '/archive/code/containers/FMRIPREP/poldracklab_fmriprep_1.1.1-2018-06-07-2f08547a0732.img'

def configure_logger(quiet,verbose,debug): 
    '''
    Configure logger settings for script session 
    TODO: Configure log to server
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
        logger.error('{} not a valid study ID!'.format(study))
        sys.exit(1) 

    return config

def run_bids_conversion(study,subject,config): 
    '''
    Wrapper function for running /datman/bin/nii_to_bids.py. 
    Assume it does all the validation checking so we don't have to :) 
    TODO: Add a check so we don't re-run nii-to-bids!
    '''

    nii2bds_cmd = 'nii_to_bids.py {study} {subject}'.format(study=study,subject = ' '.join(subject))

    p = proc.Popen(nii2bds_cmd, stdout=proc.PIPE, stdin=proc.PIPE, shell=True)  
    std, err = p.communicate() 

    if p.returncode: 
        logger.error('datman to BIDS conversion failed! STDERR: {}'.format(err)) 
        sys.exit(1) 

    try:
        os.listdir(os.path.join(config.get_path('data'),'bids'))
    except OSError:
        logger.error('BIDS directory failed to initialize! Please run nii_to_bids.py manually to debug!')
        logger.error('Failed command: {}'.format(nii2bds_cmd))
    return

def initialize_environment(config,subject,out_dir=None): 

    '''
    Initializes environment for fmriprep mounting
    Arguments: 
        config              Datman configuration object (datman.config.config)
        subject             Subject to create environment for
        out_dir             Base directory for fmriprep outputs
    '''

    pipeline_dir = os.path.join(config.get_study_base(),'pipelines','fmriprep',subject) 

    #Initialize pipeline output directory
    if not out_dir: 
        logger.info('No out_dir argument. Creating fmriprep outputs at {}'.format(pipeline_dir))
        out_dir = pipeline_dir 
    try: 
        os.makedirs(out_dir) 
    except OSError: 
        logger.info('Path already exists, fmriprep output directories will be created within: {}'.format(out_dir))  

    bids_dir = os.path.join(config.get_path('data'),'bids') 

    return {'out' : out_dir, 'bids' : bids_dir}
    

def get_proj_subjects(config,rewrite): 
    '''
    Fetch non-phantom subjects from project data directory 

    Arguments: 
        config                  datman.config object with study already set

    Outputs: 
        List of subjects meeting criteria: 
            1) Not already processed via fmriprep
            2) Not a phantom
    '''

    pipeline_dir = os.listdir(os.path.join(config.get_study_base(),'pipelines','fmriprep'))
    
    if not rewrite: 
        criteria = lambda x: (x not in pipeline_dir) and ('PHA' not in x)
    else: 
        critera = lambda x: ('PHA' not in x) 

    return [s for s in os.listdir(config.get_path('nii')) if criteria(s)]
    
    
def gen_jobscript(simg,env,subject,fs_license): 

    '''
    Write a singularity job script to submit; complete with cleanup management
    
    Arguments: 
        env                 A dictionary containing fmriprep mounting directories: {base: <base directory>, work: <base/{}_work>, home: <base/{}_home>, out: <output_dir>,license: <base/{}_li}
        simg                fmriprep singularity image

    Output: 
        job_file            Full path to jobfile
    '''
    
    #Make job file
    _,job_file = tempfile.mkstemp(suffix='fmriprep_job') 

    #Bids subject identifier
    bids_sub = subject.split('_')[1] + '-' + subject.split('_')[-2]

    #Interpreter
    header = '#!/bin/bash'

    #Cleanup function 
    trap_func = '''

    function cleanup(){
        echo "Cleaning $HOME" >> /scratch/jjeyachandra/tmp/testing.txt
        rm -rf $HOME
    }

    '''

    #Temp initialization
    init_cmd = '''

    HOME=$(mktemp -d /tmp/home.XXXXX)
    WORK=$(mktemp -d $HOME/work.XXXXX)
    LICENSE=$(mktemp -d $HOME/li.XXXXX)
    BIDS={bids}
    SIMG={simg}
    SUB={sub}
    OUT={out}

    '''.format(bids=env['bids'],simg=simg,sub=bids_sub,out=env['out'])

    #Fetch freesurfer license 
    fs_cmd =  '''

    cp {} $LICENSE/license.txt
    cat $LICENSE/license.txt >> /scratch/jjeyachandra/tmp/testing.txt

    '''.format(fs_license if fs_license else DEFAULT_FS_LICENSE)

    
    cmd = '''
    trap cleanup EXIT 
    singularity run -H $HOME -B $BIDS:/bids -B $WORK:/work -B $OUT:/out -B $LICENSE:/li 
    $SIMG 
    /bids /out 
    participant --participant-label $SUB 
    --fs-license-file /li/license.txt

    '''

    #Testing function 
    echo_func = '''

    echo $HOME >> /scratch/jjeyachandra/tmp/testing.txt
    echo $WORK >> /scratch/jjeyachandra/tmp/testing.txt
    echo $LICENSE >> /scratch/jjeyachandra/tmp/testing.txt
    echo $BIDS >> /scratch/jjeyachandra/tmp/testing.txt
    echo $SIMG >> /scratch/jjeyachandra/tmp/testing.txt
    echo $SUB >> /scratch/jjeyachandra/tmp/testing.txt
    echo $OUT >> /scratch/jjeyachandra/tmp/testing.txt

    '''

    #Run post-cleanup if successful
    cleanup = '\n cleanup \n'


    #Write job-file
    write_executable(job_file,[header,trap_func,init_cmd,fs_cmd,echo_func,cleanup]) 

    logger.debug('Successfully wrote to {}'.format(job_file))

    return job_file

def write_executable(f,cmds): 
    '''
    Helper script to write an executable file

    Arguments: 
        f                       Full file path
        cmds                    List of commands to write, will separate with \n
    '''

    with open(f,'w') as cmdfile: 
        cmdfile.writelines(cmds)

    p = proc.Popen('chmod +x {}'.format(f), stdin=proc.PIPE, stdout=proc.PIPE, shell=True) 
    std, err = p.communicate() 
    if p.returncode: 
        logger.error('Failed to change permissions on {}'.format(f)) 
        logger.error('ERR CODE: {}'.format(err)) 
        sys.exit(1) 

def submit_jobfile(job_file): 

    '''
    Submit fmriprep jobfile

    Arguments: 
        job_file                    Path to fmriprep job script to be submitted
    '''

    cmd = 'qsub -V {}'.format(job_file)

    logger.info('Submitting job with command: {}'.format(cmd)) 

    p = proc.Popen(cmd, stdin=proc.PIPE, stdout=proc.PIPE, shell=True) 
    std,err = p.communicate() 
    
    if p.returncode: 
        logger.error('Failed to submit job, STDERR: {}'.format(err)) 
        sys.exit(1) 

    #Delete jobfile
    logger.info('Removing jobfile...')
    os.remove(job_file)
    
def main(): 
    
    arguments = docopt(__doc__) 

    study                       = arguments['<study>']
    subjects                     = arguments['<subjects>']
    singularity_img             = arguments['--singularity-image']
    out_dir                     = arguments['--out-dir']
    fs_license                  = arguments['--fs-license-dir']

    debug                       = arguments['--debug'] 
    quiet                       = arguments['--quiet'] 
    verbose                     = arguments['--verbose'] 
    rewrite                     = arguments['--rewrite']
    
    singularity_img = singularity_img if singularity_img else DEFAULT_SIMG

    #Global initialization routines
    configure_logger(quiet,verbose,debug) 
    config = get_datman_config(study)

    #run_bids_conversion(study, subjects, config) 
    bids_dir = os.path.join(config.get_path('data'),'bids') 

    if not subjects: 
        subjects = get_proj_subjects(config)

    for subject in subjects: 

        env = initialize_environment(config, subject, out_dir)
        job_file = gen_jobscript(singularity_img,env,subject,fs_license) 
        submit_jobfile(job_file) 



if __name__ == '__main__': 
    main() 
