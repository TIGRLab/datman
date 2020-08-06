import datman.scanid as scanid
import pytest


def test_parse_empty():
    with pytest.raises(scanid.ParseException):
        scanid.parse("")


def test_parse_None():
    with pytest.raises(scanid.ParseException):
        scanid.parse(None)


def test_parse_garbage():
    with pytest.raises(scanid.ParseException):
        scanid.parse("lkjlksjdf")


def test_parse_good_datman_scanid():
    ident = scanid.parse("DTI_CMH_H001_01_02")
    assert ident.study == "DTI"
    assert ident.site == "CMH"
    assert ident.subject == "H001"
    assert ident.timepoint == "01"
    assert ident.session == "02"


def test_parse_good_datman_PHA_scanid():
    ident = scanid.parse("DTI_CMH_PHA_ADN0001")
    assert ident.study == "DTI"
    assert ident.site == "CMH"
    assert ident.subject == "PHA_ADN0001"
    assert ident.timepoint == ""
    assert ident.session == ""
    assert str(ident) == "DTI_CMH_PHA_ADN0001"


def test_parse_good_date_based_datman_pha_scanid():
    ident = scanid.parse("OPT01_UTO_PHA_FBN190603")
    assert ident.study == "OPT01"
    assert ident.site == "UTO"
    assert ident.subject == "PHA_FBN190603"
    assert ident.timepoint == ""
    assert str(ident) == "OPT01_UTO_PHA_FBN190603"


def test_parse_good_kcni_scanid():
    ident = scanid.parse("ABC01_CMH_12345678_01_SE02_MR")
    assert ident.study == 'ABC01'
    assert ident.site == 'CMH'
    assert ident.subject == '12345678'
    assert ident.timepoint == '01'
    assert ident.session == '02'


def test_parse_good_kcni_PHA_scanid():
    ident = scanid.parse("ABC01_CMH_LEGPHA_0001_MR")
    assert ident.study == 'ABC01'
    assert ident.site == 'CMH'
    assert ident.subject == 'PHA_LEG0001'


def test_parses_datman_subject_id_as_datman_identifier():
    dm_subject = "DTI01_CMH_H001_01_02"
    ident = scanid.parse(dm_subject)
    assert isinstance(ident, scanid.DatmanIdentifier)


def test_parses_datman_pha_id_as_datman_identifier():
    dm_pha = "DTI01_CMH_PHA_FBN0001"
    ident = scanid.parse(dm_pha)
    assert isinstance(ident, scanid.DatmanIdentifier)


def test_parses_kcni_subject_id_as_kcni_identifier():
    kcni_subject = "DTI01_CMH_H001_01_SE02_MR"
    ident = scanid.parse(kcni_subject)
    assert isinstance(ident, scanid.KCNIIdentifier)


def test_parses_kcni_pha_id_as_kcni_identifier():
    kcni_pha = "DTI01_CMH_ABCPHA_0001_MR"
    ident = scanid.parse(kcni_pha)
    assert isinstance(ident, scanid.KCNIIdentifier)


def test_parse_exception_when_kcni_subject_id_modality_missing():
    with pytest.raises(scanid.ParseException):
        scanid.parse("DTI01_CMH_H001_01_SE02")


def test_parse_exception_when_kcni_pha_id_modality_missing():
    with pytest.raises(scanid.ParseException):
        scanid.parse("DTI01_CMH_ABCPHA_0001")


def test_parse_exception_when_kcni_session_malformed():
    with pytest.raises(scanid.ParseException):
        scanid.parse("DTI01_CMH_H001_01_02_MR")


def test_user_settings_id_type_respected():
    # Datman IDs should be rejected if user says to parse only KCNI IDs
    with pytest.raises(scanid.ParseException):
        scanid.parse("DTI01_CMH_H001_01_02", settings={'ID_TYPE': 'KCNI'})

    # KCNI IDs should be rejected if the user says to parse only Datman IDs
    with pytest.raises(scanid.ParseException):
        scanid.parse("DTI01_CMH_H001_01_SE02_MR",
                     settings={'ID_TYPE': 'DATMAN'})


def test_kcni_study_field_is_modified_when_settings_given():
    settings = {
        'STUDY': {
            'DTI01': 'DTI'
        }
    }
    kcni_id = "DTI01_CMH_H001_01_SE02_MR"
    ident = scanid.parse(kcni_id, settings=settings)

    assert ident.study == 'DTI'
    assert str(ident) == "DTI_CMH_H001_01_02"


def test_kcni_site_field_is_modified_when_settings_given():
    settings = {
        'SITE': {
            'UTO': 'UT2'
        }
    }
    kcni_id = 'ABC01_UTO_12345678_01_SE02_MR'
    ident = scanid.parse(kcni_id, settings=settings)

    assert ident.site == 'UT2'
    assert str(ident) == 'ABC01_UT2_12345678_01_02'


def test_get_kcni_identifier_from_datman_str():
    kcni_ident = scanid.get_kcni_identifier("ABC01_UTO_12345678_01_02")
    assert isinstance(kcni_ident, scanid.KCNIIdentifier)
    assert kcni_ident.orig_id == "ABC01_UTO_12345678_01_SE02_MR"


def test_get_kcni_identifier_from_datman_pha_str():
    kcni_ident = scanid.get_kcni_identifier("ABC01_CMH_PHA_FBN0001")
    assert isinstance(kcni_ident, scanid.KCNIIdentifier)
    assert kcni_ident.orig_id == "ABC01_CMH_FBNPHA_0001_MR"


def test_get_kcni_identifier_from_datman_date_based_pha_str():
    kcni_ident = scanid.get_kcni_identifier("OPT01_UTO_PHA_FBN190603")
    assert isinstance(kcni_ident, scanid.KCNIIdentifier)
    assert kcni_ident.orig_id == "OPT01_UTO_FBNPHA_190603_MR"


def test_get_kcni_identifier_from_datman_ident():
    ident = scanid.parse("SPN01_CMH_0001_01_01")
    kcni_ident = scanid.get_kcni_identifier(ident)
    assert isinstance(kcni_ident, scanid.KCNIIdentifier)
    assert kcni_ident.orig_id == "SPN01_CMH_0001_01_SE01_MR"


def test_get_kcni_identifier_from_datman_pha_ident():
    dm_ident = scanid.parse("OPT01_UTO_PHA_ADN0001")
    kcni_ident = scanid.get_kcni_identifier(dm_ident)
    assert isinstance(kcni_ident, scanid.KCNIIdentifier)
    assert kcni_ident.orig_id == "OPT01_UTO_ADNPHA_0001_MR"


def test_get_kcni_identifier_from_datman_with_field_changes():
    settings = {
        "STUDY": {
            "AND01": "ANDT"
        },
        "SITE": {
            "UTO": "CMH"
        }
    }

    kcni = scanid.get_kcni_identifier("ANDT_CMH_0001_01_01", settings)
    assert kcni.study == "ANDT"
    assert kcni.site == "CMH"
    assert kcni.orig_id == "AND01_UTO_0001_01_SE01_MR"

    kcni_pha = scanid.get_kcni_identifier("ANDT_CMH_PHA_FBN0023", settings)
    assert kcni_pha.study == "ANDT"
    assert kcni_pha.site == "CMH"
    assert kcni_pha.orig_id == "AND01_UTO_FBNPHA_0023_MR"


def test_get_kcni_identifier_handles_already_kcni():
    kcni = "ABC01_UTO_12345678_01_SE02_MR"
    kcni_ident = scanid.parse(kcni)

    kcni1 = scanid.get_kcni_identifier(kcni)
    assert isinstance(kcni1, scanid.KCNIIdentifier)
    assert kcni1.orig_id == kcni

    kcni2 = scanid.get_kcni_identifier(kcni_ident)
    assert isinstance(kcni2, scanid.KCNIIdentifier)
    assert kcni2.orig_id == kcni


def test_datman_converted_to_kcni_and_back_is_unmodified():
    orig_datman = 'SPN01_CMH_0001_01_01'

    dm_ident = scanid.parse(orig_datman)
    kcni = scanid.get_kcni_identifier(dm_ident)
    assert isinstance(kcni, scanid.KCNIIdentifier)

    new_datman = scanid.parse(str(kcni))
    assert str(new_datman) == orig_datman


def test_kcni_converted_to_datman_and_back_is_unmodified():
    orig_kcni = 'SPN01_CMH_0001_01_SE01_MR'
    kcni_ident = scanid.parse(orig_kcni)
    datman = scanid.parse(str(kcni_ident))
    assert isinstance(datman, scanid.DatmanIdentifier)

    new_kcni = scanid.get_kcni_identifier(datman)
    assert new_kcni.orig_id == orig_kcni


def test_id_field_changes_correct_for_repeat_conversions():
    settings = {
        'STUDY': {
            'AND01': 'ANDT'
        },
        'SITE': {
            'UTO': 'CMH'
        }
    }
    correct_kcni = "AND01_UTO_0001_01_SE01_MR"
    correct_datman = "ANDT_CMH_0001_01_01"

    # KCNI to datman and back
    kcni_ident = scanid.parse(correct_kcni, settings)
    dm_ident = scanid.parse(str(kcni_ident), settings)
    assert str(dm_ident) == correct_datman

    new_kcni = scanid.get_kcni_identifier(dm_ident, settings)
    assert new_kcni.orig_id == correct_kcni

    # Datman to KCNI and back
    dm_ident = scanid.parse(correct_datman, settings)
    kcni_ident = scanid.get_kcni_identifier(dm_ident, settings)
    assert kcni_ident.orig_id == correct_kcni

    new_dm = scanid.parse(str(kcni_ident), settings)
    assert str(new_dm) == correct_datman


def test_kcni_get_xnat_subject_id_not_affected_by_field_translation():
    settings = {
        "STUDY": {
            "ABC01": "ABCD"
        }
    }

    pha = "ABC01_CMH_LEGPHA_0001_MR"
    pha_ident = scanid.parse(pha, settings)
    assert pha_ident.get_xnat_subject_id() == "ABC01_CMH_LEGPHA"

    sub = "ABC01_CMH_12345678_01_SE02_MR"
    sub_ident = scanid.parse(sub, settings)
    assert sub_ident.get_xnat_subject_id() == "ABC01_CMH_12345678"


def test_kcni_get_xnat_experiment_id_not_affected_by_field_translations():
    settings = {
        "STUDY": {
            "ABC01": "ABCD"
        }
    }

    pha = "ABC01_CMH_LEGPHA_0001_MR"
    pha_ident = scanid.parse(pha, settings)
    assert pha_ident.get_xnat_experiment_id() == pha

    sub = "ABC01_CMH_12345678_01_SE02_MR"
    sub_ident = scanid.parse(sub, settings)
    assert sub_ident.get_xnat_experiment_id() == sub


def test_is_scanid_garbage():
    assert not scanid.is_scanid("garbage")


def test_is_scanid_subjectid_only():
    assert not scanid.is_scanid("DTI_CMH_H001")


def test_is_scanid_extra_fields():
    assert scanid.is_scanid("DTI_CMH_H001_01_01_01_01_01_01") is False


def test_is_datman_scanid_good():
    assert scanid.is_scanid("SPN01_CMH_0002_01_01")


def test_is_kcni_scanid_good():
    assert scanid.is_scanid("SPN01_CMH_0001_01_SE01_MR")


def test_is_scanid_good_when_already_parsed():
    parsed = scanid.parse("DTI_CMH_H001_01_01")
    assert scanid.is_scanid(parsed)


def test_is_scanid_with_session_when_already_parsed():
    parsed = scanid.parse("OPT01_UT2_UT10001_01_01")
    assert scanid.is_scanid_with_session(parsed)


def test_get_full_subjectid():
    ident = scanid.parse("DTI_CMH_H001_01_02")
    assert ident.get_full_subjectid() == "DTI_CMH_H001"


def test_subject_id_with_timepoint():
    ident = scanid.parse("DTI_CMH_H001_01_02")
    assert ident.get_full_subjectid_with_timepoint() == 'DTI_CMH_H001_01'


def test_PHA_timepoint():
    ident = scanid.parse("DTI_CMH_PHA_ADN0001")
    assert ident.get_full_subjectid_with_timepoint() == 'DTI_CMH_PHA_ADN0001'


def test_parse_filename():
    ident, tag, series, description = scanid.parse_filename(
        'DTI_CMH_H001_01_01_T1_03_description.nii.gz')
    assert str(ident) == 'DTI_CMH_H001_01_01'
    assert tag == 'T1'
    assert series == '03'
    assert description == 'description'


def test_parse_filename_parses_when_tag_contains_pha():
    ident, tag, series, description = scanid.parse_filename(
        "CLZ_CMP_0000_01_01_PHABCD_11_FieldMap-2mm")

    assert str(ident) == "CLZ_CMP_0000_01_01"
    assert tag == "PHABCD"
    assert series == "11"
    assert description == "FieldMap-2mm"

    _, tag, _, _ = scanid.parse_filename(
        "CLZ_CMP_0000_01_01_ABCPHA_11_FieldMap-2mm")
    assert tag == "ABCPHA"

    _, tag, _, _ = scanid.parse_filename(
        "CLZ_CMP_0000_01_01_ABCPHADEF_11_FieldMap-2mm")
    assert tag == "ABCPHADEF"


def test_parse_filename_parses_when_tag_contains_kcniish_MR_substring():
    ident, tag, series, description = scanid.parse_filename(
        "CLZ_CMP_0000_01_01_MRABC_11_FieldMap-2mm.nii.gz")

    assert str(ident) == "CLZ_CMP_0000_01_01"
    assert tag == "MRABC"
    assert series == "11"
    assert description == "FieldMap-2mm"

    _, tag, _, _ = scanid.parse_filename(
        "CLZ_CMP_0000_01_01_ABCMR_11_FieldMap-2mm")
    assert tag == "ABCMR"

    _, tag, _, _ = scanid.parse_filename(
        "CLZ_CMP_0000_01_01_ABCMRDEF_11_FieldMap-2mm")
    assert tag == "ABCMRDEF"


def test_parse_filename_parses_when_tag_contains_kcniish_SE_substring():
    ident, tag, series, description = scanid.parse_filename(
        "CLZ_CMP_0000_01_01_SEABC_11_FieldMap-2mm.nii.gz")

    assert str(ident) == "CLZ_CMP_0000_01_01"
    assert tag == "SEABC"
    assert series == "11"
    assert description == "FieldMap-2mm"

    _, tag, _, _ = scanid.parse_filename(
        "CLZ_CMP_0000_01_01_ABCSE_11_FieldMap-2mm")
    assert tag == "ABCSE"

    _, tag, _, _ = scanid.parse_filename(
        "CLZ_CMP_0000_01_01_ABCSEDEF_11_FieldMap-2mm")
    assert tag == "ABCSEDEF"


def test_parse_filename_PHA():
    ident, tag, series, description = scanid.parse_filename(
        'DTI_CMH_PHA_ADN0001_T1_02_description.nii.gz')
    assert str(ident) == 'DTI_CMH_PHA_ADN0001'
    assert tag == 'T1'
    assert series == '02'
    assert description == 'description'


def test_parse_filename_PHA_2():
    ident, tag, series, description = scanid.parse_filename(
        'SPN01_MRC_PHA_FBN0013_RST_04_EPI-3x3x4xTR2.nii.gz')
    assert ident.study == 'SPN01'
    assert ident.site == 'MRC'
    assert ident.subject == 'PHA_FBN0013'
    assert ident.timepoint == ''
    assert ident.session == ''
    assert str(ident) == 'SPN01_MRC_PHA_FBN0013'
    assert tag == 'RST'
    assert series == '04'
    assert description == 'EPI-3x3x4xTR2'


def test_parse_filename_with_path():
    ident, tag, series, description = scanid.parse_filename(
        '/data/DTI_CMH_H001_01_01_T1_02_description.nii.gz')
    assert str(ident) == 'DTI_CMH_H001_01_01'
    assert tag == 'T1'
    assert series == '02'
    assert description == 'description'


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


def test_parse_bids_filename_missing_subject():
    with pytest.raises(scanid.ParseException):
        scanid.parse_bids_filename("ses-01_run-1_T1w")


def test_parse_bids_filename_malformed_subject():
    with pytest.raises(scanid.ParseException):
        scanid.parse_bids_filename("CMH0001_ses-01_run-1_T1w")


def test_parse_bids_filename_missing_session():
    with pytest.raises(scanid.ParseException):
        scanid.parse_bids_filename("sub-CMH0001_run-1_T1w")


def test_parse_bids_filename_malformed_session():
    with pytest.raises(scanid.ParseException):
        scanid.parse_bids_filename("sub-CMH0001_ses-_run-1_T1w")


def test_parse_bids_filename_missing_suffix():
    with pytest.raises(scanid.ParseException):
        scanid.parse_bids_filename("sub-CMH0001_ses-01_run-1.nii.gz")


def test_parse_bids_filename_missing_suffix_and_run():
    with pytest.raises(scanid.ParseException):
        scanid.parse_bids_filename("sub-CMH0001_ses-01.nii.gz")


def test_unknown_entity_does_not_get_set_as_suffix():
    with pytest.raises(scanid.ParseException):
        scanid.parse_bids_filename("sub-CMH_ses-01_new-FIELD_T1w.nii.gz")


def test_empty_entity_name_does_not_get_set_as_suffix():
    with pytest.raises(scanid.ParseException):
        scanid.parse_bids_filename("sub-CMH_ses-01_-FIELD_T1w.nii.gz")


def test_empty_entity_name_and_label_does_not_get_set_as_suffix():
    with pytest.raises(scanid.ParseException):
        scanid.parse_bids_filename("sub-CMH_ses-01_-_T1w.nii.gz")


def test_bids_file_raises_exception_when_wrong_entities_used_for_anat():
    with pytest.raises(scanid.ParseException):
        scanid.parse_bids_filename(
            "sub-CMH0001_ses-01_ce-somefield_dir-somedir"
            "_run-1_T1w.nii.gz")


def test_bids_file_raises_exception_when_wrong_entities_used_for_task():
    with pytest.raises(scanid.ParseException):
        scanid.parse_bids_filename("sub-CMH0001_ses-01_task-sometask_"
                                   "ce-somefield_run-1_T1w.nii.gz")


def test_bids_file_raises_exception_when_wrong_entities_used_for_fmap():
    with pytest.raises(scanid.ParseException):
        scanid.parse_bids_filename("sub-CMH0001_ses-01_dir-somedir_"
                                   "rec-somefield_run-1_T1w.nii.gz")


def test_optional_entities_dont_get_parsed_as_suffix():
    optional_entities = "sub-CMH0001_ses-01_{}_T1w.nii.gz"
    for entity in ['run', 'acq', 'ce', 'rec', 'echo', 'ce', 'mod', 'task']:
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
