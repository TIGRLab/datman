#!/usr/bin/env python
"""
Produces a .csv of scan dates and emails them to the specified person.

Usage:
    scan-date-report.py <datadir> <filename> [options]

Arguments:
    <datadir>         Parent folder holding folders of dicoms
    <filename>        Filename to save report as.


Options:
    --email    EMAIL  Email to send report to (not functional yet).

DETAILS

    This program will collect the dates of each scan from the folder defined,
    where each sub-folder is for a subject and each contains at least one
    DICOM file. It outputs a simple report .csv in the format:

    SUBJECT,SCANDATE
    subj01,YYYY-MM-DD
    subj02,YYYY-MM-DD
    subj03,YYYY-MM-DD
"""

import os, sys
import csv
import glob
import datetime
import datman as dm
from datman.docopt import docopt
import dicom as dcm

def get_scan_date(subj):
    """
    Looks through the contents of a folder for a single dicom. Returns the 
    scan date of the first dicom found as a python datetime object.
    """

    files = os.listdir(subj)

    for f in files:
        try:
            d = dcm.read_file(os.path.join(subj, f))
            date = d.SeriesDate
            date = datetime.date(int(date[0:4]), int(date[4:6]), int(date[6:8]))
            return date
        except:
            pass

    return None

def main():

    arguments = docopt(__doc__)
    datadir   = arguments['<datadir>']
    filename  = arguments['<filename>']
    email     = arguments['--email']

    # get a sorted list of all the subject folders
    subjects = os.listdir(datadir)
    subjects.sort()

    # open csvfile for writing
    with open(filename , 'wb') as csvfile:
        writer = csv.writer(csvfile, delimiter=',')
        writer.writerow(['SUBJECT', 'SCANDATE'])

        for subj in subjects:
            date = get_scan_date(os.path.join(datadir, subj))
            
            # skip scans with no dates
            if date == None:
                print('ERROR: failed for {}'.format(os.path.join(datadir, subj)))
                pass

            # remove project name
            subj = '_'.join(subj.split('_')[1:])
            date = date.strftime('%Y-%m-%d')
            writer.writerow([subj, date])

if __name__ == '__main__':
    main()
