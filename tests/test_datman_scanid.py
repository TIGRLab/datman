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
    ok_(not scanid.is_scanid("DTI_CMH_H001_01_01_01_01_01_01"))

def test_is_scanid_good():
    ok_(scanid.is_scanid("SPN01_CMH_0002_01_01"))

# vim: ts=4 sw=4:
