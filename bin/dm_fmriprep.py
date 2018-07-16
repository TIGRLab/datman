#!/usr/bin/env python 

'''
Runs fmriprep minimal processing pipeline on datman studies or individual sessions 

Usage: 
    dm_fmriprep [options] <study> 
    dm_fmriprep [options] <study> [<subjects>...] 

Arguments:
    <study>                 datman study nickname to be processed by fmriprep 
    <subjects>              List of space-separated datman-style subject IDs

Options: 
    -i, --singularity-image IMAGE     Specify a custom fmriprep singularity image to use [default='/archive/code/containers/FMRIPREP/poldrack*fmriprep*.img']
    -q, --quiet                 Only show WARNING/ERROR messages
    -v, --verbose               Display lots of logging information
    -d, --debug                 Display all logging information 
    -o, --out-dir               Location of where to output fmriprep outputs [default = /config_path/<study>/pipelines/fmriprep]
    -r, --rewrite               Overwrite if fmriprep pipeline outputs already exist in output directory
    -f, --fs-license-dir FSLISDIR          Freesurfer license path [default = /opt/quaratine/freesurfer/6.0.0/build/license.txt]
    -t, --threads NUM_THREADS,OMP_THREADS              Formatted as threads,omp_threads, which indicates total number of threads and # of threads per process [Default: use all available threads]
    --ignore-recon              Use this option to perform reconstruction even if already available in pipelines directory
    -d, --tmp-dir TMPDIR        Specify custom temporary directory (when using remote servers with restrictions on /tmp/ writing) 
    -l, --log LOGDIR,verbosity  Specify fmriprep log output directory and level of verbosity (according to fmriprep). Example [/logs/,vvv] will output to /logs/<SUBJECT>_fmriprep_log.txt with extremely verbose output     
    -e, --exclude [<TAG>,...,<TAG>]              Exclude certain file tags from BIDS output, this is to prevent certain BIDS apps from automatically using images we don't want them to use, a regex will be applied around the tag as *<TAG>*. Format: <TAG1>,<TAG2>,...,<TAGN>
    
Requirements: 
    FSL (fslroi) - for nii_to_bids.py

Note:
    FMRIPREP freesurfer module combines longitudinal data in order to enhance surface reconstruction, however sometimes we want to maintain both reconstructions 
    for temporally varying measures that are extracted from pial surfaces. 

    Thus the behaviour of the script is as follows: 
        a) If particular session is coded XX_XX_XXXX_0N where N > 1. Then the original reconstructions will be left behind and a new one will be formed 
        b) For the first run, the original freesurfer implementation will always be symbolically linked to fmriprep's reconstruction (unless a new one becomes available)  

VERSION: LOGGING FMRIPREP 
'''

import os 
import sys
import datman.config
import logging
import tempfile
import subprocess as proc
from docopt import docopt

logging.basicConfig(level = logging.WARN, 
        format='[%(name)s] %(levelname)s : %(message)s')
logger = logging.getLogger(os.path.basename(__file__))


#Defaults (will only work correctly in tigrlab environment -- fix) 
DEFAULT_FS_LICENSE = '/opt/quarantine/freesurfer/6.0.0/build/license.txt'
DEFAULT_SIMG = '/archive/code/containers/FMRIPREP/poldracklab_fmriprep_1.1.1-2018-06-07-2f08547a0732.img'

def get_bids_name(subject): 
    '''
    Helper function to convert datman to BIDS name
    Arguments: 
        subject                     Datman style subject ID
    '''

    return 'sub-' + subject.split('_')[1] + subject.split('_')[-2]

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

    #Check if study argument was incorrectly inputted as subject
    if study != config.study_name: 
        logger.error('Study incorrectly entered as subject {}! Exiting..'.format(study)) 
        sys.exit(1) 

    return config

def fetch_fs_recon(config,subject,sub_out_dir): 
    '''
    Copies over freesurfer reconstruction to fmriprep pipeline output for auto-detection

    Arguments: 
        config                      datman.config.config object with study initialized
        subject                     datman style subject ID
        sub_out_dir                 fmriprep output directory for subject

    Output: 
        Return r-sync command
    '''
    
    #Check whether freesurfer directory exists for subject
    fs_recon_dir = os.path.join(config.get_study_base(),'pipelines','freesurfer',subject) 
    fmriprep_fs = os.path.join(sub_out_dir,'freesurfer',get_bids_name(subject)) 

    if os.path.isdir(fs_recon_dir): 
        logger.info('Located FreeSurfer reconstruction files for {}, copying (rsync) to {}'.format(subject,fmriprep_fs))

        #Create a freesurfer directory in the output directory
        try: 
            os.makedirs(fmriprep_fs) 
        except OSError: 
            logger.warning('Failed to create directory {} already exists!'.format(fmriprep_fs)) 

        #Rsync, dereference as fmriprep is directory constrained
        cmd = '''
        
        rsync -L -a {recon_dir} {out_dir}
        
        '''.format(recon_dir=os.path.join(fs_recon_dir,''),out_dir=fmriprep_fs)
        
        return [cmd]
    else:
        return []


def filter_processed(subjects, out_dir): 

    '''
    Filter out subjects that have already been previously run through fmriprep

    Arguments: 
        subjects                List of candidate subjects to be processed through pipeline
        out_dir                 Base directory for where fmriprep outputs will be placed

    Outputs: 
        List of subjects meeting criteria: 
            1) Not already processed via fmriprep
            2) Not a phantom
    '''

    criteria = lambda x: not os.path.isdir(os.path.join(out_dir,x,'fmriprep')) 
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
    '''.format(threads=num_threads, name=subject)

    return [pbs_directives]

def get_exclusion_cmd(exclude): 
    '''
    Returns a deletion command for each tag in exclude
    
    Arguments: 
        exclude                 List of string tags to be excluded from subject bids folder
    '''

    exclusion_cmd = '\n'.join(['find $BIDS -name *{tag}* -delete'.format(tag=tag) for tag in exclude]) 
    return exclusion_cmd


def gen_jobcmd(study,subject,simg,sub_dir,tmp_dir,fs_license,num_threads,log_opt,exclude): 

    '''
    Generates list of job submission commands to be written into a job file
    
    Arguments: 
        study               DATMAN study shortname
        subject             DATMAN-style subject name
        simg                Full path to singularity container image
        sub_dir             Full path to fmriprep output directory for subject
        tmp_dir             Path to store temporary job script and fmriprep working environment in 
        fs_license          Full path to freesurfer license
        num_threads         Number of threads to utilize [format threads,omp_threads]

    Output: 
        [list of commands to be written into job file]
    '''
    
    #Configure logging option
    log_dir_cmd = ''
    verbosity_cmd = ''
    if log_opt: 
        log_list = log_opt.split(',') 
        log_dir, log_level = log_list[0], log_list[1]
        verbosity_cmd = ' -{}'.format(log_level)
        log_dir_cmd = ' &>> {}'.format(os.path.join(log_dir,subject + '_fmriprep_log.txt'))

        
    #Cleanup function 
    trap_func = '''

    function cleanup(){
        rm -rf $FMHOME
    }

    '''

    #Variable and directory initialization
    init_cmd = '''

    FMHOME=$(mktemp -d {home})
    LICENSE=$FMHOME/li
    BIDS=$FMHOME/bids
    WORK=$FMHOME/tmpwork/
    SIMG={simg}
    SUB={sub}
    OUT={out}

    mkdir -p $LICENSE
    mkdir -p $BIDS
    mkdir -p $WORK

    echo $FMHOME {log_cmd} 
    '''.format(home=os.path.join(tmp_dir,'home.XXXXX'),simg=simg,sub=get_bids_name(subject),out=sub_dir,log_cmd = log_dir_cmd)

    #Datman to BIDS conversion command
    niibids_cmd = '''

    nii_to_bids.py {study} {subject} --bids-dir $BIDS {log_cmd}

    '''.format(study=study,subject=subject,log_cmd = log_dir_cmd)

    #Exclusions following nii_2_bids
    exclude_cmd = '' 
    if exclude: 
        exclude_cmd = get_exclusion_cmd(exclude) 
        

    #Fetch freesurfer license 
    fs_cmd =  '''

    cp {} $LICENSE/license.txt

    '''.format(fs_license if fs_license else DEFAULT_FS_LICENSE)

    #Extract thread information 
    thread_arg = ''
    if num_threads:
        thread_list = num_threads.split(',') 
        threads,omp_threads = thread_list[0], thread_list[1]
        thread_arg = ' --nthreads {} --omp-nthreads {}'.format(threads,omp_threads)

    
    fmri_cmd = '''

    trap cleanup EXIT 
    singularity run -H $FMHOME -B $BIDS:/bids -B $WORK:/work -B $OUT:/out -B $LICENSE:/li \\
    $SIMG {log} \\
    /bids /out -w /work \\
    participant --participant-label $SUB --use-syn-sdc \\
    --fs-license-file /li/license.txt {thread} {log_cmd}

    '''.format(log=verbosity_cmd, thread=thread_arg, log_cmd = log_dir_cmd)

    return [trap_func,init_cmd,niibids_cmd,exclude_cmd,fs_cmd,fmri_cmd] 

def get_symlink_cmd(jobfile,config,subject,sub_out_dir): 
    '''
    Returns list of commands that remove original freesurfer directory and link to fmriprep freesurfer directory

    Arguments: 
        jobfile                 Path to jobfile to be modified 
        config                  datman.config.config object with study initialized
        subject                 Datman-style subject ID
        sub_out_dir             fmriprep subject output path

    Outputs: 
        [remove_cmd,symlink_cmd]    Removal of old freesurfer directory and symlinking to fmriprep version of freesurfer reconstruction
    '''

    #Path to fmriprep output and freesurfer recon directories
    fmriprep_fs_path = os.path.join(sub_out_dir,'freesurfer')
    fs_recon_dir = os.path.join(config.get_study_base(),'pipelines','freesurfer',subject) 

    #Remove entire subject directory, then symlink in the fmriprep version
    remove_cmd = '\nrm -rf {} \n'.format(fs_recon_dir) 
    symlink_cmd = 'ln -s {} {} \n'.format(fmriprep_fs_path,fs_recon_dir)
    
    return [remove_cmd, symlink_cmd]


def write_executable(f,cmds): 
    '''
    Helper script to write an executable file

    Arguments: 
        f                       Full file path
        cmds                    List of commands to write, will separate with \n
    '''
    
    #BASH interpreter + exit upon error
    header = '#!/bin/bash \n set -e \n'

    with open(f,'w') as cmdfile: 
        cmdfile.write(header) 
        cmdfile.writelines(cmds)

    os.chmod(f,0o775)

    logger.info('Successfully wrote commands to {}'.format(f))

def submit_jobfile(job_file, subject,ppn): 

    '''
    Submit fmriprep jobfile

    Arguments: 
        job_file                    Path to fmriprep job script to be submitted
        subject                     DATMAN-style subject ID
    '''

    #Formulate command
    cmd = 'qsub -l nodes=1:ppn={ppn},walltime=24:00:00 -V -N {subject} {job}'\
    .format(ppn=ppn, subject=subject, job=job_file)

    #Submit jobfile and delete after successful submission
    logger.info('Submitting job with command: {}'.format(cmd)) 
    p = proc.Popen(cmd, stdin=proc.PIPE, stdout=proc.PIPE, shell=True) 
    std,err = p.communicate() 
    
    if p.returncode: 
        logger.error('Failed to submit job, STDERR: {}'.format(err)) 
        sys.exit(1) 

    logger.info('Removing jobfile...')
    os.remove(job_file)

def main(): 
    
    arguments = docopt(__doc__) 

    study                       = arguments['<study>']
    subjects                     = arguments['<subjects>']

    singularity_img             = arguments['--singularity-image']

    out_dir                     = arguments['--out-dir']
    tmp_dir                     = arguments['--tmp-dir']
    fs_license                  = arguments['--fs-license-dir']

    debug                       = arguments['--debug'] 
    quiet                       = arguments['--quiet'] 
    verbose                     = arguments['--verbose'] 
    rewrite                     = arguments['--rewrite']
    ignore_recon                = arguments['--ignore-recon']
    num_threads                 = arguments['--threads']
    log_opt                     = arguments['--log']
    exclude                     = arguments['--exclude'] 
    
    #Configure dm_fmriprep logger
    configure_logger(quiet,verbose,debug) 

    #Configuration
    config = get_datman_config(study)
    keeprecon = config.get_key('KeepRecon') 
    ppn = num_threads.split(',')[0]

    #Configure settings with defaults
    singularity_img = singularity_img if singularity_img else DEFAULT_SIMG
    DEFAULT_OUT = os.path.join(config.get_study_base(),'pipelines','fmriprep') 
    out_dir = out_dir if out_dir else DEFAULT_OUT
    tmp_dir = tmp_dir if tmp_dir else '/tmp/'

    #Get exclusion command
    exclude = exclude.split(',') 

    #Filter subjects
    if not subjects: 
        subjects = [s for s in os.listdir(config.get_path('nii')) if 'PHA' not in s] 

    if not rewrite: 
        subjects = filter_processed(subjects,out_dir) 

    #Process subjects
    for subject in subjects: 

        sub_dir = os.path.join(out_dir,subject) 
        try: 
            os.makedirs(sub_dir) 
        except OSError: 
            logger.warning('Subject directory already exists, outputting fmriprep to {}'.format(sub_dir))

        #Generate a job file in temporary directory
        fd,job_file = tempfile.mkstemp(suffix='fmriprep_job',dir=tmp_dir) 
        os.close(fd) 

        #Main command, TODO: Make consistent commands into a dictionary with implicit defaults
        fmriprep_cmd = gen_jobcmd(study,subject,singularity_img,sub_dir,tmp_dir,fs_license,num_threads,log_opt,exclude) 

        #symlink depending on study type (longitudinal/cross-sectional) 
        symlink_cmd = [''] 
        fetch_cmd = ['']
        if not ignore_recon or not keeprecon:

            fetch_cmd = fetch_fs_recon(config,subject,sub_dir) 
            
            if fetch_cmd: 
                symlink_cmd = get_symlink_cmd(job_file,config,subject,sub_dir)       
        
        #Formulate final command list and append final cleanup line
        master_cmd = fetch_cmd + fmriprep_cmd + symlink_cmd + ['\n cleanup \n']
        write_executable(job_file, master_cmd)
        submit_jobfile(job_file,subject,ppn) 

if __name__ == '__main__': 
    main() 
