import unittest
import logging
import datetime

import pytest
from mock import patch

import datman.fs_log_scraper as scraper

logging.disable(logging.CRITICAL)


class TestFSLog(unittest.TestCase):

    fs_path = '/some/path/freesurfer/subject_id'
    FS_date_format = '%a %b %d %X %Z %Y'

    @patch('datman.fs_log_scraper.FSLog.read_log')
    @patch('glob.glob')
    def test_sets_running_status_when_subject_running_less_than_24h(
            self, mock_glob, mock_read_log):
        mock_glob.return_value = ['/some/path/IsRunning.lh+rh']
        # Time zone isnt taken into account when time is compared, but required
        # by the date parsing code
        now = datetime.datetime.now(tz=EST()).strftime(self.FS_date_format)
        mock_read_log.return_value = ['DATE {}'.format(now)]

        my_log = scraper.FSLog(self.fs_path)

        assert my_log.status == scraper.FSLog._RUNNING

    @patch('datman.fs_log_scraper.FSLog.read_log')
    @patch('glob.glob')
    def test_sets_status_timedout_when_subject_running_more_than_24h(
            self, mock_glob, mock_read_log):
        mock_glob.return_value = ['/some/path/IsRunning.lh+rh']
        two_days_ago = datetime.datetime.now(tz=EST()) - datetime.timedelta(2)
        mock_read_log.return_value = [
            'DATE {}'.format(two_days_ago.strftime(self.FS_date_format))
        ]

        my_log = scraper.FSLog(self.fs_path)

        assert my_log.status == scraper.FSLog._TIMEDOUT.format(
            'IsRunning.lh+rh')

    @patch('glob.glob')
    def test_sets_status_maybe_halted_when_IsRunning_log_unreadable(
            self, mock_glob):
        # Return path to nonexistent file
        mock_glob.return_value = ["/some/path/IsRunning.lh+rh"]

        my_log = scraper.FSLog(self.fs_path)

        assert my_log.status == scraper.FSLog._MAYBE_HALTED

    @patch('os.path.exists')
    def test_sets_status_error_when_recon_error_present(self, mock_exists):
        error_log = self.fs_path + '/scripts/recon-all.error'
        mock_exists.side_effect = lambda x: True if x == error_log else False

        my_log = scraper.FSLog(self.fs_path)

        assert my_log.status == scraper.FSLog._ERROR

    @patch('os.path.exists')
    def test_sets_status_to_empty_when_recon_done_present(self, mock_exists):
        recon_done = self.fs_path + '/scripts/recon-all.done'
        mock_exists.side_effect = lambda x: True if x == recon_done else False

        my_log = scraper.FSLog(self.fs_path)

        assert my_log.status == ''

    @patch('datman.fs_log_scraper.FSLog.read_log')
    @patch('os.path.exists')
    def test_values_set_to_empty_when_recon_done_unreadable(
            self, mock_exists, mock_read_log):
        recon_done = self.fs_path + '/scripts/recon-all.done'
        mock_exists.side_effect = lambda x: True if x == recon_done else False
        mock_read_log.return_value = {}

        my_log = scraper.FSLog(self.fs_path)

        assert my_log.status == ''
        # Subject will be set to basename of the freesurfer path if
        # recon-all.done isnt present/is unreadable
        # assert my_log.subject == ''
        assert my_log.start == ''
        assert my_log.end == ''
        assert my_log.kernel == ''
        assert my_log.args == ''
        assert my_log.nii_inputs == ''

    def test_args_excludes_subject_specific_arguments(self):
        cmd_args = '-all -qcache -notal-check -parallel -subjid SOMEID12345 ' \
            + '-i /some/path/nii_input1.nii.gz ' \
            + '-T2 /some/path/nii_input2.nii.gz'
        relevant_args = ['-all', '-qcache', '-notal-check', '-parallel']
        expected = " ".join(sorted(relevant_args))

        args = scraper.FSLog.get_args(cmd_args)

        assert args == expected

    def test_args_doesnt_separate_values_associated_with_an_arg(self):
        cmd_args = '-parallel -nuiterations 8 -qcache -subjid SOMEID12345 ' \
            + '-i /some/path/item1.nii.gz'
        relevant_args = ['-parallel', '-nuiterations 8', '-qcache']
        expected = " ".join(sorted(relevant_args))

        args = scraper.FSLog.get_args(cmd_args)

        assert args == expected

    def test_nii_inputs_includes_T2_inputs(self):
        t1 = '/some/path/nii_input1.nii.gz'
        t2 = 'some/path/nii_input2.nii.gz'
        cmd_args = '-all -qcache -notal-check -nuiterations 8 ' \
                   + '-subjid SOMEID12345' \
                   + '-i {} -T2 {}'.format(t1, t2)

        nii_inputs = scraper.FSLog.get_niftis(cmd_args)

        assert t2 in nii_inputs

    def test_nii_inputs_doesnt_include_args(self):
        t1 = '/some/path/nii_input1.nii.gz'
        t2 = 'some/path/nii_input2.nii.gz'
        cmd_args = '-all -qcache -notal-check -nuiterations 8 ' \
                   + '-subjid SOMEID12345' \
                   + '-i {} -T2 {}'.format(t1, t2)

        nii_inputs = scraper.FSLog.get_niftis(cmd_args)

        for arg in [
                '-all', '-qcache', '-notal-check', '-nuiterations 8',
                '-subjid SOMEID12345'
        ]:
            assert arg not in nii_inputs


class TestChooseStandardSub(unittest.TestCase):
    def test_chooses_subject_without_status_set(self):
        class LogStub(object):
            def __init__(self, subid, status):
                self.subject = subid
                self.status = status

        subject1 = LogStub('SUBJECT1111', 'Exited')
        subject2 = LogStub('SUBJECT2222', '')
        subject3 = LogStub('SUBJECT3333', 'Still Running')

        standard_sub = scraper.choose_standard_sub(
            [subject1, subject2, subject3])

        assert standard_sub.subject == subject2.subject

    def test_raises_exception_if_no_subjects_have_completed_pipeline(self):
        class LogStub(object):
            def __init__(self, subid, status):
                self.subject = subid
                self.status = status

        subject1 = LogStub('SUBJECT1', 'Exited with error')
        subject2 = LogStub('SUBJECT2', 'Still Running')

        with pytest.raises(Exception):
            scraper.choose_standard_sub([subject1, subject2])


class TestVerifyStandards(unittest.TestCase):
    def test_raises_keyerror_when_expected_key_missing(self):
        standards_dict = {
            'build': 'expected_build here',
            'kernel': 'expected kernel here'
        }
        expected_keys = ['build', 'kernel', 'args']

        with pytest.raises(KeyError):
            scraper.verify_standards(standards_dict, expected_keys)

    def test_ignores_unexpected_keys(self):
        standards_dict = {
            'build': 'build goes here',
            'some_key': 'something else goes here'
        }
        expected_keys = ['build']

        scraper.verify_standards(standards_dict, expected_keys)

        # Function always passes if extra key doesnt cause exception
        assert True


class CheckDiff(unittest.TestCase):
    def test_no_diffs_returns_empty_string(self):
        log_field = 'kernel1234'
        standard_field = 'kernel1234'

        diffs = scraper.check_diff(log_field, standard_field)

        assert diffs == ''

    def test_order_of_args_string_doesnt_fool_comparison(self):
        subject_args = '-parallel -notal-check -qcache'
        standard_args = '-qcache -parallel -notal-check'

        diffs = scraper.check_diff(subject_args, standard_args)

        assert not diffs

    def test_returned_differences_are_string(self):
        subject_args = 'kernel1'
        standard_args = 'kernel2'

        diffs = scraper.check_diff(subject_args, standard_args)

        assert isinstance(diffs, str)


# A timezone class, to fill in the expected (but not used) datetime timezone
class EST(datetime.tzinfo):
    def utcoffset(self, dt):
        return datetime.timedelta(0)

    def tzname(self, dt):
        return "EDT"

    def dst(self, dt):
        return datetime.timedelta(0)
