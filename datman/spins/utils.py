#!/usr/bin/env python
"""
A collection of utilities for munging imaging data,. Built for the 
spins project.
"""
import os
import numpy as np

def subject_type(subject):
    """
    Uses subject naming to determine what kind of files we are looking at. If
    we find a strangely-named subject, we return None.
    """
    try:
        subject = subject.split('_')

        if subject[2] == 'PHA':
            return 'phantom'
        
        elif subject[2] != 'PHA' and subject[2][0] == 'P':
            return 'humanphantom'
        
        elif str.isdigit(subject[2]) == True and len(subject[2]) == 4:
            return 'subject'
        
        else:
            return None

    except:
        return None

def get_subjects(data_path):
    """
    Finds all of the subject folders in the nifti directory. Assumes this
    is represenative (it is basically -- hard do to the analysis without them).
    """
    idx = np.array(map(lambda x: os.path.isdir(
                                 os.path.join(data_path, 'nifti', x)),
                                 os.listdir(data_path + '/nifti')))
    subjects = np.array(os.listdir(data_path + '/nifti'))[idx]
    subjects.sort()

    return subjects

def make_epitome_folders(path, n_runs):
    """
    Makes an epitome-compatible folder structure with functional data FUNC of n
    runs, and a single T1.
    """
    # make the anatomical run folder
    os.system('mkdir -p ' + path + '/TEMP/SUBJ/T1/SESS01/RUN01')

    # make the functional run folders
    for run in np.arange(n_runs)+1:
        num = "{:0>2}".format(str(run))
        os.system('mkdir -p ' + path + '/TEMP/SUBJ/FUNC/SESS01/RUN' + num)
