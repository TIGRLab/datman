#!/usr/bin/env python
"""
Diffs the relevant fields of the header to determine if anything has changed in
the protocol.

Usage: 
    dm-check-header.py [options] <standards> <logs> <exam>...

Arguments: 
    <standards/>            Folder with subfolders named by tag. Each subfolder
                            has a sample gold standard dicom file for that tag.

    <logs/>                 Folder to contain the outputs (specific errors found)
                            of this script.

    <exam/>                 Folder with one dicom file sample from each series
                            to check

Options: 
    --quiet                 Don't print warnings
    --ignore-headers LIST   Comma delimited list of headers to ignore

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

ignored_headers = set([
    'AcquisitionDate',
    'AcquisitionTime',
    'AcquisitionNumber',
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

def get_subject_from_filename(filename):
    filename = os.path.basename(filename)
    filename = filename.split('_')[0:5]
    filename = '_'.join(filename)

    return filename

def compare_headers(stdpath, stdhdr, cmppath, cmphdr, ignore, logsdir, errors):
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
        print("{cmppath}: headers in series, not in standard: {list}".format(cmppath=cmppath, list=", ".join(only_stdhdr)))

    if only_cmphdr:
        print("{cmppath}: headers in standard, not in series: {list}".format(cmppath=cmppath, list=", ".join(only_cmphdr)))
    
    for header in both_hdr:
        stdval = stdhdr.get(header)
        cmpval = cmphdr.get(header)

        # integer level tolerance
        if header in integer_tolerances:
            n = integer_tolerances[header]

            stdval_rounded = np.round(float(stdval))
            cmpval_rounded = np.round(float(cmpval))
            difference = np.abs(stdval_rounded - cmpval_rounded)

            if difference > n:
                with open(os.path.join(logsdir, get_subject_from_filename(cmppath) + '.log'), "a") as fname:
                    fname.write(
                        "{}: header {}, expected = {}, actual = {} [tolerance = {}]\n".format(
                            cmppath, header, stdval_rounded, cmpval_rounded, n))
                errors = errors + 1

        # decimal level tolerance
        elif header in decimal_tolerances:
            n = decimal_tolerances[header]

            stdval_rounded = round(float(stdval), n)
            cmpval_rounded = round(float(cmpval), n)

            if stdval_rounded != cmpval_rounded:
                with open(os.path.join(logsdir, get_subject_from_filename(cmppath) + '.log'), "a") as fname:
                    fname.write(
                        "{}: header {}, expected = {}, actual = {} [tolerance = {}]\n".format(
                            cmppath, header, stdval_rounded, cmpval_rounded, n))
                errors = errors + 1

        # no tolerance set
        elif str(cmpval) != str(stdval):
            with open(os.path.join(logsdir, get_subject_from_filename(cmppath) + '.log'), "a") as fname:
                fname.write(
                    "{}: header {}, expected = {}, actual = {}\n".format(
                        cmppath, header, stdval, cmpval))
            errors = errors + 1

    return errors

def compare_exam_headers(stdmap, examdir, ignorelist, logsdir):
    """
    Compares headers for each series in an exam against gold standards

    <stdmap> is a map from description -> (cmppath, headers) of all of the
    standard headers to compare against. 

    <ignorelist> is a list of headers, in addition to the defaults, to ignore. 
    """
    exam_headers = dm.utils.get_all_headers_in_folder(examdir)

    ignore = ignored_headers.union(ignorelist)

    try:
        dm.utils.run('rm {}'.format(os.path.join(logsdir, get_subject_from_filename(cmppath) + '.log')))
    except:
        pass

    errors = 0 # if this counter gets tripped, we print a single warning to the screen per subject
    for cmppath, cmphdr in exam_headers.iteritems():
        ident, tag, series, description = dm.scanid.parse_filename(cmppath)

        if tag not in stdmap:
            if not QUIET: 
                print("WARNING: {}: No matching standard for tag '{}'".format(cmppath, tag))
            continue

        stdpath, stdhdr = stdmap[tag]

        errors = compare_headers(stdpath, stdhdr, cmppath, cmphdr, ignore, logsdir, errors)

    if errors > 0:
        print('ERROR: {} header mismatches for {}'.format(errors, get_subject_from_filename(cmppath)))

def main():
    global QUIET
    arguments = docopt(__doc__)

    QUIET = arguments['--quiet']

    standardsdir = arguments['<standards>']
    logsdir      = arguments['<logs>']
    examdirs     = arguments['<exam>']
    ignorelist   = arguments['--ignore-headers']

    logsdir = dm.utils.define_folder(logsdir)

    # check inputs
    if os.path.isdir(logsdir) == False:
        print('ERROR: Log directory {} does not exist'.format(logsdir))
        sys.exit()
    if os.path.isdir(standardsdir) == False:
        print('ERROR: Standards directory {} does not exist'.format(standardsdir))
        sys.exit()

    if ignorelist:
        ignorelist = ignorelist.split(",")
    else:
        ignorelist = []

    manifest = dm.utils.get_all_headers_in_folder(standardsdir, recurse=True)
   
    # map tag name to headers 
    stdmap = { os.path.basename(os.path.dirname(k)):(k,v) for (k,v) in manifest.items()}

    # remove phantoms from examdirs
    examdirs = filter(lambda x: '_PHA_' not in x, examdirs)

    for examdir in examdirs:
        compare_exam_headers(stdmap, examdir, ignorelist, logsdir)
        
if __name__ == '__main__': 
    main()
