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
    --lookup FILE            Path to scan id lookup table 
                                [default: metadata/scans.csv]
    --scanid_field STR       Dicom field to match target_name with 
                             [default: PatientName]
    -v,--verbose             Verbose logging
    --debug                  Debug logging
    -n,--dry-run             Dry run


DETAILS

    This program is used to rename an exam archive with their properly
    formatted scan names (see datman.scanid). Two approaches are used to find
    this name: 

    ### Scan ID in the dicom header (--scanid_field)

    Some scans may have the scan ID embedded in a dicom header field.
    
    The --scanid_field specifies a dicom header field to check for a
    well-formatted exam name. If it isn't well formatted, then we the lookup
    table is consulted. 


    ### Scan ID in a lookup table (--lookup)

    The lookup table should have atleast two columns: source_name, and
    target_name.  For example: 

        source_name      target_name
        2014_0126_FB001  ASDD_CMH_FB001_01_01

    The source_name column is matched against the archive filename (so the
    entry above applies to 2014_0126_FB001.zip). The target_name column
    specifies the proper name for the exam. 


ADDITIONAL MATCH CONDITIONS

    Additional columns in the lookup table can be specified to ensure that the
    DICOM headers of the file match what is expected. These column names should
    start with dicom_. For example, 

        source_name      target_name            dicom_StudyID
        2014_0126_FB001  ASDD_CMH_FB001_01_01   512

    In the example above, this script would check that the StudyID field of an
    arbitrary dicom file in the archive contains the value "512". If not, an
    error is thrown. 
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
    global DEBUG
    arguments    = docopt(__doc__)
    archives     = arguments['<archive>']
    targetdir    = arguments['<targetdir>']
    lookup_table = arguments['--lookup']
    scanid_field = arguments['--scanid_field']
    VERBOSE      = arguments['--verbose']
    DEBUG        = arguments['--debug']
    DRYRUN       = arguments['--dry-run']

    lookup = pd.read_table(lookup_table, sep='\s+', dtype=str)
    targetdir = os.path.normpath(targetdir)

    for archivepath in archives: 
        basename    = os.path.basename(os.path.normpath(archivepath))

        # get some DICOM headers from the archive
        header = dm.utils.get_archive_headers(archivepath, 
                stop_after_first=True).values()[0]

        if scanid_field not in header:
            error("{} field is not in {} dicom headers".format(
                scanid_field, archivepath))
            continue

        # check header field for scan id
        scanid = str(header.get(scanid_field))

        if dm.scanid.is_scanid(scanid):
            debug("{}: Using scan ID from dicom field {} = {}.".format(
                    archivepath, scanid_field, scanid))
        else:
            # try the lookup table
            debug("Dicom field {} = {} is not a valid scan id.".format(
                    scanid_field, scanid))
            debug("Trying lookup table...")

            source_name = basename[:-len('.zip')]
            lookupinfo  = lookup[ lookup['source_name'] == source_name ]

            if len(lookupinfo) == 0:
                error("{} not found in source_name column. Skipping.".format(
                    source_name))
                continue

            scanid = lookupinfo['target_name'].tolist()[0]
            debug("Found scan ID '{}' in lookup table".format(scanid))

            if not validate(header, lookupinfo):
                continue

        target = os.path.join(targetdir,scanid)+'.zip'
        if os.path.exists(target): 
            verbose("{} already exists for archive {}. Skipping.".format(
                target,archivepath))
            continue

        relpath = os.path.relpath(archivepath,os.path.dirname(target))
        log("linking {} to {}".format(relpath, target))
        if not DRYRUN:
            os.symlink(relpath, target)

def validate(header, lookupinfo):
    """
    Validates an exam archive against the lookup table

    Checks that all dicom_* dicom header fields match the lookup table
    """
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
