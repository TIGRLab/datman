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

    ### Scan ID in a lookup table (--lookup)

    The lookup table should have atleast two columns: source_name, and
    target_name.  For example: 

        source_name      target_name
        2014_0126_FB001  ASDD_CMH_FB001_01_01

    The source_name column is matched against the archive filename (so the
    entry above applies to 2014_0126_FB001.zip). The target_name column
    specifies the proper name for the exam. 

    If the archive is not found in the lookup table, the dicom header is
    consulted: 

    ### Scan ID in the dicom header (--scanid_field)

    Some scans may have the scan ID embedded in a dicom header field.
    
    The --scanid_field specifies a dicom header field to check for a
    well-formatted exam name. 


ADDITIONAL MATCH CONDITIONS
    Additional columns in the lookup table can be specified to ensure that the
    DICOM headers of the file match what is expected. These column names should
    start with dicom_. For example, 

        source_name      target_name            dicom_StudyID
        2014_0126_FB001  ASDD_CMH_FB001_01_01   512

    In the example above, this script would check that the StudyID field of an
    arbitrary dicom file in the archive contains the value "512". If not, an
    error is thrown. 

IGNORING EXAM ARCHIVES
    Exam archives can be ignored by placing an entry into the lookup table with
    the target_name of '<ignore>', for example: 
        source_name      target_name            dicom_StudyID
        2014_0126_FB001  <ignore>
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
        
        # get some DICOM headers from the archive
        try:
            header = dm.utils.get_archive_headers(
                                archivepath, stop_after_first=True).values()[0]
        except:
            error("{}: Contains no DICOMs. Skipping.".format(archivepath))
            continue

        # search the lookup and the headers for a valid scan ID 
        scanid = get_scanid_from_lookup_table(archivepath, header, lookup)
        debug("Found {} as scanid from lookup table {}".format(scanid, lookup_table))
        if scanid == '<ignore>': 
            verbose("Ignoring {}".format(archivepath))
            continue
        if scanid is None:
            scanid = get_scanid_from_header(archivepath, header, scanid_field) 
            debug("Found {} as scanid from header.".format(scanid))
        if scanid is None: 
            error("{}: Cannot find scan id. Skipping".format(archivepath))
            continue

        # do the linking 
        target = os.path.join(targetdir,scanid) + datman.utils.get_extension(archivepath)
        if os.path.exists(target): 
            verbose("{} already exists for archive {}. Skipping.".format(
                target,archivepath))
            continue

        relpath = os.path.relpath(archivepath,os.path.dirname(target))
        log("linking {} to {}".format(relpath, target))
        if not DRYRUN:
            os.symlink(relpath, target)

def get_scanid_from_lookup_table(archivepath, header, lookup):
    """
    Gets the scanid from the lookup table (pandas dataframe)

    Returns None if a match can't be found, or additional dicom fields don't
    match. 
    """
    basename    = os.path.basename(os.path.normpath(archivepath))
    source_name = basename[:-len(datman.utils.get_extension(basename))]
    lookupinfo  = lookup[ lookup['source_name'] == source_name ]

    if len(lookupinfo) == 0:
        debug("{} not found in source_name column.".format(source_name))
        return None
    else: 
        scanid = lookupinfo['target_name'].tolist()[0]
        debug("Found scan ID '{}' in lookup table".format(scanid))
        if not validate(archivepath, header, lookupinfo):
            return None
        else:
            return scanid

def get_scanid_from_header(archivepath, header, scanid_field):
    """
    Gets the scanid from the dicom header object. 

    Returns None if the header field isn't present or the value isn't a proper
    scan ID.
    """

    if scanid_field not in header:
        error("{} field is not in {} dicom headers".format(
            scanid_field, archivepath))
        return None

    scanid = str(header.get(scanid_field))

    if dm.scanid.is_scanid(scanid):
        debug("{}: Using scan ID from dicom field {} = {}.".format(
                archivepath, scanid_field, scanid))
        return scanid 

    else: 
        error("{}: {} (header {}) not valid scan ID".format(
            archivepath, scanid, scanid_field))
        return None


def validate(archivepath, header, lookupinfo):
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
