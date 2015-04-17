#!/usr/bin/env python
"""
Renames (links) exam zip archives by consulting a lookup table.

This program looks up the proper name in a table that lists the original exam
archive name, and the target name. 

Usage:
    link.py [options] <targetdir> <archive>...

Arguments: 
    <targetdir>              Path to rename (i.e. link) the archive into
    <archive>                Path to MR Unit archive zip
                             
Options:                     
    --lookup FILE            Path to scan id lookup table [default: metadata/scans.csv]
    --scanid_field STR       Dicom field to match target_name with 
                             [default: PatientName]
    -v,--verbose             Verbose logging
    -n,--dry-run             Dry run


DETAILS

The lookup table should have atleast two columns: original_name, and
target_name.  For example: 

    source_name      target_name
    2014_0126_FB001  ASDD_CMH_FB001_01_01

Additional columns can be specified to ensure that the DICOM headers of the file
match. These column names should start with dicom_. For example, 

    source_name      target_name            dicom_StudyID
    2014_0126_FB001  ASDD_CMH_FB001_01_01   512

In the example above, this script would check that the StudyID field of an
arbitrary dicom file in the archive contains the value "512". If not, an error
is thrown. 
"""

from docopt import docopt
import pandas as pd
import datman as dm
import datman.utils
import datman.scanid
import os.path
import sys

VERBOSE = False
DRYRUN  = False
DEBUG   = False
 
def log(message): 
    print message
    sys.stdout.flush()

def error(message): 
    log("ERROR: " + message)

def verbose(message): 
    if not(VERBOSE or DEBUG): return
    log(message)

def debug(message): 
    if not DEBUG: return
    log("DEBUG: " + message)

def main():
    global VERBOSE 
    global DRYRUN
    arguments    = docopt(__doc__)
    archives     = arguments['<archive>']
    targetdir    = arguments['<targetdir>']
    lookup_table = arguments['--lookup']
    scanid_field = arguments['--scanid_field']
    VERBOSE      = arguments['--verbose']
    DRYRUN       = arguments['--dry-run']

    lookup = pd.read_table(lookup_table, sep='\s+', dtype=str)
    targetdir = os.path.normpath(targetdir)

    for archivepath in archives: 
        basename    = os.path.basename(os.path.normpath(archivepath))
        source_name = basename[:-len('.zip')]

        lookupinfo  = lookup[ lookup['source_name'] == source_name ]

        if len(lookupinfo) == 0:
            error("{} not found in source_name column of lookup table. Skipping.".format(
                archivepath))
            continue

        target_name = lookupinfo['target_name'].tolist()[0]

        if not validate(archivepath, lookupinfo, scanid_field, source_name, target_name):
            continue

        target = os.path.join(targetdir,target_name)+'.zip'
        if os.path.exists(target): 
            verbose("{} already exists for archive {}. Skipping.".format(
                target,archivepath))
            continue

        relpath = os.path.relpath(archivepath,os.path.dirname(target))
        log("linking {} to {}".format(relpath, target))
        if not DRYRUN:
            os.symlink(relpath, target)

def validate(archivepath, lookupinfo, scanid_field, source_name, target_name):
    """
    Validates an exam archive against the lookup table

    Checks that: 
    1. The target_name == dicom header field <dcm_field>
        OR
    2. All dicom_* dicom header fields match the lookup table
    """
    header = dm.utils.get_archive_headers(archivepath, stop_after_first=True).values()[0]

    if scanid_field not in header:
        error("{} field is not in {} dicom headers".format(
            scanid_field, archivepath))
        return False

    if header.get(scanid_field) == target_name:
        verbose("{}: target_name {} matches {} dicom field".format(
            archivepath, target_name, scanid_field))
        return True
    
    columns    = lookupinfo.columns.values.tolist()
    dicom_cols = [c for c in columns if c.startswith('dicom_')]

    for c in dicom_cols:
        f = c.split("_")[1]

        if f not in header:
            error("{}: {} field is not in {} dicom headers".format(
                archivepath, scanid_field, archivepath))
            return False

        actual   = str(header.get(f))
        expected = str(lookupinfo[c].tolist()[0])

        if actual != expected :
            error("{}: dicom field '{}' = '{}', expected '{}'".format(
                archivepath, f, actual, expected))
            return False

    return True

if __name__ == '__main__': 
    main()

# vim: ts=4 sw=4:
