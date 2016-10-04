#!/usr/bin/env python
"""
Compares number of recieved files for a subject with the expected counts defined
in the exportinfo.csv file.

Usage: 
    dm-check-protocols.py <datadir> <exportinfo> [options]

Arguments: 
    <datadir>          Folder containing subject folders (nifti, datman naming convention)
    <exportinfo>       exportinfo.csv file containing expected counts

Options:
    --verbose          Be chatty

DETAILS

    This program uses the exportinfo file to determine if each subject's 
    submitted data is complete (i.e., contains all of the expected scans).

    In the case that the number of scans found across all of the defined
    protocols for ANY TAG, the program reports the number of found images
    of that tag to the user.
"""

import os
import pandas as pd
import datman as dm
from docopt import docopt

def check_protocol_length(data, expected):
    if len(data) != expected:
        raise ValueError

def find_niftis_with_tag(datadir, tag):
    files = dm.utils.get_files_with_tag(datadir, tag)
    files = filter(lambda x: '.nii.gz' in x, files)

    return files

def main():

    arguments       = docopt(__doc__)
    datadir         = arguments['<datadir>']
    exportinfo      = arguments['<exportinfo>']
    VERBOSE         = arguments['--verbose']

    subjects = dm.utils.get_subjects(datadir)
    subjects = filter(lambda x: '_PHA_' not in x, subjects)

    # import data, get dimensions
    data = pd.read_csv(exportinfo, skipinitialspace=True, delimiter=' ')
    n_protocols = len(data['count'][0].split(','))
    tags = list(data['tag'])

    try:
        tags.remove('?') # removed ignored series from the list if they are defined
    except:
        pass

    tags_expected = {}
    tags_found = {}

    for i, tag in enumerate(tags):
        try:
            check_protocol_length(data['count'][i].split(','), n_protocols)
            tags_expected[tag] = data['count'][i].split(',')
        except:
            print('ERROR: {} has the wrong number of protocols defined for {}.'.format(input_file, tags[tag]))
            sys.exit()

    # loop through subjects, reporting 
    for sub in subjects:
        subjdir = os.path.join(datadir, sub)

        for tag in tags_expected:
            files = find_niftis_with_tag(subjdir, tag)
            tags_found[tag] = len(files)

        # compare the protocols
        successful = None
        for protocol in range(n_protocols):
            tags_warning = {}

            for tag in tags_expected:
                if tags_found[tag] < int(tags_expected[tag][protocol]):
                    tags_warning[tag] = tags_found[tag]

            if len(tags_warning) == 0:
                successful = 1
                pass
            else:
                continue

        if not successful:
            msg = 'ERROR: Protocol mismatch for {}: '.format(sub)
            for tag in tags_warning:
                msg = '{} {} {}, '.format(msg, tag, tags_warning[tag])
            print(msg)

if __name__ == '__main__':
    main()
