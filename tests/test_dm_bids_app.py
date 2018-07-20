#!/usr/bin/env python

import os
import unittest
import importlib
import logging

ba = importlib.import_module("bin.dm_bids_app.py") 
logging.disable(logging.CRITICAL) 

FIXTURE = 'tests/fixture_dm_bids_app'
json_config = os.path.join(FIXTURE,'mock_json.json')
bad_json = os.path.join(FIXTURE,'bad_json.json')
output_path = os.path.join(FIXTURE,'out')

def test_get_json_args_returns_formatted_dict(): 

    expected_out = {'img': 'potato', 'app': 'FMRIPREP','--test_int':10,'--test_bool':''}
    assert expected_out == ba.get_json_args(json_config)

def test_validate_json_on_good_json():

    jargs = {'img': 'potato', 'app': 'FMRIPREP','--test_int':10,'--test_bool':''}
    assert ba.validate_json_args(jargs) == True

def test_filter_subjects_filters_preexisting_directories(): 

    subjects = ['POTATO1','POTATO2','POTATO3','POTATO4','POTATO5']
    expected_out = ['POTATO1,POTATO5']
    assert set(ba.filter_processed(subjects,output_path)) == set(expected_out)

def test_gen_log_redirect_provides_correct_tag(): 

    log_dir = 'log_dir'
    subject = 'subject'
    app_name = 'app'

    expected_out = ' &>> log_dir/subject/dm_bids_app_app_log.txt' 

    assert ba.gen_log_redirect(log_dir,subject,app_name) == expected_out

def test_get_exclusion_cmd_formats_correctly(): 

    tags = ['HI','EXCLUDE','ME']
    
    expected_out = ['find $BIDS -name *HI* -delete', 'find $BIDS -name *EXCLUDE* -delete', 
                    'find $BIDS -name *ME* -delete']

    assert set(ba.get_exclusion_cmd(tags)) == set(expected_out) 
    


@raise(KeyError) 
def test_validate_json_on_bad_json(): 

    jargs = {'i_am_bad' : True} 
    ba.validate_json_args(jargs)  


def test_get_requested_threads_returns_int_given_string(): 

    thread_dict = {'FMRIPREP' : '', 
                   'MRIQC' : ''}
    jargs = {'--nthreads' : '5'} 
    assert ba.get_requested_threads(jargs,thread_dict) == 5

def test_get_requested_threads_returns_int_given_int(): 

    thread_dict = {'FMRIPREP' : '', 
                    'MRIQC' : ''}
    jargs = {'--nthreads' : 5} 
    assert ba.get_requested_threads(jargs,thread_dict) == 5

@raises(TypeError) 
def test_get_requested_threads_fails_on_float():

    thread_dict = {'FMRIPREP' : '',
                    'MRIQC' : ''}
    jargs = {'--nthreads' : 5.4}
    ba.get_requested_threads(jargs,thread_dict) 

@raises(TypeError) 
def test_get_requested_threads_fails_on_str_float(): 

    thread_dict = {'FMRIPREP' : '',
                    'MRIQC' : ''} 
    jargs = {'--nthreads' : '10.23'} 
    ba.get_requested_threads(jargs,thread_dict) 
    
