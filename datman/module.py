"""
Manages paths. Can be edited to match any environment.
"""

from subprocess import Popen, PIPE
import os

# edit these for a given system
FSBASE = '/opt/quarantine/freesurfer/5.3.0/build'

def load_freesurfer():
    """
    Configures freesurfer. 
    Sets SUBJECTS_DIR to be empty, which must be set or freesurfer will fail.
    Therefore, set SUBJECTS_DIR after loading freesurfer.
    """
    # get syswide paths for later appending
    path = os.getenv('PATH')
    ld_library_path = os.getenv('LD_LIBRARY_PATH')
    perl5lib = os.getenv('PERL5LIB')
    matlabpath = os.getenv('MATLABPATH')

    # set paths
    os.environ['PATH'] = FSBASE + '/bin:' + path
    os.environ['PATH'] = FSBASE + '/mni/bin:' + path
    os.environ['PATH'] = FSBASE + '/fsfast/bin:' + path
    os.environ['PATH'] = FSBASE + '/tktools:' + path
    os.environ['LD_LIBRARY_PATH'] = FSBASE + '/lib'
    os.environ['PERL5LIB'] = FSBASE + '/mni/lib/perl5/5.8.5'
    os.environ['MATLABPATH'] = FSBASE + '/matlab:' + matlabpath
    os.environ['MATLABPATH'] = FSBASE + '/fsfast/toolbox:' + matlabpath

    # set OS env variable
    process = Popen(['uname', '-s'], stdout=PIPE, stderr=PIPE)
    os, _ = process.communicate()
    os.environ['OS'] = os.strip('\n')

    # set a bunch of other variables
    os.environ['FREESURFER_HOME'] = FSBASE
    os.environ['LOCAL_DIR'] = FSBASE + '/local'
    os.environ['FUNCTIONALS_DIR'] = FSBASE + '/sessions'
    os.environ['FSFAST_HOME'] = FSBASE + '/fsfast'
    os.environ['FMRI_ANALYSIS_DIR'] = FSBASE + '/fsfast'
    os.environ['MINC_BIN_DIR'] = FSBASE + '/mni/bin'
    os.environ['MINC_LIB_DIR'] = FSBASE + '/mni/lib'
    os.environ['MNI_DATAPATH'] = FSBASE + '/mni/data'
    os.environ['MNI_DIR'] = FSBASE + '/mni'
    os.environ['FSF_OUTPUT_FORMAT'] = '.nii.gz'
    os.environ['MNI_PERL5LIB'] = FSBASE + '/mni/lib/perl5/5.8.5'
