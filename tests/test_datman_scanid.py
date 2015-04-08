import datman.scanid as scanid
from nose.tools import *

@raises(scanid.ParseException)
def test_parse_empty(): 
    scanid.parse("")

@raises(scanid.ParseException)
def test_parse_None(): 
    scanid.parse(None)

@raises(scanid.ParseException)
def test_parse_garbage(): 
    scanid.parse("lkjlksjdf")

def test_parse_good_scanid():
    ident = scanid.parse("DTI_CMH_H001_01_02")
    eq_(ident.study, "DTI")
    eq_(ident.site, "CMH")
    eq_(ident.subject, "H001")
    eq_(ident.timepoint, "01")
    eq_(ident.session, "02")

def test_scanid_to_string():
    ident = scanid.Identifier("DTI","CMH","H001","01","02")
    eq_(str(ident),"DTI_CMH_H001_01_02")

def test_is_scanid_garbage():
    ok_(not scanid.is_scanid("garbage"))

def test_is_scanid_subjectid_only():
    ok_(not scanid.is_scanid("DTI_CMH_H001"))

def test_is_scanid_extra_fields():
    eq_(scanid.is_scanid("DTI_CMH_H001_01_01_01_01_01_01"), False)

def test_is_scanid_good():
    ok_(scanid.is_scanid("SPN01_CMH_0002_01_01"))

def test_get_full_subjectid():
    ident = scanid.parse("DTI_CMH_H001_01_02")
    eq_(ident.get_full_subjectid(), "DTI_CMH_H001")

def test_parse_PHA_scanid():
    ident = scanid.parse("DTI_CMH_PHA_ADN0001")
    eq_(ident.study, "DTI")
    eq_(ident.site, "CMH")
    eq_(ident.subject,"PHA_ADN0001")
    eq_(ident.timepoint, "")
    eq_(ident.session, "")
    eq_(str(ident),"DTI_CMH_PHA_ADN0001")

def test_subject_id_with_timepoint():
    ident = scanid.parse("DTI_CMH_H001_01_02")
    eq_(ident.get_full_subjectid_with_timepoint(), 'DTI_CMH_H001_01')

def test_PHA_timepoint():
    ident = scanid.parse("DTI_CMH_PHA_ADN0001")
    eq_(ident.get_full_subjectid_with_timepoint(), 'DTI_CMH_PHA_ADN0001')

def test_parse_filename():
    ident, tag, description = scanid.parse_filename(
            'DTI_CMH_H001_01_01_T1_description.nii.gz')
    eq_(str(ident), 'DTI_CMH_H001_01_01')
    eq_(tag, 'T1')
    eq_(description, 'description')

def test_parse_filename_PHA():
    ident, tag, description = scanid.parse_filename(
            'DTI_CMH_PHA_ADN0001_T1_description.nii.gz')
    eq_(str(ident), 'DTI_CMH_PHA_ADN0001')
    eq_(tag, 'T1')
    eq_(description, 'description')

def test_parse_filename_with_path():
    ident, tag, description = scanid.parse_filename(
            '/data/DTI_CMH_H001_01_01_T1_description.nii.gz')
    eq_(str(ident), 'DTI_CMH_H001_01_01')
    eq_(tag, 'T1')
    eq_(description, 'description')

# vim: ts=4 sw=4:
