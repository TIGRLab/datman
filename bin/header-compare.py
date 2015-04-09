#!/usr/bin/env python
"""
Diffs the relevant fields of the header to determine if anything 
has changed in the protocol.

Usage: 
    header-compare.py <goldstd.dcm> <compare.dcm>
"""
import sys
from docopt import docopt
import dicom as dcm

ignored_headers = set([
    'AcquisitionDate',
    'AcquisitionTime',
    'ContentDate',
    'ContentTime',
    'FrameOfReferenceUID',
    'ImagePositionPatient',
    'InstanceNumber',
    'LargestImagePixelValue',
    'PatientID',
    'PixelData',
    'RefdImageSequence',
    'RefdPerformedProcedureStepSequence',
    'ReferencedImageSequence',
    'ReferencedPerformedProcedureStepSequence',
    'PatientName',
    'PatientWeight',
    'PerformedProcedureStepID',
    'PerformedProcedureStepStartDate',
    'PerformedProcedureStepStartTime',
    'SAR',
    'SOPInstanceUID',
    'SoftwareVersions',
    'SeriesNumber',
    'SeriesDate',
    'SeriesInstanceUID',
    'SeriesTime',
    'SliceLocation',
    'StudyDate',
    'StudyID',
    'StudyInstanceUID',
    'StudyTime',
    'WindowCenter',
    'WindowWidth',
])

def compare_headers(goldstd, compare):
    """
    Accepts two pydicom objects and prints out header value differences. 
    
    Headers in the ignore_header set are ignored.
    """
    goldstd_headers = set(goldstd.dir()).difference(ignored_headers)
    compare_headers = set(compare.dir()).difference(ignored_headers)

    only_goldstd = goldstd_headers.difference(compare_headers)
    only_compare = compare_headers.difference(goldstd_headers)
    both_headers = goldstd_headers.intersection(compare_headers)
   
    if only_goldstd: 
        print "The following headers appear only in the Gold standard:",
        print ", ".join(only_goldstd)

    if only_compare:
        print "The following headers appear only in the Comparison:",
        print ", ".join(only_compare)

    for header in both_headers:
        if str(goldstd.get(header)) != str(compare.get(header)):
            print("Header '{}' differs. Gold = '{}', Compare = '{}'".format(
                header, goldstd.get(header), compare.get(header)))

if __name__ == '__main__': 
    arguments = docopt(__doc__)
    goldfile = arguments['<goldstd.dcm>']
    compfile = arguments['<compare.dcm>']

    goldstd = dcm.read_file(goldfile)
    compare = dcm.read_file(compfile)

    compare_headers(goldstd, compare)
