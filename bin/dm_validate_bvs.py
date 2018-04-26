#!/usr/bin/env python

'''
QC Check to validate bval/bvecs generated from dicom to NIfTI conversion.
Outputs a flag .csv file that indicates which .bv* files should be verified 

Usage: 
    dm_validate_bvs.py [options] <study>   

Arguments: 
    <study>                         DATMAN structured project name 
    
Options: 
    -v,--verbose                    Verbose logging
    -d,--debug                      Debug log 
    -a,--bval_temp BVAL_TMP         Template file for bvals 
    -e,--bvec_temp BVEC_TMP         Template file for bvecs 
'''

import os 
import pdb  
import logging 
import sys

import datman.config
import datman.utils
import datman.scan
import datman.scanid

import pandas as pd 

from docopt import docopt 


logging.basicConfig(level=logging.WARN,
        format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

df = pd.DataFrame() #this is just to store data to eventually write into

def load_config(study): 

    logger.info('Loading configuration of {}'.format(study))

    try: 
        config = datman.config.config(study=study) 
    except: 
        logging.error('Cannot locate configuration file of {}'.format(study)) 
        sys.exit(1) 

    #Check if required paths exist 
    req_paths = ['nii'] 

    for path in req_paths: 
        try: 
            config.get_path(path) 
        except KeyError: 
            logging.error('Cannot locate {} in {}/data/'.format(path,study)) 

    return config 

def bv_load(config,subject,series): 

    full_path = os.path.join(config.get_path('nii'),subject)
    bval,bvec = None, None 

    #Attempt to load bval/bvec files try: 
    try:
        with open(os.path.join(full_path,series + '.bval'),'r') as val: 
            bval = val.read() 
            bval = list(map(float,bval.split(None)))

    except FileNotFoundError: 
        logger.warning('{} bval not found!'.format(series))

    try: 
        
        with open(os.path.join(full_path,series + '.bvec'),'r') as vec: 
            bvec = vec.read() 
            bvec = list(map(float,bvec.split(None))) 

    except FileNotFoundError: 
        logger.warning('{} bvec not found!'.format(series)) 
    
    return bval, bvec

def match_template(bv,template): 
    '''
    Perform template matching between bv and provided template 

    Method: 
    1. Identifies initial displacement 
    2. Checks # mismatches 
    '''

    logger.debug('Matching to template {}'.format(template)) 

def comp_to_template(bv,t_bv, epsilon = 0.001): 
    '''
    Extracts bval differences between given expected template and 
    recorded bvals. 
    Returns record of: 
    1. Displacement of starting bvals 
    2. Return number of mismatches 
    3. Return length mismatch 
    '''

    logger.debug('Matching to template \n {} \n with \n {} '.format(t_bv,bv)) 

    #Load in the templates 
    with open(t_bv,'r') as f:
        template = f.read()

        #Match formats of bval
        template = list(map(float,template.split(None))) 
        
        #First check template displacement 
        temp_zero  = next((i for i,x in enumerate(template) 
                if abs(x) > epsilon),None) 
        bv_zero = next((i for i,x in enumerate(bv)
                if abs(x) > epsilon),None) 
        displacement = abs(temp_zero-bv_zero) 
        
        #Perform a length check then check displacement 
        if temp_zero > bv_zero: 
            del(template[0]) 
        else: 
            del(bv[0]) 

        diff_flag = [True for t,b in zip(template,bv) if (t-b) > epsilon] 
        logger.info('Number of mismatches found: {}'.format(len(diff_flag)))

        return displacement, len(diff_flag) > 0, len(template) == len(bv)  

def get_validation_entry(config,subject,series,t_bval,t_bvec): 
    '''
    Performs validation of single DTI series. 
    Writes to global pandas.DataFrame the following information: 
    Ideally requires a template to match to
    1. Series Name 
    2. bval file (None if missing) 
    3. bval displacement 
    4. bval value mismatch
    5. bval length mismatch 
    6. bvec file (None if missing) 
    7. bvec displacement 
    8. bvec value mismatch 
    9. bvec length mismatch
    '''
    
    bval,bvec = None, None 
    disp_val, disp_vec = None, None 
    val_diff_flag, vec_diff_flag = None, None 
    len_mis_val, len_mis_vec = None, None 

    #First try to locate and open bval/bvec files  
    bval, bvec = bv_load(config,subject,series) 
    
    #If template is available run comparison
    if t_bval and bval: 
        disp_val, val_diff_flag, len_mis_val = comp_to_template(bval,t_bval)
    if t_bvec and bvec: 
        disp_vec, vec_diff_flag, len_mis_vec = comp_to_template(bval,t_bvec) 

    #Return validation info 
    return {'SeriesName' :      series, 

            'bval':             bval, 
            'bval_disp' :       disp_val, 
            'bval_mis' :        val_diff_flag, 
            'bval_len_mis':     len_mis_val, 

            'bvec':             bvec, 
            'bvec_disp':        disp_vec, 
            'bvec_mis':         vec_diff_flag, 
            'bvec_len_mis':     len_mis_vec
            } 

def intrasite_bv_consist(valid_dict_list): 
    '''
    Performs an intrasite consistency check
    Finds 'categories' if exist, return outliers if major category exists 
    If template matching did not raise mismatches then we skip since that 
    implies that intrasite consistency would be achieved 
    '''

    pdb.set_trace()
    logger.info('Performing intrasite consistency check for {}'.format( 
        valid_dict_list[0]['Site'])) 

    #Check for template mismatch 
    

def validate_site_bvs(config,site,t_bval,t_bvec): 
    logging.info('Processing site {}'.format(site))

    '''
    For each site we need to pull a list of non-phantom subjects 
    '''
    #Get nii path
    nii_path = config.get_path('nii') 

    #Extract site list: currently just processing human subjects
    subject_list  = [scan for scan in os.listdir(nii_path)
            if (site in scan) and ('PHA' not in scan)]  

    logging.debug('Processing subjects: {}'.format(subject_list)) 

    valid_dict_list = [] 
    for subject in subject_list:  

        sub_scan = datman.scan.Scan(subject,config) 
        
        #Use hacky method because DTi tagging is broken.. 
        all_dti_base = set([dti.split('.')[0] 
            for dti in os.listdir(os.path.join(nii_path,subject)) 
                if 'DTI' in dti]) 

        #For each series, grab the associated bv's and run comparator 
        for series in all_dti_base: 

            valid_info = get_validation_entry(config,subject,
                            series,t_bval,t_bvec)

            valid_info.update({'Site':site})
            valid_dict_list.append(valid_info) 
    
    #Now we perform within site consistency check
    intrasite_bv_consist(valid_dict_list)  

    return valid_dict_list 


def main(): 

    #Parse arguments
    arguments = docopt(__doc__) 

    study =         arguments['<study>'] 

    t_bval =        arguments['--bval_temp']
    t_bvec =        arguments['--bvec_temp']

    verbose =       arguments['--verbose'] 
    debug=          arguments['--debug'] 


    #When templates not provided
    if not t_bval: t_bval = None 
    if not t_bvec: t_bvec = None 

    #Configure logging
    if verbose: 
        logger.setLevel(logging.INFO) 
    elif debug:  
        logger.setLevel(logging.DEBUG)
    else: 
        logger.setLevel(logging.WARNING)

    #Load configuration file for study 
    config = load_config(study) 

    #Get nii path, list files and obtain study sites
    sites = config.get_sites() 

    bv_record = []

    #So we check within sites 
    for site in sites: 

        bv_record.append(validate_site_bvs(config,site,t_bval,t_bvec))  




if __name__ == '__main__': 
    main() 
