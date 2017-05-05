import unittest
import logging

import datman.fs_log_scraper as scraper

logging.disable(logging.CRITICAL)

class TestFSLog(unittest.TestCase):

    def test_sets_running_status_when_subject_running_less_than_24h(self):
        return False

    def test_sets_status_timedout_when_subject_running_more_than_24h(self):
        return False

    def test_sets_status_maybe_halted_when_IsRunning_log_unreadable(self):
        return False

    def test_sets_status_error_when_recon_error_present(self):
        return False

    def test_sets_status_to_empty_when_recon_done_present(self):
        return False

    def test_values_set_to_empty_when_recon_done_unreadable(self):
        return False

    def test_args_excludes_uninteresting_inputs(self):
        return False

    def test_args_doesnt_exclude_values_associated_with_an_arg(self):
        return False

    def test_nii_inputs_includes_T2_inputs(self):
        return False

    def test_nii_inputs_doesnt_include_args(self):
        return False

class TestVerifyStandards(unittest.TestCase):

    def test_raises_keyerror_when_expected_key_missing(self):
        return False

    def test_ignores_unexpected_keys(self):
        return False
