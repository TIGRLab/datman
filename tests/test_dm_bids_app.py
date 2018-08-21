#!/usr/bin/env python

import os
import unittest
import importlib
import logging
from mock import patch, mock_open
import nose, pytest
import subprocess as proc
import shutil
import unittest

ba = importlib.import_module("bin.dm_bids_app") 
scanid = importlib.import_module("datman.scanid")
logging.disable(logging.CRITICAL) 

file_path = os.path.abspath(os.path.join(os.path.realpath(__file__),os.path.pardir)) 
FIXTURE = os.path.join(file_path,'fixture_dm_bids_app') 
json_config = os.path.join(FIXTURE,'test_jsons','mock_json.json')
bad_json = os.path.join(FIXTURE,'test_jsons','bad_json.json')
output_path = os.path.join(FIXTURE,'out')
fs_dir = os.path.join(FIXTURE,'freesurfer') 

def test_get_json_args_returns_formatted_dict(): 

    expected_out = {'img': 'potato', 'app': 'FMRIPREP','bidsargs' :{'--test_int':'10','--test_bool':''}}
    actual_out = ba.get_json_args(json_config) 

    assert expected_out == actual_out 

def test_validate_json_on_good_json():

    jargs = {'img': 'potato', 'app': 'FMRIPREP','bidsargs':''}
    test_dict = {'FMRIPREP' : ''}
    assert ba.validate_json_args(jargs,test_dict) == True

def test_filter_subjects_filters_preexisting_directories(): 

    subjects = ['POTATO1','POTATO2','POTATO3','POTATO4','POTATO5']
    expected_out = ['POTATO1','POTATO5']
    assert set(ba.filter_subjects(subjects,output_path)) == set(expected_out)

def test_group_subjects_correctly_groups_by_subject_ID_when_longitudinal(): 

    subjects = ['POTATO_01','POTATO_0233','POTATO_1234'] 
    expected_out = {'POTATO': ['POTATO_01','POTATO_0233','POTATO_1234']} 

    actual_out = ba.group_subjects(subjects,True) 

    assert expected_out.keys() == actual_out.keys() 
    assert set(actual_out.values()[0]) == set(expected_out.values()[0]) 

def test_group_subjects_correctly_maps_onto_self_when_cross_sectional(): 

    subjects = ['POTATO_01','POTATO_0233','POTATO_1234'] 
    expected_out = {'POTATO_01' : ['POTATO_01'], 'POTATO_0233' : ['POTATO_0233'], 'POTATO_1234' : ['POTATO_1234']}

    actual_out = ba.group_subjects(subjects,False) 

    assert actual_out == expected_out 

def test_gen_log_redirect_provides_correct_tag(): 

    log_dir = 'log_dir'
    subject = 'subject'
    app_name = 'app'

    expected_out = ' &>> log_dir/subject_dm_bids_app_app_log.txt' 

    assert ba.gen_log_redirect(log_dir,subject,app_name) == expected_out

    
@patch('os.makedirs') 
def test_fs_fetch_recon_returns_rsync_when_recon_found(mock_makedir): 

    subject = 'SPN01_CMH_1234_01' 
    exp_dir = os.path.join(output_path,'freesurfer','sub-CMH1234') 
    sub_dir = os.path.join(output_path) 
    
    expected_cmd = '''

    rsync -L -a {recon_dir}/ {out_dir}

    '''.format(recon_dir=os.path.join(fs_dir,subject),out_dir = exp_dir) 

    mock_makedir.returnvalue = ''

    assert ba.fetch_fs_recon(fs_dir,sub_dir,subject).replace(' ','') == expected_cmd.replace(' ','')

@patch('os.makedirs') 
def test_fs_fetch_recon_returns_nothing_if_no_recon(mock_makedir): 

    subject = 'SPN01_CMH_4321_01' 
    sub_dir = os.path.join(output_path,subject) 

    mock_makedir.returnvalue = ''
    assert ba.fetch_fs_recon(fs_dir,sub_dir,subject).replace(' ','') == ''
    
def test_get_exclusion_cmd_formats_correctly(): 

    tags = ['HI','EXCLUDE','ME']
    
    expected_out = ['find $BIDS -name *HI* -delete', 'find $BIDS -name *EXCLUDE* -delete', 
                    'find $BIDS -name *ME* -delete']

    assert set(ba.get_exclusion_cmd(tags)) == set(expected_out) 

def test_get_symlink_cmd_returns_correct_command(): 

    subject = 'SPN01_CMH_1234_01'
    sub_dir = os.path.join(output_path,subject) 

    exp_sub_fmriprep_fs = os.path.join(sub_dir,'freesurfer','sub-CMH1234')
    sub_fs_dir = os.path.join(fs_dir,subject) 

    exp_rm_cmd = '\n rm -rf {} \n'.format(sub_fs_dir) 
    exp_symlink_cmd = 'ln -s {} {} \n'.format(exp_sub_fmriprep_fs,sub_fs_dir) 

    rm_cmd, sym_cmd = ba.get_symlink_cmd(fs_dir,sub_dir,subject) 

    assert (rm_cmd.replace(' ','') == exp_rm_cmd.replace(' ','')) and \
            (sym_cmd.replace(' ','') == exp_symlink_cmd.replace(' ',''))
    

def test_get_bids_name_returns_correct_bids_name(): 

    subject = 'SPN01_CMH_13395_01'
    assert ba.get_bids_name(subject) == 'sub-CMH13395'

def test_get_bids_name_fails_when_given_incorrect_name(): 

    subject = 'SPN01_FAILME'
    
    with pytest.raises(scanid.ParseException): 
        ba.get_bids_name(subject) 

@patch('os.chmod') 
def test_write_executable_writes_to_file_correctly(mock_chmod): 
    
    cmds = ['i','am','a','command']
    dest_path = "some/fake/file"
    mock_chmod.returnvalue = ''

    dest_file_mock = mock_open() 
    with patch('__builtin__.open', dest_file_mock): 

        ba.write_executable(dest_path,cmds) 

    dest_file_mock().writelines.assert_called_once_with(cmds) 

@patch('os.chmod')
def test_write_executable_fails_if_chmod_fails(mock_chmod): 

    mock_chmod.side_effect = OSError() 
    cmds = ['i','am','a','fake','file']
    f = '/some/random/path'

    dest_file_mock = mock_open() 

    with pytest.raises(OSError): 
        with patch('__builtin__.open',dest_file_mock): 
            ba.write_executable(f,cmds) 
    

def test_validate_json_on_bad_json(): 

    jargs = {'i_am_bad' : True} 
    test_dict = {'FMRIPREP':''}

    with pytest.raises(KeyError): 
        ba.validate_json_args(jargs,test_dict)  


def test_get_requested_threads_returns_int_given_string(): 

    thread_dict = {'FMRIPREP' : '--nthreads', 
                   'MRIQC' : '--n_procs'}
    jargs = {'app':'FMRIPREP', 'bidsargs':{'--nthreads' : 5}}

    ba.get_requested_threads(jargs,thread_dict) 
    assert ba.get_requested_threads(jargs,thread_dict) == 5

def test_get_requested_threads_returns_int_given_int(): 

    thread_dict = {'FMRIPREP' : '--nthreads', 
                   'MRIQC' : '--n_procs'}

    jargs = {'app':'FMRIPREP', 'bidsargs':{'--nthreads' : 5}}
    assert ba.get_requested_threads(jargs,thread_dict) == 5

def test_get_requested_threads_fails_on_float():

    thread_dict = {'FMRIPREP' : '--nthreads', 
                   'MRIQC' : '--n_procs'}
    jargs = {'app':'FMRIPREP', 'bidsargs':{'--nthreads' : 5.4}}

    with pytest.raises(TypeError):
        ba.get_requested_threads(jargs,thread_dict) 

def test_get_requested_threads_fails_on_str_float(): 

    thread_dict = {'FMRIPREP' : '--nthreads', 
                   'MRIQC' : '--n_procs'}

    jargs = {'app':'FMRIPREP', 'bidsargs':{'--nthreads' : '10.23'}}
    
    with pytest.raises(TypeError): 
        ba.get_requested_threads(jargs,thread_dict) 
    

def test_fmriprep_fork_fails_when_no_fs_license_in_dict(): 

    jargs = {'app': 'FMRIPREP', 'test' : 'value'} 
    log_tag = ''
    sub_dir = '' 
    subject = '' 
    
    with pytest.raises(KeyError):  
        ba.fmriprep_fork(jargs,log_tag,sub_dir,subject) 

#Suite of tests for checking BASH outputs from dm_bids_app 
class TestBASHCommands(unittest.TestCase): 

    def setUp(self): 
        #Create a temporary directory for outputting BASH cmds
        self.tmpdir = os.path.join(FIXTURE,'BASH_testing','test_instance')
        os.makedirs(self.tmpdir) 

    def tearDown(self): 
        #Remove the temp directory at the end of testing 
        shutil.rmtree(self.tmpdir) 

    def test_get_init_cmd_creates_correct_directories(self):

        #Set up test_path 
        os.makedirs(os.path.join(self.tmpdir,'correct_directories'))

        #Arguments 
        subject = 'SPN01_CMH_1234_01'
        study= 'SPINS' 
        test_dir = os.path.join(self.tmpdir,'correct_directories')
        sub_dir = 'test'
        simg = 'some_image.img'
        log_tag = ''

        #Fetch command 
        cmd = ba.get_init_cmd(study,subject,test_dir,sub_dir,simg,log_tag)
        cmd = '\n'.join(cmd) 

        #Remove EXIT trap to prevent removing file
        cmd = cmd.replace('trap cleanup EXIT','') 

        #Run command
        p = proc.Popen(cmd,stdout=proc.PIPE,stderr=proc.PIPE,shell=True,executable='/bin/bash') 
        std, err = p.communicate() 

        #Check home directory is only directory 
        num_dirs = len(os.listdir(test_dir))  
        home_dirs = [h for h in os.listdir(test_dir) if 'home' in h] 
        assert num_dirs == 1
        assert len(home_dirs) == 1

        #Next check subfolders of home_dirs, should be length 2 and named work/bids
        home_path = os.path.join(test_dir,home_dirs[0])
        sub_dirs = os.listdir(home_path) 

        #Only two directories should be present
        assert len(sub_dirs) == 2

        #Check if paths exist
        assert os.path.exists(os.path.join(home_path,'bids')) 
        assert os.path.exists(os.path.join(home_path,'work'))

    def test_get_init_cmd_log_outputs_to_correct_path(self): 
        
        os.makedirs(os.path.join(self.tmpdir,'get_init_correct_log')) 

        subject = 'SPN01_CMH_1234_01' 
        study = 'SPINS' 
        test_dir = os.path.join(self.tmpdir,'get_init_correct_log') 
        out_dir = 'test' 
        simg = 'some_image.img' 
        log_file = os.path.join(test_dir,'test_log.txt')
        log_tag = ' &> {}'.format(log_file)

        #Fetch command
        cmd = ba.get_init_cmd(study,subject,test_dir,out_dir,simg,log_tag) 
        cmd = '\n'.join(cmd) 
        cmd = cmd.replace('trap cleanup EXIT','') 

        #Run command
        p = proc.Popen(cmd,stdout=proc.PIPE,stdin=proc.PIPE,shell=True,executable='/bin/bash') 
        std, err = p.communicate() 

        #Check test_log.txt exists
        assert os.path.exists(log_file)

        #Check log contains correct file
        with open(log_file,'r') as l: 
            lines = l.readlines()[0].replace('\n','') 

        home_folder = [h for h in os.listdir(test_dir) if 'home' in h]

        #Test that test_log contains expected information (use abspath to avoid relative path weirdness)... 
        assert os.path.abspath(lines) == os.path.abspath(os.path.join(test_dir,home_folder[0]))

    





