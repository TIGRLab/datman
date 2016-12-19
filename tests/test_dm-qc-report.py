import os
import unittest
import importlib
import logging
from random import randint

import nose.tools
from mock import patch, mock_open, call, MagicMock

import datman.config as cfg
import datman.scan

# Necessary to silence all logging from dm-qc-report during tests.
logging.disable(logging.CRITICAL)

qc = importlib.import_module('bin.dm-qc-report')

FIXTURE = "tests/fixture_project_settings"

site_config_path = os.path.join(FIXTURE, 'site_config.yaml')
system = 'local'
study = 'STUDY'

config = cfg.config(filename=site_config_path, system=system, study=study)

class GetConfig(unittest.TestCase):
    @nose.tools.raises(SystemExit)
    def test_exits_gracefully_with_bad_study(self):
        config = qc.get_config(study="madeupcode")

    @nose.tools.raises(SystemExit)
    @patch('datman.config.config')
    def test_exits_gracefully_when_paths_missing_from_config(self, mock_config):
        mock_config.return_value.get_path.side_effect = lambda path: {'dcm': '',
                'nii': ''}[path]
        config = qc.get_config("STUDY")

class VerifyInputPaths(unittest.TestCase):

    @nose.tools.raises(SystemExit)
    def test_exits_gracefully__with_broken_input_path(self):
        bad_path = ["./fakepath/somewhere"]
        qc.verify_input_paths(bad_path)

    @patch('os.path.exists')
    def test_returns_if_paths_exist(self, mock_exists):
        mock_exists.return_value = True
        paths = ["./somepath", "/some/other/path"]
        qc.verify_input_paths(paths)

class PrepareScan(unittest.TestCase):

    @nose.tools.raises(SystemExit)
    def test_exits_gracefully_with_bad_subject_id(self):
        qc.prepare_scan("STUDYSITE_ID", config)

    @patch('bin.dm-qc-report.verify_input_paths')
    @patch('datman.utils')
    def test_checks_input_paths(self, mock_utils, mock_verify):
        assert mock_verify.call_count == 0
        qc.prepare_scan("STUDY_SITE_ID_01", config)
        assert mock_verify.call_count == 1

    @patch('datman.utils.remove_empty_files')
    @patch('bin.dm-qc-report.verify_input_paths')
    @patch('datman.utils.define_folder')
    def test_makes_qc_folder_if_doesnt_exist(self, mock_create, mock_verify,
            mock_remove):
        assert mock_create.call_count == 0
        scan = qc.prepare_scan("STUDY_SITE_ID_01", config)
        assert mock_create.call_count == 1

class GetStandards(unittest.TestCase):
    site = "CAMH"
    path = "/some/path"

    def test_returns_empty_dict_when_no_matching_standards(self):
        standards = qc.get_standards(self.path, self.site)

        assert not standards

    @patch('glob.glob')
    def test_standards_dict_holds_series_instances(self, mock_glob):
        standards = ['STUDY_CAMH_9999_01_01_DTI60_05_Ax.dcm']
        mock_glob.return_value = standards

        results = qc.get_standards(self.path, self.site)

        assert results.keys() == ['DTI60']
        assert isinstance(results['DTI60'], datman.scan.Series)

    @patch('glob.glob')
    def test_returns_expected_dict(self, mock_glob):
        DTI_standard = 'STUDY_CAMH_9999_01_01_DTI60_05_Ax.dcm'
        T1_standard = 'STUDY_CAMH_9999_01_01_T1_02_SagT1.dcm'
        T1_diff_site = 'STUDY_OTHER_0001_01_01_T1_07_SagT1.dcm'

        standards = [DTI_standard,
                     T1_diff_site,
                     T1_standard]
        mock_glob.return_value = standards

        standard_dict = qc.get_standards(self.path, self.site)

        actual_T1 = standard_dict['T1'].file_name
        actual_DTI = standard_dict['DTI60'].file_name

        assert sorted(standard_dict.keys()) == sorted(['T1', 'DTI60'])
        assert  actual_T1 == T1_standard
        assert  actual_DTI == DTI_standard

    @patch('glob.glob')
    def test_excludes_badly_named_standards(self, mock_glob):
        standards = ['STUDY_CAMH_9999_01_01_DTI60_05_Ax.dcm',
                     'STUDY_OTHER_0001_01_01_T1_07_SagT1.dcm',
                     'STUDY_CAMH_9999_01_01_T102SagT1.dcm']

        mock_glob.return_value = standards

        matched = qc.get_standards(self.path, self.site)
        expected = 'STUDY_CAMH_9999_01_01_DTI60_05_Ax.dcm'

        assert matched.keys() == ['DTI60']
        assert matched['DTI60'].file_name == expected

class RunHeaderQC(unittest.TestCase):
    standards = './standards'
    log = './qc/subject_id/header-diff.log'

    @patch('bin.dm-qc-report.get_standards')
    @patch('datman.utils.run')
    def test_doesnt_crash_with_empty_dicom_dir(self, mock_run, mock_standards):
        subject = datman.scan.Scan('STUDY_SITE_ID_01', config)
        assert subject.dicoms == []

        mock_standards.return_value = ['STUDY_CAMH_0001_01_01_T1_02_SagT1-BRAVO.dcm']

        qc.run_header_qc(subject, self.standards, self.log)
        assert mock_run.call_count == 0

    @patch('datman.scan.Scan')
    @patch('bin.dm-qc-report.get_standards')
    @patch('datman.utils.run')
    def test_doesnt_crash_without_matching_standards(self, mock_run,
            mock_standards, mock_subject):
        dicom1 = datman.scan.Series('STUDY_CAMH_9999_01_01_T1_02_Sag.dcm')

        mock_subject.return_value.dicoms = [dicom1]
        mock_standards.return_value = {}

        qc.run_header_qc(mock_subject.return_value, self.standards, self.log)
        assert mock_run.call_count == 0

    @patch('datman.scan.Scan')
    @patch('bin.dm-qc-report.get_standards')
    @patch('datman.utils.run', autospec=True)
    def test_expected_qcmon_call_made(self, mock_run, mock_standards, mock_subject):
        dicom1 = datman.scan.Series('./dicoms/subject_id/' \
                    'STUDY_CAMH_0001_01_01_OBS_09_Ax-Observe-Task.dcm')
        dicom2 = datman.scan.Series('./dicoms/subject_id/' \
                    'STUDY_CAMH_0001_01_01_T1_02_SagT1-BRAVO.dcm')

        mock_subject.return_value.dicoms = [dicom1, dicom2]

        standard = datman.scan.Series('./standards/STUDY_CAMH_9999_01'\
                    '_01_T1_99_SagT1-BRAVO.dcm')
        mock_standards.return_value = {'T1': standard}

        qc.run_header_qc(mock_subject.return_value, self.standards, self.log)

        expected = 'qc-headers {} {} {}'.format(dicom2.path, standard.path,
                self.log)

        mock_run.assert_called_once_with(expected)

# # class FindExpectedFiles(unittest.TestCase):
#
class FMRIQC(unittest.TestCase):
    file_name = "./nii/STUDY_SITE_0001_01/" \
            "STUDY_SITE_0001_01_01_OBS_09_Ax-Observe-Task.nii"
    qc_dir = config.get_path('qc')
    qc_report = MagicMock(spec=file)
    output_name = os.path.join(qc_dir,
            "STUDY_SITE_0001_01_01_OBS_09_Ax-Observe-Task")

    @patch('os.path.isfile')
    @patch('datman.utils.run')
    def test_no_commands_run_when_output_exists(self, mock_run, mock_isfile):
        mock_isfile.return_value = True

        qc.fmri_qc(self.file_name, self.qc_dir, self.qc_report)

        assert mock_run.call_count == 0

    @patch('datman.utils.run')
    def test_expected_commands_run(self, mock_run):
        scan_length = 'qc-scanlength {} {}'.format(self.file_name,
                self.output_name + '_scanlengths.csv')
        fmri = 'qc-fmri {} {}'.format(self.file_name,
                self.output_name)

        slicer_cmd = 'slicer {} -S {} {} {}'
        slicer1 = slicer_cmd.format(self.output_name +
                '_sfnr.nii.gz', 2, 1600, self.output_name + '_sfnr.png')
        slicer2 = slicer_cmd.format(self.output_name + '_corr.nii.gz',
                 2, 1600, self.output_name + '_corr.png')
        slicer3 = slicer_cmd.format(self.file_name,  2, 1600,
                self.output_name + '_raw.png')

        qc.fmri_qc(self.file_name, self.qc_dir, self.qc_report)

        expected_calls = [call(scan_length), call(fmri), call(slicer1),
                call(slicer2), call(slicer3)]

        assert mock_run.call_count == 5
        print("Test will fail if format of the argument string changes."\
              " If the new code is correct, update this test to make it pass "\
              " with the new format.")
        mock_run.assert_has_calls(expected_calls, any_order=True)

class AddImage(unittest.TestCase):
    qc_report = MagicMock(spec=file)
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

    def __mock_file_system(self, depth, add_notes=True):
        walk_list = []
        cur_path = self.path
        for num in xrange(1, depth + 1):
            cur_path = cur_path + "/dir{}".format(num)
            dirs = ("dir{}".format(num + 1),)
            files = ("file1.txt", "file2")
            if add_notes and num == depth:
                files = ("file1.txt", "file2", self.notes)
            level = (cur_path, dirs, files)
            walk_list.append(level)
        return walk_list

class AddHeaderQC(unittest.TestCase):
    nifti = datman.scan.Series("./some_dir/STUDY_CAMH_0001_01/" \
            "STUDY_CAMH_0001_01_01_T1_02_SagT1-BRAVO.nii")

    def test_doesnt_crash_without_header_diff_log(self):
        mock_report = MagicMock(spec=file)

        qc.add_header_qc(self.nifti, mock_report, "./some_log.log")

        # Expected that no changes are made to the report
        assert not mock_report.write.called

    def test_no_report_changes_without_matching_header_diff_log_lines(self):
        # Line 1: different series, Line 2: wrong subject ID
        log_lines = ["/path1/STUDY_CAMH_0001_01_01_OBS_09_Ax-Observe-Task.nii " \
                " some list of differences\n",
                "/path2/STUDY_CAMH_9999_01_01_T1_02_SagT1-BRAVO.nii " \
                " another list of differences\n"]

        mock_report = MagicMock(spec=file)
        mock_log = mock_open(read_data=log_lines)

        with patch("__builtin__.open", mock_log) as mock_stream:
            # This line is needed to get log contents from read_line
            mock_stream.return_value.readlines.return_value = log_lines

            qc.add_header_qc(self.nifti, mock_report, mock_log)

            # Expected that log is read, but report is NOT written to
            mock_stream.assert_called_once_with(mock_log, 'r')
            assert not mock_report.write.called

    def test_report_updated_when_matching_header_diff_log_lines(self):
        # Line 1: Wrong series, Line 2: matching ID, should be written.
        log_lines = ["/path1/STUDY_CAMH_0001_01_01_OBS_09_Ax-Observe-Task.nii " \
                " some list of differences\n",
                "/path2/STUDY_CAMH_0001_01_01_T1_02_SagT1-BRAVO.nii " \
                " another list of differences\n"]

        mock_report = MagicMock(spec=file)
        mock_log = mock_open(read_data=log_lines)

        with patch("__builtin__.open", mock_log) as mock_stream:
            # This line is needed to get log contents from read_line
            mock_stream.return_value.readlines.return_value = log_lines

            qc.add_header_qc(self.nifti, mock_report, mock_log)

            # Expected that log is read and report IS written to at least once.
            mock_stream.assert_called_once_with(mock_log, 'r')
            assert mock_report.write.called

class AddReportToChecklist(unittest.TestCase):
    path = "/some/path/"
    checklist = "./checklist.csv"
    checklist_data = ["qc_subject1.html\n", "qc_subject2.html   signed-off\n",
                      "qc_subject4.pdf\n", "qc_subject5\n"]

    def test_list_unchanged_with_empty_report_path(self):
        report = ""
        call_count, arg_list, _ = self.__mock_add_report(report)

        assert call_count == 0
        assert arg_list == []

    def test_list_updated_with_new_report(self):
        report = "qc_subject3.html"
        call_count, arg_list, checklist_mock = self.__mock_add_report(self.path
                + report)

        assert call_count == 2
        assert arg_list == [call(self.checklist, 'r'), call(self.checklist, 'a')]
        checklist_mock().write.assert_called_once_with(report + "\n")

    def test_list_not_updated_with_repeat_report(self):
        report = "/path/qc_subject1.html"
        call_count, arg_list, checklist_mock = self.__mock_add_report(self.path +
                report)

        assert call_count == 1
        assert arg_list == [call(self.checklist, 'r')]
        assert not checklist_mock().write.called

        # Expect that entries in report with 2+ columns not repeated.
        qced_report = "/path/qc_subject2.html"
        call_count, arg_list, checklist_mock = self.__mock_add_report(self.path +
                report)

        assert call_count == 1
        assert arg_list == [call(self.checklist, 'r')]
        assert not checklist_mock().write.called

    def test_list_not_updated_with_same_report_with_new_extension(self):
        report = "/path/qc_subject5.html"
        call_count, arg_list, checklist_mock = self.__mock_add_report(self.path +
                report)

        assert call_count == 1
        assert arg_list == [call(self.checklist, 'r')]
        assert not checklist_mock().write.called

    def __mock_add_report(self, report):
        # Checklist not defined as an attribute so that calls don't have to be
        # reset for each test.
        checklist_mock = mock_open(read_data=self.checklist_data)
        with patch("__builtin__.open", checklist_mock) as mock_file:
            # This line is needed because mock_open wont allow iteration
            # over a file handler otherwise
            mock_file.return_value.__iter__.return_value = self.checklist_data
            qc.add_report_to_checklist(report, self.checklist)

            return mock_file.call_count, mock_file.call_args_list, checklist_mock
