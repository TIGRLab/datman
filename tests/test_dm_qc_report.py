import os
import unittest
import importlib
import logging
from io import TextIOBase
from random import randint

import pytest
from mock import patch, call, MagicMock
import datman.config as cfg
import datman.scan
import datman.dashboard

# Necessary to silence all logging from dm_qc_report during tests.
logging.disable(logging.CRITICAL)

# Turn off testing of integrated dashboard functions for now
datman.dashboard.dash_found = False

qc = importlib.import_module('bin.dm_qc_report')

FIXTURE = "tests/fixture_project_settings"

site_config_path = os.path.join(FIXTURE, 'site_config.yaml')
system = 'local'
study = 'STUDY'

config = cfg.config(filename=site_config_path, system=system, study=study)


class GetConfig(unittest.TestCase):
    def test_exits_gracefully_with_bad_study(self):
        with pytest.raises(SystemExit):
            qc.get_config(study="madeupcode")

    @patch('datman.config.config')
    def test_exits_gracefully_when_paths_missing_from_config(
            self, mock_config):

        with pytest.raises(SystemExit):
            mock_config.return_value.get_path.side_effect = lambda path: \
                {'dcm': '',
                 'nii': ''}[path]
            qc.get_config("STUDY")


class VerifyInputPaths(unittest.TestCase):
    def test_exits_gracefully__with_broken_input_path(self):
        bad_path = ["./fakepath/somewhere"]
        with pytest.raises(SystemExit):
            qc.verify_input_paths(bad_path)

    @patch('os.path.exists')
    def test_returns_if_paths_exist(self, mock_exists):
        mock_exists.return_value = True
        paths = ["./somepath", "/some/other/path"]
        qc.verify_input_paths(paths)


class PrepareScan(unittest.TestCase):
    def test_exits_gracefully_with_bad_subject_id(self):
        with pytest.raises(SystemExit):
            qc.prepare_scan("STUDYSITE_ID", config)

    @patch('bin.dm_qc_report.verify_input_paths')
    @patch('datman.utils')
    def test_checks_input_paths(self, mock_utils, mock_verify):
        assert mock_verify.call_count == 0
        qc.prepare_scan("STUDY_SITE_ID_01", config)
        assert mock_verify.call_count == 1

    @patch('datman.utils.remove_empty_files')
    @patch('bin.dm_qc_report.verify_input_paths')
    @patch('datman.utils.define_folder')
    def test_makes_qc_folder_if_doesnt_exist(self, mock_create, mock_verify,
                                             mock_remove):
        assert mock_create.call_count == 0
        qc.prepare_scan("STUDY_SITE_ID_01", config)
        assert mock_create.call_count == 1


class GetStandards(unittest.TestCase):
    site = "CMH"
    path = "/some/path"

    def test_returns_empty_dict_when_no_matching_standards(self):
        standards = qc.get_standards(self.path, self.site)

        assert not standards

    @patch('glob.glob')
    def test_standards_dict_holds_series_instances(self, mock_glob):
        standards = ['STUDY_CMH_9999_01_01_DTI60_05_Ax.json']
        mock_glob.return_value = standards

        results = qc.get_standards(self.path, self.site)

        assert list(results.keys()) == ['DTI60']
        assert results['DTI60'] == standards[0]

    @patch('glob.glob')
    def test_returns_expected_dict(self, mock_glob):
        DTI_standard = 'STUDY_CMH_9999_01_01_DTI60_05_Ax.json'
        T1_standard = 'STUDY_CMH_9999_01_01_T1_02_SagT1.json'
        T1_diff_site = 'STUDY_OTHER_0001_01_01_T1_07_SagT1.json'

        standards = [DTI_standard, T1_diff_site, T1_standard]
        mock_glob.return_value = standards

        standard_dict = qc.get_standards(self.path, self.site)

        actual_T1 = standard_dict['T1']
        actual_DTI = standard_dict['DTI60']

        assert sorted(standard_dict.keys()) == sorted(['T1', 'DTI60'])
        assert actual_T1 == T1_standard
        assert actual_DTI == DTI_standard

    @patch('glob.glob')
    def test_excludes_badly_named_standards(self, mock_glob):
        standards = [
            'STUDY_CMH_9999_01_01_DTI60_05_Ax.json',
            'STUDY_OTHER_0001_01_01_T1_07_SagT1.json',
            'STUDY_CMH_9999_01_01_T102SagT1.json'
        ]

        mock_glob.return_value = standards

        matched = qc.get_standards(self.path, self.site)
        expected = 'STUDY_CMH_9999_01_01_DTI60_05_Ax.json'

        assert list(matched.keys()) == ['DTI60']
        assert matched['DTI60'] == expected


class RunHeaderQC(unittest.TestCase):
    standards = './standards'
    log = './qc/subject_id/header-diff.log'

    @patch('bin.dm_qc_report.get_standards')
    @patch('datman.header_checks.construct_diffs')
    def test_doesnt_crash_with_empty_dicom_dir(self, mock_make_diffs,
                                               mock_standards):
        subject = datman.scan.Scan('STUDY_SITE_ID_01', config)
        assert subject.dicoms == []

        mock_standards.return_value = [
            'STUDY_CMH_0001_01_01_T1_02_SagT1-BRAVO.json'
        ]

        qc.run_header_qc(subject, config)
        assert mock_make_diffs.call_count == 0

    @patch('datman.scan.Scan')
    @patch('bin.dm_qc_report.get_standards')
    @patch('datman.header_checks.construct_diffs')
    def test_doesnt_crash_without_matching_standards(self, mock_make_diffs,
                                                     mock_standards,
                                                     mock_subject):
        dicom1 = datman.scan.Series('STUDY_CMH_9999_01_01_T1_02_Sag.dcm')

        mock_subject.return_value.dicoms = [dicom1]
        mock_subject.return_value.site = "CMH"
        mock_standards.return_value = {}

        qc.run_header_qc(mock_subject.return_value, config)
        assert mock_make_diffs.call_count == 0


class FMRIQC(unittest.TestCase):
    file_name = "./nii/STUDY_SITE_0001_01/" \
            "STUDY_SITE_0001_01_01_OBS_09_Ax-Observe-Task.nii"
    qc_dir = config.get_path('qc')
    qc_report = MagicMock(spec=TextIOBase)
    qc_report.name = "qc_STUDY_SITE_0001_01.html"
    output_name = os.path.join(qc_dir,
                               "STUDY_SITE_0001_01_01_OBS_09_Ax-Observe-Task")

    @patch('os.path.isfile')
    @patch('datman.utils.run')
    def test_no_commands_run_when_output_exists(self, mock_run, mock_isfile):
        mock_isfile.return_value = True

        qc.fmri_qc(self.file_name, self.qc_dir, self.qc_report)

        assert mock_run.call_count == 0

    @patch('datman.utils.run')
    def test_expected_number_of_commands_run(self, mock_run):
        qc.fmri_qc(self.file_name, self.qc_dir, self.qc_report)
        assert mock_run.call_count == 7


class AddImage(unittest.TestCase):
    qc_report = MagicMock(spec=TextIOBase)
    qc_report.name = "qc_STUDY_SITE_1000_01.html"
    image = "./qc/STUDY_SITE_1000_01/some_qc_image.png"

    def test_image_added(self):
        qc.add_image(self.qc_report, self.image)
        actual_calls = self.qc_report.write.call_args_list

        image_path = os.path.relpath(self.image,
                                     os.path.dirname(self.qc_report.name))
        expected_call = call('<img src="{}" >'.format(image_path))

        assert self.qc_report.write.call_count > 0
        # Assert at least one call to write is the expected call
        assert True if expected_call in actual_calls else False


class FindTechNotes(unittest.TestCase):
    notes = "TechNotes.pdf"
    other_pdf1 = "SomeFile.pdf"
    other_pdf2 = "otherFile.pdf"
    path = "./resources"

    def test_doesnt_crash_with_broken_path(self):

        found_file = qc.find_tech_notes(self.path)

        assert not found_file

    @patch('os.walk', autospec=True)
    def test_doesnt_crash_when_no_tech_notes_exist(self, mock_walk):
        mock_walk.return_value = self.__mock_file_system(randint(1, 10),
                                                         add_notes=False)

        found_file = qc.find_tech_notes(self.path)

        assert not found_file

    @patch('os.walk', autospec=True)
    def test_tech_notes_found_regardless_of_depth(self, mock_walk):
        mock_walk.return_value = self.__mock_file_system(randint(1, 10))

        found_file = qc.find_tech_notes(self.path)

        assert os.path.basename(found_file) == self.notes

    @patch('os.walk', autospec=True)
    def test_returns_tech_notes_when_multiple_pdfs_present(self, mock_walk):
        mock_walk.return_value = self.__mock_file_system(randint(1, 10),
                                                         add_pdf=True)

        found_file = qc.find_tech_notes(self.path)

        assert os.path.basename(found_file) == self.notes

    @patch('os.walk', autospec=True)
    def test_first_file_returned_when_multiple_pdfs_but_no_tech_notes(
            self, mock_walk):
        mock_walk.return_value = self.__mock_file_system(randint(1, 10),
                                                         add_notes=False,
                                                         add_pdf=True)

        found_file = qc.find_tech_notes(self.path)

        assert os.path.basename(found_file) == self.other_pdf1

    def __mock_file_system(self, depth, add_notes=True, add_pdf=False):
        walk_list = []
        cur_path = self.path
        file_list = ["file1.txt", "file2"]
        if add_pdf:
            file_list.extend([self.other_pdf1, self.other_pdf2])
        if add_notes:
            file_list.append(self.notes)
        for num in range(1, depth + 1):
            cur_path = cur_path + "/dir{}".format(num)
            dirs = ("dir{}".format(num + 1), )
            files = ("file1.txt", "file2")
            if num == depth:
                files = tuple(file_list)
            level = (cur_path, dirs, files)
            walk_list.append(level)
        return walk_list
