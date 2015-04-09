#!/usr/bin/env python
"""
A collection of utilities for the EPItome-xl pipeline. Mostly for getting 
subject numbers/names, checking paths, gathering inforamtion, etc.
"""

import os, sys, copy
import epitome as epi
import epitome.commands as cmd

def selector_float():
    """
    Prompts the user to input a floating-point number.
    """
    option = raw_input('#: ') # have the user enter a number

    # ensure response is non-negative
    if option == '':
        option = -1
    
    # check input
    try:
        if float(option) >= float(0):
            response = float(option)
            return response
        else:
            print('*** Input must be positive! ***')
            raise ValueError    
    except:
        print('*** Input must be a float! ***')
        raise ValueError    

def selector_int():
    """
    Prompts the user to input a integer number.
    """
    option = raw_input('#: ') # have the user enter a number

    # ensure response is non-negative
    if option == '':
        option = -1
    
    # check input
    try:
        if int(option) >= 0:
            response = int(option)
            return response
        else:
            print('*** Input must be positive! ***')
            raise ValueError
    except:
        print('*** Input must be an integer! ***')
        raise ValueError

def selector_list(item_list):
    """
    Prompts the user to select from an item in the supplied list.
    """
    if type(item_list) != list:
        raise TypeError('Input must be a list!')

    # sort the input list
    item_list.sort()

    # print the options, and their numbers
    for i, item in enumerate(item_list):
        print('    ' + str(i+1) +': ' + str(item))

    # retrieve the option number
    option = raw_input('option #: ')

    # check input
    if option == '':
        option = 0
    try:
        response = item_list[int(option)-1]
    except:
        print('*** Option # invalid! ***')
        raise ValueError
    if int(option) == 0:
        print('*** Option # invalid! ***')
        raise ValueError
    return response

def selector_dict(item_dict):
    """
    Prompts the user to select an item in the supplied dictionary.
    """

    if type(item_dict) != dict:
        raise TypeError('Input must be a dict!')

    # init list where we store / find the responses
    item_list = []
    
    # generate a sorted list of dict keys
    for item in item_dict:
        item_list.append(item)
    item_list.sort()

    # loop through sorted list
    for i, item in enumerate(item_list):
        print(str(i+1) + ': ' + item + ' ' + item_dict[item])
    
    # retrieve the option number
    option = raw_input('option #: ')

    # check input
    if option == '':
        option = 0
    try:
        response = item_list[int(option)-1]
    except:
        print('*** Option # invalid! ***')
        raise ValueError
    if int(option) == 0:
        print('*** Option # invalid! ***')
        raise ValueError
    return response

def get_subj(dir):
    """
    Gets all folder names (i.e., subjects) in a directory (of subjects).
    """
    subjects = []
    for subj in os.walk(dir).next()[1]:
        if os.path.isdir(os.path.join(dir, subj)) == True:
            subjects.append(subj)
    subjects.sort()
    return subjects

def has_permissions(directory):
    if os.access(directory, 7) == True:
        flag = True
    else:
        print('\nYou do not have write access to directory ' + str(directory))
        print('Please contact a system administrator and try again.\n')
        flag = False

    return flag

def check_os():
    """
    Ensures the user isn't Bill Gates.
    """
    import platform

    operating_system = platform.system()
    if operating_system == 'Windows':
        print("""
              Windows detected. epitome requires Unix-like operating systems!
              """)
        sys.exit()

def init_shell(path, expt):
    """
    Gets all of the subjects and prints them as a BASH friendly variable.
    """
    subjects = epi.utilities.get_subj(os.path.join(path, expt))
    output = '"'

    for subj in subjects:
        output+=str(subj)
        output+=' '
    output+='"'

    os.system('echo ' + str(output))

if __name__ == "__main__":
    init_shell(sys.argv[1], sys.argv[2])
