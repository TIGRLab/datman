import os
import unittest

import pytest
from mock import patch

import datman.config as cfg
import datman.scan

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixture_project_settings/")


site_config = os.path.join(FIXTURE + "site_config.yaml")
system = 'local'
study = 'STUDY'


class TestSeries(unittest.TestCase):
    good_name = "/somepath/STUDY_SITE_9999_01_01_T1_03_SagT1Bravo-09mm.nii.gz"
    bad_name = "/somepath/STUDYSITE_9999_T1_03_SagT1Bravo-09mm.nii.gz"

    def test_raises_parse_exception_with_bad_file_name(self):

        with pytest.raises(datman.scanid.ParseException):
            datman.scan.Series(self.bad_name)

    def test_creates_series_for_well_named_file(self):
        series = datman.scan.Series(self.good_name)

        assert series is not None
        assert series.path == self.good_name
        assert series.ext == '.nii.gz'
        assert series.description == 'SagT1Bravo-09mm'
        assert series.full_id == 'STUDY_SITE_9999_01'


class TestScan(unittest.TestCase):
    good_name = "STUDY_CMH_9999_01"
    bad_name = "STUDYCMH_9999"
    phantom = "STUDY_CMH_PHA_XXX9999"
    config = cfg.config(filename=site_config, system=system, study=study)

    def test_raises_parse_exception_with_bad_subject_id(self):
        with pytest.raises(datman.scanid.ParseException):
            datman.scan.Scan(self.bad_name, self.config)

    def test_makes_scan_instance_for_id_without_session(self):
        subject = datman.scan.Scan(self.good_name, self.config)

        assert subject is not None
        # Check that the missing session was set to the default
        assert subject.session == '01'

    def test_makes_scan_instance_for_phantom(self):
        subject = datman.scan.Scan(self.phantom, self.config)

        assert subject is not None
        assert subject.full_id == self.phantom

    def test_is_phantom_sets_correctly(self):
        subject = datman.scan.Scan(self.good_name, self.config)
        phantom = datman.scan.Scan(self.phantom, self.config)

        assert not subject.is_phantom
        assert phantom.is_phantom

    @patch('os.path.exists')
    def test_resources_paths_uses_full_id_plus_session(self, mock_exists):
        mock_exists.return_value = True
        subject = datman.scan.Scan(self.good_name, self.config)

        expected_path = self.config.get_path('resources') + \
            "STUDY_CMH_9999_01_01"
        assert subject.resource_path == expected_path

    def test_returns_expected_subject_paths(self):
        subject = datman.scan.Scan(self.good_name, self.config)

        expected_nii = self.config.get_path('nii') + self.good_name
        expected_dcm = self.config.get_path('dcm') + self.good_name
        expected_qc = self.config.get_path('qc') + self.good_name

        assert subject.nii_path == expected_nii
        assert subject.dcm_path == expected_dcm
        assert subject.qc_path == expected_qc

    def test_niftis_and_dicoms_set_to_empty_list_when_broken_path(self):
        subject = datman.scan.Scan(self.good_name, self.config)

        assert subject.niftis == []
        assert subject.dicoms == []

    @patch('glob.glob')
    def test_niftis_with_either_extension_type_found(self, mock_glob):
        simple_ext = "{}_01_T1_02_SagT1-BRAVO.nii".format(self.good_name)
        complex_ext = "{}_01_DTI60-1000_05_Ax-DTI-60.nii.gz".format(
            self.good_name)
        wrong_ext = "{}_01_DTI60-1000_05_Ax-DTI-60.bvec".format(self.good_name)

        nii_list = [simple_ext, complex_ext, wrong_ext]
        mock_glob.return_value = nii_list

        subject = datman.scan.Scan(self.good_name, self.config)

        found_niftis = [series.path for series in subject.niftis]
        expected = [simple_ext, complex_ext]

        assert sorted(found_niftis) == sorted(expected)

    @patch('glob.glob')
    def test_subject_series_with_nondatman_name_causes_parse_exception(
            self,
            mock_glob):
        well_named = "{}_01_T1_02_SagT1-BRAVO.nii".format(self.good_name)
        badly_named1 = "{}_01_DTI60-1000_05_Ax-DTI-60.nii".format(
            self.bad_name)
        badly_named2 = "{}_01_T2_07.nii".format(self.good_name)

        nii_list = [well_named, badly_named1, badly_named2]
        mock_glob.return_value = nii_list

        with pytest.raises(datman.scanid.ParseException):
            datman.scan.Scan(self.good_name, self.config)

    @patch('glob.glob')
    def test_dicoms_lists_only_dicom_files(self, mock_glob):
        dicom1 = "{}_01_T1_02_SagT1-BRAVO.dcm".format(self.good_name)
        dicom2 = "{}_01_DTI60-1000_05_Ax-DTI-60.dcm".format(self.good_name)
        nifti = "{}_01_T1_02_SagT1-BRAVO.nii".format(self.good_name)
        wrong_ext = "{}_01_DTI60-1000_05_Ax-DTI-60.bvec".format(self.good_name)

        dcm_list = [dicom1, nifti, dicom2, wrong_ext]
        mock_glob.return_value = dcm_list

        subject = datman.scan.Scan(self.good_name, self.config)

        found_dicoms = [series.path for series in subject.dicoms]
        expected = [dicom1, dicom2]

        assert sorted(found_dicoms) == sorted(expected)

    @patch('glob.glob')
    def test_nii_tags_lists_all_tags(self, mock_glob):
        T1 = "STUDY_CAMH_9999_01_01_T1_02_SagT1-BRAVO.nii"
        DTI = "STUDY_CAMH_9999_01_01_DTI60-1000_05_Ax-DTI-60.nii"

        mock_glob.return_value = [T1, DTI]

        subject = datman.scan.Scan(self.good_name, self.config)

        assert sorted(subject.nii_tags) == sorted(['T1', 'DTI60-1000'])
        assert subject.dcm_tags == []

    @patch('glob.glob')
    def test_dcm_tags_lists_all_tags(self, mock_glob):
        T1 = "STUDY_CAMH_9999_01_01_T1_02_SagT1-BRAVO.dcm"
        DTI = "STUDY_CAMH_9999_01_01_DTI60-1000_05_Ax-DTI-60.dcm"

        mock_glob.return_value = [T1, DTI]

        subject = datman.scan.Scan(self.good_name, self.config)

        assert sorted(subject.dcm_tags) == sorted(['T1', 'DTI60-1000'])
        assert subject.nii_tags == []

    @patch('glob.glob')
    def test_get_tagged_nii_finds_all_matching_series(self, mock_glob):
        T1_1 = "STUDY_CAMH_9999_01_01_T1_02_SagT1-BRAVO.nii"
        T1_2 = "STUDY_CAMH_9999_01_01_T1_03_SagT1-BRAVO.nii.gz"
        DTI = "STUDY_CAMH_9999_01_01_DTI_05_Ax-DTI-60.nii"

        mock_glob.return_value = [T1_1, DTI, T1_2]

        subject = datman.scan.Scan(self.good_name, self.config)

        actual_T1s = [series.path for series in subject.get_tagged_nii('T1')]
        expected = [T1_1, T1_2]
        assert sorted(actual_T1s) == sorted(expected)

        actual_DTIs = [series.path for series in subject.get_tagged_nii('DTI')]
        expected = [DTI]
        assert actual_DTIs == expected

    @patch('glob.glob')
    def test_get_tagged_dcm_finds_all_matching_series(self, mock_glob):
        T1_1 = "STUDY_CAMH_9999_01_01_T1_02_SagT1-BRAVO.dcm"
        T1_2 = "STUDY_CAMH_9999_01_01_T1_03_SagT1-BRAVO.dcm"
        DTI = "STUDY_CAMH_9999_01_01_DTI_05_Ax-DTI-60.dcm"

        mock_glob.return_value = [T1_1, DTI, T1_2]

        subject = datman.scan.Scan(self.good_name, self.config)

        actual_T1s = [series.path for series in subject.get_tagged_dcm('T1')]
        expected = [T1_1, T1_2]
        assert sorted(actual_T1s) == sorted(expected)

        actual_DTIs = [series.path for series in subject.get_tagged_dcm('DTI')]
        expected = [DTI]
        assert actual_DTIs == expected

    @patch('glob.glob')
    def test_get_tagged_X_returns_empty_list_when_no_tag_files(self,
                                                               mock_glob):
        nifti = "STUDY_CAMH_9999_01_01_T1_03_SagT1-BRAVO.nii.gz"
        dicom = "STUDY_CAMH_9999_01_01_DTI_05_Ax-DTI-60.dcm"

        mock_glob.return_value = [nifti, dicom]

        subject = datman.scan.Scan(self.good_name, self.config)

        assert subject.get_tagged_nii('DTI') == []
        assert subject.get_tagged_dcm('T1') == []
