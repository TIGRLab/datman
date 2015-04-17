#!/usr/bin/env python
"""
Diffs the relevant fields of the header to determine if anything has changed in
the protocol.

Usage: 
    header-compare.py file <goldstandard.dcm> <compare.dcm>
    header-compare.py exam <goldstandards/> <exam/>

Arguments: 
    <goldstandard.dcm>      Dicom file to compare against

    <compare.dcm>           Dicom file to compare

    <goldstandards/>        Folder with gold standard dicom files.

    <exam/>                 Folder with exam series data. A single dicom from 
                            each series is compared against the gold standard 
                            with the matching description.
"""
import sys
from docopt import docopt
import dicom as dcm
import datman as dm
import datman.utils

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
        different = True

    if only_compare:
        print "The following headers appear only in the Comparison:",
        print ", ".join(only_compare)
    
    for header in both_headers:
        if str(goldstd.get(header)) != str(compare.get(header)):
            print("Header '{}' differs. Gold = '{}', Compare = '{}'".format(
                header, goldstd.get(header), compare.get(header)))
            different = True

def compare_exam_headers(standarddir, examdir):
    """
    Compares headers for each series in an exam against gold standards
    """
    std_headers  = dm.utils.get_all_headers_in_folder(standarddir,recurse=True)
    std_headers  = {v.get("SeriesDescription") : (k,v) for (k,v) in \
            std_headers.items()}
    exam_headers = dm.utils.get_archive_headers(examdir)

    for path, header in exam_headers.iteritems():
        description = header.get("SeriesDescription")

        if description not in std_headers:
            print("ERROR: {}: No matching standard for series '{}'".format(
                path, description))
            continue

        std_path, std_header = std_headers[description]

        print("Comparing {} against gold standard {}".format(
            path, std_path))

        compare_headers(std_header, header)
        print

def main():
    arguments = docopt(__doc__)

    if arguments['<goldstandard.dcm>']:
        goldfile = arguments['<goldstandard.dcm>']
        compfile = arguments['<compare.dcm>']

        goldstd = dcm.read_file(goldfile)
        compare = dcm.read_file(compfile)

        compare_headers(goldstd, compare)
    else:
        standarddir = arguments['<goldstandards/>']
        examdir     = arguments['<exam/>']

        compare_exam_headers(standarddir, examdir)
        
if __name__ == '__main__': 
    main()
