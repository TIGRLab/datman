import os
import unittest
import importlib
from random import randint

import nose.tools
from mock import patch, mock_open, call, MagicMock

FIXTURE = "tests/fixture_dm-qc-report"

qc = importlib.import_module('bin.dm-qc-report')

class GetSiteConfig(unittest.TestCase):
    config_file = os.path.join(FIXTURE, 'project_settings.yml')

    @nose.tools.raises(SystemExit)
    def test_exits_gracefully_with_broken_path(self):
        bad_path = "./doesnt-exist.yml"

        config = qc.get_site_config(bad_path)

    @nose.tools.raises(SystemExit)
    @patch('bin.dm-qc-report.SiteConfig')
    def test_exits_gracefully_when_config_paths_missing(self, mock_config):
        mock_config.return_value.paths = ['dcm', 'nii']

        config = qc.get_site_config(self.config_file)

    def test_SiteConfig_instance_returned(self):
        config = qc.get_site_config(self.config_file)

        assert isinstance(config, qc.SiteConfig)

# class FindExpectedFiles(unittest.TestCase):

# class SiteConfig(unittest.TestCase):

# class ExportInfo(unittest.TestCase):


class FMRIQC(unittest.TestCase):
    file_name = "./nii/STUDY_SITE_0001_01/" \
            "STUDY_SITE_0001_01_01_OBS_09_Ax-Observe-Task.nii"
    qc_dir = "./qc/STUDY_SITE_0001_01"
    qc_report = MagicMock(spec=file)
    output_name = qc_dir + "/STUDY_SITE_0001_01_01_OBS_09_Ax-Observe-Task"

    @patch('os.path.isfile')
    @patch('datman.utils.run')
    def test_no_commands_run_when_output_exists(self, mock_run, mock_isfile):
        mock_isfile.return_value = True

        qc.fmri_qc(self.file_name, self.qc_dir, self.qc_report)

        assert mock_run.call_count == 0

    @patch('datman.utils.run')
    def test_expected_commands_run(self, mock_run):
        qc.fmri_qc(self.file_name, self.qc_dir, self.qc_report)

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

    @patch('glob.glob', autospec=True)
    def test_doesnt_crash_with_broken_path(self, mock_glob):
        mock_glob.return_value = []

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

class GetSortedNiftis(unittest.TestCase):
    scan_path = './ID_01'
    file_list = ['notes.txt',
                 'STUDY_SITE_ID_01_01_T1_02_SagT1-BRAVO.nii',
                 'STUDY_SITE_ID_01_01_DTI60-1000_11_Ax-DTI-60.nii.gz',
                 'STUDY_SITE_ID_01_01_DTI60-1000_11_Ax-DTI-60.bvec',
                 'STUDY_SITE_0001_01_01_OBS_09_Ax-Observe-Task.nii']

    @patch('glob.glob', autospec=True)
    def test_only_niftis_returned(self, mock_glob):
        mock_glob.return_value = self.file_list

        niftis = qc.get_sorted_niftis(self.scan_path)

        assert 'notes.txt' not in niftis
        assert 'STUDY_SITE_ID_01_01_DTI60-1000_11_Ax-DTI-60.bvec' not in niftis

    @patch('glob.glob', autospec=True)
    def test_niftis_sorted_by_series_num(self, mock_glob):
        mock_glob.return_value = self.file_list

        niftis = qc.get_sorted_niftis(self.scan_path)

        expected = ['STUDY_SITE_ID_01_01_T1_02_SagT1-BRAVO.nii',
                    'STUDY_SITE_0001_01_01_OBS_09_Ax-Observe-Task.nii',
                    'STUDY_SITE_ID_01_01_DTI60-1000_11_Ax-DTI-60.nii.gz']

        assert niftis == expected

    @patch('glob.glob', autospec=True)
    def test_doesnt_crash_with_empty_nii_dir(self, mock_glob):
        mock_glob.return_value = []

        niftis = qc.get_sorted_niftis(self.scan_path)

        assert niftis == []

class QCAllScans(unittest.TestCase):
    config_file = './site_config.yaml'
    nii_dir = '/data/nii'

    @patch('os.listdir', autospec=True)
    @patch('bin.dm-qc-report.make_qc_command', autospec=True)
    @patch('bin.dm-qc-report.submit_qc_jobs', autospec=True)
    @patch('datman.utils.run', autospec=True)
    def test_subjects_queued_and_phantoms_run(self, mock_run,
            mock_submit, mock_cmd, mock_dirs):

        # Prevents a ValueError due to trying to access return and out of utils.run
        mock_run.return_value = (0, '')
        mock_dirs.return_value = ['/data/nii/STUDY_SITE_0001_01',
                                  '/data/nii/STUDY_SITE_PHA_0001',
                                  '/data/nii/STUDY_SITE_PHA_0002',
                                  '/data/nii/STUDY_SITE_0002_01']
        mock_cmd.side_effect = lambda subject, config: 'dm-qc-report.py {} ' \
                '--subject {}'.format(config, subject)

        qc.qc_all_scans(self.nii_dir, self.config_file)

        # Expected calls to submit_qc_jobs should include subjects only
        expected = ['dm-qc-report.py {} ' \
                        '--subject STUDY_SITE_0001_01'.format(self.config_file),
                    'dm-qc-report.py {} ' \
                        '--subject STUDY_SITE_0002_01'.format(self.config_file)]

        assert mock_submit.call_count == 1
        mock_submit.assert_called_once_with(expected)

        # Expected calls to datman.utils.run should include phantoms only
        phantom1 = 'dm-qc-report.py {} ' \
                    '--subject STUDY_SITE_PHA_0001'.format(self.config_file)
        phantom2 = 'dm-qc-report.py {} ' \
                    '--subject STUDY_SITE_PHA_0002'.format(self.config_file)
        expected_calls = [call(phantom1), call(phantom2)]

        assert mock_run.call_count == 2
        mock_run.assert_has_calls(expected_calls, any_order=True)

    @patch('os.listdir', autospec=True)
    @patch('bin.dm-qc-report.make_qc_command', autospec=True)
    @patch('bin.dm-qc-report.submit_qc_jobs', autospec=True)
    @patch('datman.utils.run', autospec=True)
    def test_nothing_done_when_dicom_dir_is_empty(self, mock_run, mock_submit,
            mock_cmd, mock_dirs):

        # Prevents a ValueError due to trying to access return and out of utils.run
        mock_run.return_value = (0, '')
        # mock_cmd.side_effect = lambda subject, config: 'dm-qc-report.py {} ' \
        #         '--subject {}'.format(config, subject)
        mock_dirs.return_value = []

        qc.qc_all_scans(self.nii_dir, self.config_file)

        # Expect no jobs were submitted, no commands created,
        # and no calls to utils.run
        assert mock_run.call_count == 0
        assert mock_submit.call_count == 0
        assert mock_cmd.call_count == 0

class SubmitQCJobs(unittest.TestCase):
    time = '19001231-23:59:59'

    @patch('time.strftime')
    @patch('datman.utils.run')
    def test_expected_command_run_in_shell(self, mock_run, mock_time):
        mock_time.return_value = self.time
        # Prevents a ValueError from trying to access return and out of utils.run
        mock_run.return_value = (0, '')

        commands = ['dm-qc-report.py config_file.yaml --subject STUDY_SITE_ID_01']
        qc.submit_qc_jobs(commands)

        job_name = 'qc_report_{}_0'.format(self.time)
        expected = 'echo {} | qsub -V -q main.q -o ' \
                '/tmp/{job}.log -e /tmp/{job}.err -N {job}'.format(commands[0],
                        job=job_name)

        assert mock_run.call_count == 1
        print("Test will fail if the format of the argument string changes."\
              " If the new code is correct, update this test to make it pass "\
              " with the new format.")
        mock_run.assert_called_once_with(expected)

class AddHeaderQC(unittest.TestCase):
    nifti_path = "./some_dir/STUDY_CAMH_0001_01/" \
            "STUDY_CAMH_0001_01_01_T1_02_SagT1-BRAVO.nii"

    def test_doesnt_crash_without_header_diff_log(self):
        mock_report = MagicMock(spec=file)

        qc.add_header_qc(self.nifti_path, mock_report, "./some_log.log")

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

            qc.add_header_qc(self.nifti_path, mock_report, mock_log)

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

            qc.add_header_qc(self.nifti_path, mock_report, mock_log)

            # Expected that log is read and report IS written to at least once.
            mock_stream.assert_called_once_with(mock_log, 'r')
            assert mock_report.write.called

class RunHeaderQC(unittest.TestCase):
    dicoms = './dicoms/subject_id'
    standards = './standards'
    log = './qc/subject_id/header-diff.log'

    @patch('glob.glob')
    @patch('datman.utils.run')
    def test_doesnt_crash_with_empty_dicom_dir(self, mock_run, mock_glob):
        mock_glob.side_effect = lambda path: {
             './dicoms/subject_id/*': [],
             './standards/*': ['STUDY_CAMH_0001_01_01_T1_02_SagT1-BRAVO.dcm']
             }[path]

        qc.run_header_qc(self.dicoms, self.standards, self.log)
        assert mock_run.call_count == 0

    @patch('glob.glob')
    @patch('datman.utils.run')
    def test_doesnt_crash_without_matching_standards(self, mock_run, mock_glob):
        mock_glob.side_effect = lambda path: {
            './dicoms/subject_id/*': ['./dicoms/subject_id/' \
                        'STUDY_SITE1_0002_01_01_OBS_09_Ax-Observe-Task.dcm'],
            './standards/*': ['./standards/' \
                        'STUDY_CAMH_0001_01_01_T1_02_SagT1-BRAVO.dcm']
            }[path]

        qc.run_header_qc(self.dicoms, self.standards, self.log)
        assert mock_run.call_count == 0

    @patch('glob.glob', autospec=True)
    @patch('datman.utils.run', autospec=True)
    def test_expected_qcmon_call_made(self, mock_run, mock_glob):
        mock_glob.side_effect = lambda path: {
            './dicoms/subject_id/*': ['./dicoms/subject_id/' \
                        'STUDY_CAMH_0001_01_01_OBS_09_Ax-Observe-Task.dcm',
                    './dicoms/subject_id/' \
                        'STUDY_CAMH_0001_01_01_T1_02_SagT1-BRAVO.dcm'],
            './standards/*': ['./standards/' \
                    'STUDY_CAMH_9999_01_01_T1_99_SagT1-BRAVO.dcm']
            }[path]

        qc.run_header_qc(self.dicoms, self.standards, self.log)

        matched_dicom = './dicoms/subject_id/' \
                'STUDY_CAMH_0001_01_01_T1_02_SagT1-BRAVO.dcm'
        matched_standard = './standards/' \
                'STUDY_CAMH_9999_01_01_T1_99_SagT1-BRAVO.dcm'

        expected = 'qc-headers {} {} {}'.format(matched_dicom,
                matched_standard, self.log)

        mock_run.assert_called_once_with(expected)

class AddReportToChecklist(unittest.TestCase):
    checklist = "./checklist.csv"
    checklist_data = ["qc_subject1.html\n", "qc_subject2.html   signed-off\n",
                      "qc_subject4.pdf\n", "qc_subject5\n"]

    def test_list_unchanged_with_empty_report_name(self):
        report = ""
        call_count, arg_list, _ = self.__mock_add_report(report)

        assert call_count == 0
        assert arg_list == []

    def test_list_updated_with_new_report(self):
        report = "qc_subject3.html"
        call_count, arg_list, checklist_mock = self.__mock_add_report(report)

        assert call_count == 2
        assert arg_list == [call(self.checklist, 'r'), call(self.checklist, 'a')]
        checklist_mock().write.assert_called_once_with(report + "\n")

    def test_list_not_updated_with_repeat_report(self):
        report = "qc_subject1.html"
        call_count, arg_list, checklist_mock = self.__mock_add_report(report)

        assert call_count == 1
        assert arg_list == [call(self.checklist, 'r')]
        assert not checklist_mock().write.called

        # Expect that entries in report with 2+ columns not repeated.
        qced_report = "qc_subject2.html"
        call_count, arg_list, checklist_mock = self.__mock_add_report(report)

        assert call_count == 1
        assert arg_list == [call(self.checklist, 'r')]
        assert not checklist_mock().write.called

    def test_list_not_updated_with_same_report_with_new_extension(self):
        report = "qc_subject5.html"
        call_count, arg_list, checklist_mock = self.__mock_add_report(report)

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
