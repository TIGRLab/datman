#!/usr/bin/env python
"""
Diffs the relevant fields of the header to determine if anything has changed in
the protocol.

Usage:
    dm-check-header.py [options] <standards/> <logdir/> <examsdir/>

Arguments:
    <standards/>            Folder with subfolders named by tag. Each subfolder
                            has a sample gold standard dicom file for that tag.

    <logdir/>               Folder to contain the outputs (specific errors found)
                            of this script. A log file is created in this
                            folder for each exam, named: dm-check-headers-<examdir>.log

    <examsdir/>             Folder with subfolder for each exam to check. Each
                            exam directory should have one dicom file sample
                            from each series to check.

Options:
    --filter TEXT           A string to filter exams by (ex. site name). All
                            exam folders found in <examsdir/> must have this
                            text in their name.
    --ignore-headers LIST   Comma delimited list of headers to ignore
    --verbose               Print mismatches to stdout as well as the log file
"""

import sys
import collections
from docopt import docopt
import dicom as dcm
import datman as dm
import glob
import logging as log
import numpy as np
import datman.utils
import os.path

DEFAULT_IGNORED_HEADERS = set([
    'AccessionNumber',
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
    'InstanceCreationDate',
    'InstanceCreationTime',
    'InstitutionAddress',
    'InversionTime',
    'ImagesInAcquisition',
    'InstanceNumber',
    'LargestImagePixelValue',
    'OperatorsName',
    'PatientID',
    'PatientSize',
    'PixelData',
    'ProtocolName',
    'RefdImageSequence',
    'RefdPerformedProcedureStepSequence',
    'RefdStudySequence',
    'ReferencedImageSequence',
    'ReferencedPerformedProcedureStepSequence',
    'ReferencedStudySequence',
    'RequestAttributesSequence',
    'RequestingPhysician',
    'PatientAge',
    'PatientBirthDate',
    'PatientName',
    'PatientSex',
    'PatientWeight',
    'PercentPhaseFieldOfView',
    'PerformedProcedureStepID',
    'PerformedProcedureStepStartDate',
    'PerformedProcedureStepStartTime',
    'PhysiciansOfRecord',
    'ReferringPhysicianName',
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

INTEGER_TOLERANCES = {
    # field           : interger difference
    'ImagingFrequency': 1,
    'EchoTime': 5,
}

DECIMAL_TOLERANCES = {
    'RepetitionTime': 1
}

# represents a mismatch between expected (gold standard) and actual
# headers for a file
Mismatch = collections.namedtuple(
    'Mismatch', ['header', 'expected', 'actual', 'tolerance'])

# Configuration object for the tolerances used in header compare
Tolerances = collections.namedtuple('Tolerances', ['integer', 'decimal'])

DEFAULT_TOLERANCES = Tolerances(
    integer=INTEGER_TOLERANCES,
    decimal=DECIMAL_TOLERANCES)


def get_gold_standard_headers(path):
    """Fetches the gold standard headers.

    Expects there to be subfolders named by the tag and containing a single
    dicom file representing the expected (gold standard) headers.

    Returns a map from tag -> headers.
    """
    manifest = dm.utils.get_all_headers_in_folder(path, recurse=True)
    map = {os.path.basename(os.path.dirname(k)): (k, v)
           for (k, v) in manifest.items()}
    return map


def compare_headers(stdhdr, cmphdr, tolerances=None, ignore_headers=None):
    """
    Accepts two pydicom objects and prints out header value differences.

    Headers in ignore set are ignored.

    Returns a tuple containing a list of mismatched headers (as a list of
    Mismatch objects)
    """

    tolerances = tolerances or DEFAULT_TOLERANCES
    ignore_headers = ignore_headers or []

    # dir() is expensive so we cache results here
    stdhdr_names = stdhdr.dir()
    cmphdr_names = cmphdr.dir()

    # get the unignored headers
    headers = set(stdhdr_names).union(cmphdr_names).difference(ignore_headers)

    mismatches = []  # list of Mismatches

    for header in headers:
        if header not in stdhdr_names:
            mismatches.append(Mismatch(
                header=header, expected=None, actual=cmphdr.get(header), tolerance=None))
            continue

        if header not in cmphdr_names:
            mismatches.append(Mismatch(
                header=header, expected=stdhdr.get(header), actual=None, tolerance=None))
            continue

        stdval = stdhdr.get(header)
        cmpval = cmphdr.get(header)

        # integer level tolerance
        if header in tolerances.integer:
            n = tolerances.integer[header]

            stdval_rounded = np.round(float(stdval))
            cmpval_rounded = np.round(float(cmpval))
            difference = np.abs(stdval_rounded - cmpval_rounded)

            if difference > n:
                mismatches.append(Mismatch(
                    header=header, expected=stdval_rounded, actual=cmpval_rounded, tolerance=n))

        # decimal level tolerance
        elif header in tolerances.decimal:
            n = tolerances.decimal[header]

            stdval_rounded = round(float(stdval), n)
            cmpval_rounded = round(float(cmpval), n)

            if stdval_rounded != cmpval_rounded:
                mismatches.append(Mismatch(
                    header=header, expected=stdval_rounded, actual=cmpval_rounded, tolerance=n))

        # no tolerance set
        elif str(cmpval) != str(stdval):
            mismatches.append(Mismatch(
                header=header, expected=stdval, actual=cmpval, tolerance=None))

    return mismatches


def compare_exam_headers(stdmap, examdir, ignore_headers, tolerances=None):
    """
    Compares headers for each series in an exam against gold standards

    <stdmap> is a map from description -> (cmppath, headers) of all of the
    standard headers to compare against.

    <ignore_headers> is a list of headers to ignore.
    """
    exam_headers = dm.utils.get_all_headers_in_folder(examdir)

    all_mismatches = {}
    for cmppath, cmphdr in exam_headers.iteritems():
        ident, tag, series, description = dm.scanid.parse_filename(cmppath)

        if tag not in stdmap:
            log.warning(
                "{}: No matching standard for tag '{}'".format(cmppath, tag))
            continue

        stdpath, stdhdr = stdmap[tag]
        mismatches = compare_headers(
            stdhdr, cmphdr, tolerances, ignore_headers)
        if mismatches:
            all_mismatches[cmppath] = mismatches

    return all_mismatches


def main():
    arguments = docopt(__doc__)
    standardsdir = arguments['<standards/>']
    logsdir = arguments['<logdir/>']
    examsdir = arguments['<examsdir/>']
    verbose = arguments['--verbose']
    filtertext = arguments['--filter']
    ignore_headers = arguments['--ignore-headers']

    log.basicConfig(
        level=log.WARN, format="[dm-check-headers] %(levelname)s: %(message)s")

    if verbose:
        log.getLogger('').setLevel(log.INFO)

    if not os.path.isdir(logsdir):
        log.error('Log directory {} does not exist'.format(logsdir))
        sys.exit(1)
    if not os.path.isdir(standardsdir):
        log.error('Standards directory {} does not exist'.format(standardsdir))
        sys.exit(1)
    if not os.path.isdir(examsdir):
        log.error('Exams directory {} does not exist'.format(examsdir))
        sys.exit(1)

    ignore_headers = ignore_headers and ignore_headers.split(",") or []
    ignore_headers = DEFAULT_IGNORED_HEADERS.union(ignore_headers)

    stdmap = get_gold_standard_headers(standardsdir)

    globexpr = '*'
    if filtertext:
        globexpr = '*{}*'.format(filtertext)

    for examdir in glob.glob('{}/{}/'.format(examsdir,globexpr)):
        if '_PHA_' in examdir:  # ignore phantoms
            continue

        logfile = os.path.join(logsdir, "dm-check-headers-{}.log".format(
            os.path.basename(os.path.normpath(examdir))))

        all_mismatches = compare_exam_headers(stdmap, examdir, ignore_headers)
        if not all_mismatches:
            continue

        if not os.path.exists(logfile):  # display warning on first encounter
            log.warn('{} mismatches for exam {}'.format(len(all_mismatches), examdir))

        with open(logfile, "w") as fname:
            for path, mismatches in all_mismatches.iteritems():
                for m in mismatches:
                    message = "{}: header {}, expected = {}, actual = {} [tolerance = {}]".format(
                        path, m.header, m.expected, m.actual, m.tolerance)
                    log.info(message)
                    fname.write(message + "\n")

if __name__ == '__main__':
    main()
