#!/usr/bin/env python
"""
header-compare.py <goldstd.dcm> <compare.dcm>

Diffs the relevant fields of the header to determine if anything 
has changed in the protocol.
"""
import sys
import numpy as np
import dicom as dcm

def main(goldstd, compare):
    """
    Accepts two dicom objects (from pydicom). This removes a bunch of
    uninteresting dicom fields and compares the rest. Differences are 
    printed to STDOUT. This could be redirected to a file for QC purposes.
    """

    goldstd = dcm.read_file(goldstd)
    compare = dcm.read_file(compare)

    # get all the possible entries
    traits = goldstd.trait_names()
    header = []

    for trait in traits:
        if trait[0].isupper() == True:
            header.append(trait)

    # remove things we don't need
    header.remove('AcquisitionDate')
    header.remove('AcquisitionTime')
    header.remove('ContentDate')
    header.remove('ContentTime')
    header.remove('FrameOfReferenceUID')
    header.remove('ImagePositionPatient')
    header.remove('InstanceNumber')
    header.remove('LargestImagePixelValue')
    header.remove('PatientID')
    header.remove('PixelData')
    
    try:
        header.remove('RefdImageSequence')
    except:
        pass

    header.remove('RefdPerformedProcedureStepSequence')

    try:
        header.remove('ReferencedImageSequence')
    except:
        pass

    header.remove('ReferencedPerformedProcedureStepSequence')
    header.remove('PatientName')
    header.remove('PatientWeight')
    header.remove('PerformedProcedureStepID')
    header.remove('PerformedProcedureStepStartDate')
    header.remove('PerformedProcedureStepStartTime')
    header.remove('SAR')
    header.remove('SOPInstanceUID')
    header.remove('SoftwareVersions')
    header.remove('SeriesNumber')
    header.remove('SeriesDate')
    header.remove('SeriesInstanceUID')
    header.remove('SeriesTime')
    header.remove('SliceLocation')
    header.remove('StudyDate')
    header.remove('StudyID')
    header.remove('StudyInstanceUID')
    header.remove('StudyTime')
    header.remove('WindowCenter')
    header.remove('WindowWidth')

    # now find the differences
    for item in header:
        goldstdcmd = 'goldstd.' + item
        comparecmd = 'compare.' + item

        try:
            if eval(goldstdcmd) != eval(comparecmd):
                print(str(item) + ' differs: ')
                print('    GOLD:' + str(eval(goldstdcmd)))
                print('    COMP:' + str(eval(comparecmd)) + '\n')

        except:
            print(str(item) + """ isn't a valid property!""")

if __name__ == '__main__': 

    if len(sys.argv) == 2:
        compare_headers(goldstd, compare)
    else:
        print(__doc__)

