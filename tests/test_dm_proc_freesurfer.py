import unittest
import importlib
import logging

fs = importlib.import_module("bin.dm_proc_freesurfer")

logging.disable(logging.CRITICAL)

class TestGetRunScript(unittest.TestCase):

    def test_chooses_site_script_if_present(self):
        return False

    def test_chooses_generic_script_if_site_script_unavailable(self):
        return False

    def test_returns_none_if_no_script_found(self):
        return False

class TestGetSiteStandards(unittest.TestCase):

    def test_returns_none_if_run_script_not_found(self):
        return False

    def test_returns_none_if_recon_all_command_cant_be_read(self):
        return False

    def test_returns_none_if_no_arguments_read_from_recon_command(self):
        return False

    def test_standards_contain_expected_fields(self):
        return False

class TestGetFreesurferFolders(unittest.TestCase):

    def test_doesnt_crash_when_bad_subject_names_given(self):
        return False

    def test_skips_subjects_with_no_outputs(self):
        return False
