from nose.tools import *
import importlib
import sys
from StringIO import StringIO

check = importlib.import_module('bin.dm-check-bvecs')

FIXTURE_DIR = 'tests/fixture_dm-check-bvecs'

def test_no_dti():
    standardsdir = FIXTURE_DIR + '/gold-standards'
    examsdir     = FIXTURE_DIR + '/data/nii'
    emptyexam    = examsdir + '/SPN01_CMH_PHA_FBN0002'
    diffs = check.diff_files(emptyexam, standardsdir)

    expected = {}
    assert diffs == expected

def test_matching_bvec_bval():
    standardsdir = FIXTURE_DIR + '/gold-standards'
    examsdir     = FIXTURE_DIR + '/data/nii'
    emptyexam    = examsdir + '/SPN01_CMH_PHA_FBN0001'
    diffs = check.diff_files(emptyexam, standardsdir)

    expected = {}
    assert diffs == expected, diffs

def test_mismatched_bvec_bval():
    standardsdir = FIXTURE_DIR + '/gold-standards'
    examsdir     = FIXTURE_DIR + '/data/nii'
    emptyexam    = examsdir + '/SPN01_CMH_PHA_FBN0000'
    diffs = check.diff_files(emptyexam, standardsdir)

    bval = FIXTURE_DIR + '/data/nii/SPN01_CMH_PHA_FBN0000/SPN01_CMH_PHA_FBN0000_DTI60-1000_04_Ax-DTI-60+5-NOASSET-incomplete.bval'
    bvec = FIXTURE_DIR + '/data/nii/SPN01_CMH_PHA_FBN0000/SPN01_CMH_PHA_FBN0000_DTI60-1000_04_Ax-DTI-60+5-NOASSET-incomplete.bvec'
    assert bval in diffs.keys()
    assert bvec in diffs.keys()

