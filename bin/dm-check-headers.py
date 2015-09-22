#!/usr/bin/env python
"""
Diffs the relevant fields of the header to determine if anything has changed in
the protocol.

Usage: 
    dm-check-header.py [options] <standards> <exam>...

Arguments: 
    <standards/>            Folder with subfolders named by tag. Each subfolder
                            has a sample gold standard dicom file for that tag.

    <exam/>                 Folder with one dicom file sample from each series
                            to check

Options: 
    --quiet                 Don't print warnings
    --ignore-headers LIST   Comma delimited list of headers to ignore
    --ignore-series FILE    File containing a list of scans to ignore
                            The file should be a space separated table with two
                            columns, "series" and "reason". The series column
                            should contain full series name to be ignored (e.g.
                            ANDT_CMH_308_01_01_DTI60-1000_04_Ax-DTI60plus5-20iso)
                            [default: metadata/mismatchedheaders.txt]

DETAILS
    
    Output looks like: 

    /path/to/exam/dicom.dcm: headers not in standard: list,... 
    /path/to/exam/dicom.dcm: headers not in series: list,... 
    /path/to/exam/dicom.dcm: header {}: expected = {}, actual = {} [tolerance = {}]

"""
import sys
from docopt import docopt
import dicom as dcm
import datman as dm
import numpy as np
import datman.utils
import os.path
import pandas as pd

ignored_headers = set([
    'AcquisitionDate',
    'AcquisitionTime',
    'AcquisitionMatrix',
    'ContentDate',
    'ContentTime',
    'DeidentificationMethodCodeSequence',
    'FrameOfReferenceUID',
    'HeartRate',
    'ImageOrientationPatient',
    'ImagePositionPatient',
    'InStackPositionNumber',
    'InversionTime',
    'ImagesInAcquisition',
    'InstanceNumber',
    'LargestImagePixelValue',
    'OperatorsName',
    'PatientID',
    'PixelData',
    'ProtocolName',
    'RefdImageSequence',
    'RefdPerformedProcedureStepSequence',
    'ReferencedImageSequence',
    'ReferencedPerformedProcedureStepSequence',
    'PatientAge',
    'PatientBirthDate',
    'PatientName',
    'PatientSex',
    'PatientWeight',
    'PercentPhaseFieldOfView,',
    'PerformedProcedureStepID',
    'PerformedProcedureStepStartDate',
    'PerformedProcedureStepStartTime',
    'SAR',
    'ScanOptions',
    'ScanningSequence',
    'SequenceVariant',
    'SOPInstanceUID',
    'SoftwareVersions',
    'SeriesNumber',
    'SeriesDate',
    'SeriesDescription',
    'SeriesInstanceUID',
    'SeriesTime',
    'SliceLocation',
    'SmallestImagePixelValue',
    'StudyDate',
    'StudyID',
    'StudyInstanceUID',
    'StudyTime',
    'TemporalPositionIdentifier',
    'TriggerTime',
    'WindowCenter',
    'WindowWidth',
])

integer_tolerances = {
        # field           : interger difference
        'ImagingFrequency': 1, 
        'EchoTime': 5,
}

decimal_tolerances = {
        'RepetitionTime': 1
}


QUIET = False

def compare_headers(stdpath, stdhdr, cmppath, cmphdr, ignore=ignored_headers):
    """
    Accepts two pydicom objects and prints out header value differences. 
    
    Headers in ignore set are ignored.
    """

    # get the unignored headers
    stdhdr_ = set(stdhdr.dir()).difference(ignore)
    cmphdr_ = set(cmphdr.dir()).difference(ignore)

    only_stdhdr = stdhdr_.difference(cmphdr_)
    only_cmphdr = cmphdr_.difference(stdhdr_)
    both_hdr    = stdhdr_.intersection(cmphdr_)
  
    if only_stdhdr:
        print("{cmppath}: headers in series, not in standard: {list}".format(
            cmppath=cmppath, list=", ".join(only_stdhdr)))

    if only_cmphdr:
        print("{cmppath}: headers in standard, not in series: {list}".format(
            cmppath=cmppath, list=", ".join(only_cmphdr)))
    
    for header in both_hdr:
        stdval = stdhdr.get(header)
        cmpval = cmphdr.get(header)

        # compare within tolerance
        if header in integer_tolerances:
            n = integer_tolerances[header]

            stdval_rounded = np.round(float(stdval))
            cmpval_rounded = np.round(float(cmpval))
            difference = np.abs(stdval_rounded - cmpval_rounded)

            if difference > n:
                msg = "{}: header {}, expected = {}, actual = {} [tolerance = {}]"
                print(msg.format(cmppath, header, stdval_rounded, cmpval_rounded, n))

        elif header in decimal_tolerances:
            n = decimal_tolerances[header]

            stdval_rounded = round(float(stdval), n)
            cmpval_rounded = round(float(cmpval), n)

            if stdval_rounded != cmpval_rounded:
                msg = "{}: header {}, expected = {}, actual = {} [tolerance = {}]"
                print(msg.format(cmppath, header, stdval_rounded, cmpval_rounded, n))

        elif str(cmpval) != str(stdval):
            print("{}: header {}, expected = {}, actual = {}".format(
                    cmppath, header, stdval, cmpval))


def compare_exam_headers(std_headers, examdir, ignorelist, ignored_series):
    """
    Compares headers for each series in an exam against gold standards

    <std_headers> is a map from description -> (path, headers) of all of the
    standard headers to compare against. 

    <ignorelist> is a list of headers, in addition to the defaults, to ignore. 
    
    <ignored_series> is a list of series to ignore checking. 
    """
    exam_headers = dm.utils.get_all_headers_in_folder(examdir)

    ignore = ignored_headers.union(ignorelist)

    for path, header in exam_headers.iteritems():
        ident, tag, series, description = dm.scanid.parse_filename(path)

        if dm.scanid.make_filename(ident, tag, series, description) in ignored_series:
            if not QUIET: print("Ignoring {}".format(path))
            continue

        if tag not in std_headers:
            if not QUIET: 
                print("WARNING: {}: No matching standard for tag '{}'".format(
                path, tag))
            continue

        std_path, std_header = std_headers[tag]

        compare_headers(std_path, std_header, path, header, ignore)

def main():
    global QUIET
    arguments = docopt(__doc__)

    QUIET = arguments['--quiet']

    standardsdir = arguments['<standards>']
    examdirs     = arguments['<exam>']
    ignorelist   = arguments['--ignore-headers']
    series_file  = arguments['--ignore-series']
    
    if ignorelist:
        ignorelist = ignorelist.split(",")
    else:
        ignorelist = []

    ignored_series = []
    if series_file:
        table = pd.read_table(series_file, sep='\s*', engine="python")
        ignored_series = table["series"].tolist()

    manifest = dm.utils.get_all_headers_in_folder(standardsdir,recurse=True)
   
    # map tag name to headers 
    stdmap = { os.path.basename(os.path.dirname(k)):(k,v) for (k,v) in manifest.items()}

    for examdir in examdirs:
        compare_exam_headers(stdmap, examdir, ignorelist, ignored_series)
        
if __name__ == '__main__': 
    main()
