#!/usr/bin/env python
"""
Diffs the relevant fields of the header to determine if anything has changed in
the protocol.

Usage:
    dm-check-header.py [options] <standards> <exam>...

Arguments:
    <standards/>             Folder with subfolders named by tag. Each subfolder
                             has a sample gold standard dicom file for that tag.

    <exam/>                  Folder with one dicom file sample from each series
                             to check

Options:
    --quiet                  Don't print warnings
    --verbose                Print warnings
    --blacklist-fails FILE   Append series that fail to the blacklist (requires path to blacklist.csv)
    --ignore-headers LIST    Comma delimited list of header fields to ignore

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


# QUIET = False

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

    # create string object to hold errors
    errors = []

    if only_stdhdr:
        thiserror = "{cmppath}: headers in series, not in standard: {list}".format(
            cmppath=cmppath, list=", ".join(only_stdhdr))
        errors.append(thiserror)

    if only_cmphdr:
        thiserror = "{cmppath}: headers in standard, not in series: {list}".format(
            cmppath=cmppath, list=", ".join(only_cmphdr))
        errors.append(thiserror)

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
                errors.append(msg.format(cmppath, header, stdval_rounded, cmpval_rounded, n))

        elif header in decimal_tolerances:
            n = decimal_tolerances[header]

            stdval_rounded = round(float(stdval), n)
            cmpval_rounded = round(float(cmpval), n)

            if stdval_rounded != cmpval_rounded:
                msg = "{}: header {}, expected = {}, actual = {} [tolerance = {}]"
                errors.append(msg.format(cmppath, header, stdval_rounded, cmpval_rounded, n))

        elif str(cmpval) != str(stdval):
            errors.append("{}: header {}, expected = {}, actual = {}".format(
                    cmppath, header, stdval, cmpval))

    # if any errors occured - then write them to a log file
    if len(errors) > 0:
        with open(cmppath + '.ckheadersfailed', "w") as errorlog:
            for item in errors:
                errorlog.write("%s\n" % item)
        if QUIET == False:
            print('/n'.join(errors))


def compare_exam_headers(std_headers, examdir, ignorelist):
    """
    Compares headers for each series in an exam against gold standards

    <std_headers> is a map from description -> (path, headers) of all of the
    standard headers to compare against.

    <ignorelist> is a list of headers, in addition to the defaults, to ignore.

    <blacklist> pandas dataframe to update with header to fail
    """
    exam_headers = dm.utils.get_all_headers_in_folder(examdir)

    ignore = ignored_headers.union(ignorelist)

    ## make list to capure new errors
    newerrors = []
    for path, header in exam_headers.iteritems():
        ident, tag, series, description = dm.scanid.parse_filename(path)
        print("tag is {}".format(tag))

        if tag not in std_headers:
            if not QUIET:
                print("WARNING: {}: No matching standard for tag '{}'".format(path, tag))
            continue

        std_path, std_header = std_headers[tag]

        ### compare the headers for each header in exam series
        if not os.path.isfile(path + '.ckheadersfailed'):
            compare_headers(std_path, std_header, path, header, ignore)
            ## if new error logs were created make a note to blurp out
            if os.path.isfile(path + '.ckheadersfailed'):
                newerrors.append(tag)
                ## add the info to the blacklist
                stem = os.path.basename(path).replace('.dcm','')
                if blacklistfile != None:
                    with open(blacklistfile, "a") as blacklist:
                        blacklist.writeline("{} header-not-matching".format(stem))        for item in errors:


    #write message to log to report that an error occured
    if len(newerrors) > 0 :
        print("{} failed check headers of tags: {}".format(examdir,','.join(newerrors)))




def main():
    global QUIET
    global VERBOSE
    arguments = docopt(__doc__)

    QUIET         = arguments['--quiet']
    VERBOSE       = arguments['--verbose']
    standardsdir  = arguments['<standards>']
    examdirs      = arguments['<exam>']
    blacklistfile = arguments['--blacklist-fails']
    ignorelist    = arguments['--ignore-headers']

    #parse the ignorelist
    if ignorelist:
        ignorelist = ignorelist.split(",")
    else:
        ignorelist = []

    # get tags for gold standards from standardsdir subfolder names
    standardsdir = os.path.normpath(standardsdir)
    manifest = dm.utils.get_all_headers_in_folder(standardsdir,recurse=True)

    # scoop up all the header infomation from standards into one dictionary
    stdmap = { os.path.basename(os.path.dirname(k)):(k,v) for (k,v) in manifest.items()}

    # ## if blacklistfile was given load it - if not make a new one
    # if blacklistfile != None:
    #     if os.path.isfile(blacklistfile):
    #         bl = pd.read_table(blacklistfile, sep='\s*',engine='python')
    #     else:
    #         print('WARNING: could not find blacklistfile {} writing new one'.format(blacklistfile))
    #         bl = pd.DataFrame(columns = ['series', 'reason'])
    # else:
    #     bl = pd.DataFrame(columns = ['series', 'reason'])

    # run compare_exam_headers for each examdir given
    for examdir in examdirs:
        compare_exam_headers(stdmap, examdir, ignorelist)

    # ## if blacklistfile was given - write the results out to csv
    # if blacklistfile != None:
    #     bl.to_csv(blacklistfile, sep=' ')



if __name__ == '__main__':
    main()
