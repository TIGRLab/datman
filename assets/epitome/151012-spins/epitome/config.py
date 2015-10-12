#!/usr/bin/env python
"""
These functions search the environment for software depenencies and configuration.
"""

import os
import subprocess
import multiprocessing as mp

def find_afni():

    """
    Returns the path of the afni bin/ folder, or None if unavailable.
    """
    try:
        dir_afni = subprocess.check_output('which afni', shell=True)
        dir_afni = os.path.dirname(dir_afni)
    except:
        dir_afni = None

    return dir_afni

def find_epitome():
    """
    Returns path of the epitome bin/ folder, or None if unavailable.
    """
    try:
        dir_epitome = subprocess.check_output('which epitome', shell=True)
        dir_epitome = '/'.join(dir_epitome.split('/')[:-2])
    except:
        dir_epitome = None

    return dir_epitome

def find_matlab():
    """
    Returns the path of the matlab folder, or None if unavailable.
    """
    try:
        dir_matlab = subprocess.check_output('which matlab', shell=True)
        dir_matlab = '/'.join(dir_matlab.split('/')[:-2])

    except:
        dir_matlab = None
 
    return dir_matlab

def find_fsl():
    """
    Returns the path of the fsl bin/ folder, or None if unavailable.
    """
    try:
        dir_fsl = subprocess.check_output('which fsl', shell=True)
        dir_fsl = '/'.join(dir_fsl.split('/')[:-1])
    except:
        dir_fsl = None

    return dir_fsl

def find_fix():
    """
    Returns the path of the fix bin/ folder, or None if unavailable.
    """
    try:
        dir_fix = subprocess.check_output('which fix', shell=True)
        dir_fix = '/'.join(dir_fix.split('/')[:-1])
    except:
        dir_fix = None

    return dir_fix

def find_freesurfer():
    """
    Returns the path of the freesurfer bin/ folder, or None if unavailable.
    """
    try:
        dir_freesurfer = subprocess.check_output('which recon-all', shell=True)
        dir_freesurfer = '/'.join(dir_freesurfer.split('/')[:-1])
    except:
        dir_freesurfer = None
 
    return dir_freesurfer

def find_data():
    """
    Returns the epitome data path defined in the environment.
    """
    try:
        dir_data = os.getenv('EPITOME_DATA')
    except:
        dir_data = None

    return dir_data

def find_freesurfer_data():
    """
    Returns the freesurfer data path defined in the environment.
    """
    try:
        dir_freesurfer_data = os.getenv('SUBJECTS_DIR')
    except:
        dir_freesurfer_data = None

    return dir_freesurfer_data
