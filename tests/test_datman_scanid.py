import datman.scanid as scanid
from nose.tools import eq_, ok_, raises


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
    ident = scanid.Identifier("DTI", "CMH", "H001", "01", "02")
    eq_(str(ident), "DTI_CMH_H001_01_02")


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
    eq_(ident.subject, "PHA_ADN0001")
    eq_(ident.timepoint, "")
    eq_(ident.session, "")
    eq_(str(ident), "DTI_CMH_PHA_ADN0001")


def test_subject_id_with_timepoint():
    ident = scanid.parse("DTI_CMH_H001_01_02")
    eq_(ident.get_full_subjectid_with_timepoint(), 'DTI_CMH_H001_01')


def test_PHA_timepoint():
    ident = scanid.parse("DTI_CMH_PHA_ADN0001")
    eq_(ident.get_full_subjectid_with_timepoint(), 'DTI_CMH_PHA_ADN0001')


def test_parse_filename():
    ident, tag, series, description = scanid.parse_filename(
            'DTI_CMH_H001_01_01_T1_03_description.nii.gz')
    eq_(str(ident), 'DTI_CMH_H001_01_01')
    eq_(tag, 'T1')
    eq_(series, '03')
    eq_(description, 'description')


def test_parse_filename_PHA():
    ident, tag, series, description = scanid.parse_filename(
            'DTI_CMH_PHA_ADN0001_T1_02_description.nii.gz')
    eq_(str(ident), 'DTI_CMH_PHA_ADN0001')
    eq_(tag, 'T1')
    eq_(series, '02')
    eq_(description, 'description')


def test_parse_filename_PHA_2():
    ident, tag, series, description = scanid.parse_filename(
            'SPN01_MRC_PHA_FBN0013_RST_04_EPI-3x3x4xTR2.nii.gz')
    eq_(ident.study, 'SPN01')
    eq_(ident.site, 'MRC')
    eq_(ident.subject, 'PHA_FBN0013')
    eq_(ident.timepoint, '')
    eq_(ident.session, '')
    eq_(str(ident), 'SPN01_MRC_PHA_FBN0013')
    eq_(tag, 'RST')
    eq_(series, '04')
    eq_(description, 'EPI-3x3x4xTR2')


def test_parse_filename_with_path():
    ident, tag, series, description = scanid.parse_filename(
            '/data/DTI_CMH_H001_01_01_T1_02_description.nii.gz')
    eq_(str(ident), 'DTI_CMH_H001_01_01')
    eq_(tag, 'T1')
    eq_(series, '02')
    eq_(description, 'description')


def test_parse_bids_filename():
    ident = scanid.parse_bids_filename("sub-CMH0001_ses-01_run-1_T1w.nii.gz")
    assert ident.subject == 'CMH0001'
    assert ident.session == '01'
    assert ident.run == '1'
    assert ident.suffix == 'T1w'


def test_parse_bids_filename_with_full_path():
    ident = scanid.parse_bids_filename(
        "/some/folder/sub-CMH0001_ses-01_run-1_T1w.nii.gz")
    assert ident.subject == 'CMH0001'
    assert ident.session == '01'
    assert ident.run == '1'
    assert ident.suffix == 'T1w'


def test_parse_bids_filename_without_ext():
    ident = scanid.parse_bids_filename(
        "/some/folder/sub-CMH0001_ses-02_run-3_T1w")
    assert ident.subject == 'CMH0001'
    assert ident.session == '02'
    assert ident.run == '3'
    assert ident.suffix == 'T1w'


def test_parse_bids_filename_without_run():
    scanid.parse_bids_filename("sub-CMH0001_ses-01_T1w.nii.gz")


@raises(scanid.ParseException)
def test_parse_bids_filename_missing_subject():
    scanid.parse_bids_filename("ses-01_run-1_T1w")


@raises(scanid.ParseException)
def test_parse_bids_filename_malformed_subject():
    scanid.parse_bids_filename("CMH0001_ses-01_run-1_T1w")


@raises(scanid.ParseException)
def test_parse_bids_filename_missing_session():
    scanid.parse_bids_filename("sub-CMH0001_run-1_T1w")


@raises(scanid.ParseException)
def test_parse_bids_filename_malformed_session():
    scanid.parse_bids_filename("sub-CMH0001_ses-_run-1_T1w")


@raises(scanid.ParseException)
def test_parse_bids_filename_missing_suffix():
    scanid.parse_bids_filename("sub-CMH0001_ses-01_run-1.nii.gz")


@raises(scanid.ParseException)
def test_parse_bids_filename_missing_suffix_and_run():
    scanid.parse_bids_filename("sub-CMH0001_ses-01.nii.gz")


@raises(scanid.ParseException)
def test_unknown_entity_does_not_get_set_as_suffix():
    scanid.parse_bids_filename("sub-CMH_ses-01_new-FIELD_T1w.nii.gz")


@raises(scanid.ParseException)
def test_empty_entity_name_does_not_get_set_as_suffix():
    scanid.parse_bids_filename("sub-CMH_ses-01_-FIELD_T1w.nii.gz")


@raises(scanid.ParseException)
def test_empty_entity_name_and_label_does_not_get_set_as_suffix():
    scanid.parse_bids_filename("sub-CMH_ses-01_-_T1w.nii.gz")


@raises(scanid.ParseException)
def test_bids_file_raises_exception_when_wrong_entities_used_for_anat():
    scanid.parse_bids_filename("sub-CMH0001_ses-01_ce-somefield_dir-somedir"
                               "_run-1_T1w.nii.gz")


@raises(scanid.ParseException)
def test_bids_file_raises_exception_when_wrong_entities_used_for_task():
    scanid.parse_bids_filename("sub-CMH0001_ses-01_task-sometask_"
                               "ce-somefield_run-1_T1w.nii.gz")


@raises(scanid.ParseException)
def test_bids_file_raises_exception_when_wrong_entities_used_for_fmap():
    scanid.parse_bids_filename("sub-CMH0001_ses-01_dir-somedir_"
                               "rec-somefield_run-1_T1w.nii.gz")


def test_optional_entities_dont_get_parsed_as_suffix():
    optional_entities = "sub-CMH0001_ses-01_{}_T1w.nii.gz"
    for entity in ['run', 'acq', 'ce', 'rec', 'echo', 'ce',
                   'mod', 'task']:
        optional_field = '{}-11'.format(entity)
        bids_name = optional_entities.format(optional_field)
        parsed = scanid.parse_bids_filename(bids_name)
        assert optional_field not in parsed.suffix


def test_bids_file_equals_string_of_itself():
    bids_name = "sub-CMH0001_ses-01_run-1_T1w"
    ident = scanid.parse_bids_filename(bids_name)
    assert ident == bids_name


def test_bids_file_equals_string_of_itself_minus_run():
    bids_name = "sub-CMH0001_ses-01_run-1_T1w"
    ident = scanid.parse_bids_filename(bids_name)
    assert ident == bids_name.replace("run-1_", "")


def test_bids_file_equals_itself_with_path_and_ext():
    bids_name = "sub-CMH0001_ses-01_run-1_T1w"
    bids_full_path = "/some/folder/somewhere/{}.nii.gz".format(bids_name)
    ident = scanid.parse_bids_filename(bids_name)
    assert ident == bids_full_path


def test_bids_file_correctly_parses_when_all_anat_entities_given():
    anat_bids = "sub-CMH0001_ses-01_acq-abcd_ce-efgh_rec-ijkl_" + \
                "run-1_mod-mnop_somesuffix"

    parsed = scanid.parse_bids_filename(anat_bids)
    assert str(parsed) == anat_bids


def test_bids_file_correctly_parses_when_all_task_entities_given():
    task_bids = "sub-CMH0001_ses-01_task-abcd_acq-efgh_" + \
                "rec-ijkl_run-1_echo-11_imi"

    parsed = scanid.parse_bids_filename(task_bids)
    assert str(parsed) == task_bids


def test_bids_file_correctly_parses_when_all_fmap_entities_given():
    fmap_bids = "sub-CMH0001_ses-01_acq-abcd_dir-efgh_run-1_fmap"

    parsed = scanid.parse_bids_filename(fmap_bids)
    assert str(parsed) == fmap_bids


def test_bids_file_handles_prelapse_session_strings():
    prelapse_file = "sub-BRG33006_ses-01R_run-1_something"

    parsed = scanid.parse_bids_filename(prelapse_file)
    assert str(parsed) == prelapse_file
