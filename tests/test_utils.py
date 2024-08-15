#!/usr/bin/env python

import os
import unittest
import logging
from random import randint

import pytest
from mock import patch, MagicMock

import datman.utils as utils
import datman.config
from datman.exceptions import ParseException

logging.disable(logging.CRITICAL)


@patch('os.environ')
class TestCheckDependencyConfigured(unittest.TestCase):

    fake_env = {'PATH': '/some/path', 'FSLDIR': '/path/to/fsl'}

    @patch('datman.utils.run')
    def test_EnvironmentError_raised_if_command_not_found(
            self, mock_run, mock_env):
        mock_run.return_value = (0, '')

        with pytest.raises(EnvironmentError):
            utils.check_dependency_configured('FreeSurfer',
                                              shell_cmd='recon-all')

    def test_EnvironmentError_raised_if_any_env_variable_not_defined(
            self, mock_env):
        mock_env.__getitem__.side_effect = lambda x: self.fake_env[x]

        variables = ['PATH', 'FREESURFER_HOME']

        with pytest.raises(EnvironmentError):
            utils.check_dependency_configured('MyProgram', env_vars=variables)

    def test_doesnt_require_list_for_single_env_var(self, mock_env):
        mock_env.__getitem__.side_effect = lambda x: self.fake_env[x]

        utils.check_dependency_configured('SomeProgram', env_vars='PATH')
        # If function exits without error, this test should always pass
        assert True

    @patch('datman.utils.run')
    def test_exits_successfully_when_command_path_found_and_vars_set(
            self, mock_run, mock_env):
        mock_env.__getitem__.side_effect = lambda x: self.fake_env[x]

        cmd = 'fsl'

        def which(name):
            if name == 'which {}'.format(cmd):
                return (0, '/some/path')
            return (0, '')

        mock_run.side_effect = which
        variables = ['FSLDIR']

        utils.check_dependency_configured('FSL',
                                          shell_cmd=cmd,
                                          env_vars=variables)
        assert True


class TestValidateSubjectID:

    correct_id = "ANDT_CMH_0210_01_01"

    @pytest.fixture(scope="module")
    def dm_config(self):
        config = MagicMock(spec=datman.config.config)

        id_settings = {
            "Study": {
                "AND01": "ANDT"
            }
        }

        tags = {
            "ANDT": ["CMH"]
        }

        def get_key(key):
            if key == "IdMap":
                return id_settings
            raise datman.config.UndefinedSetting

        config.get_key.side_effect = get_key
        config.get_study_tags.return_value = tags
        return config

    def test_valid_datman_id_accepted(self, dm_config):
        ident = utils.validate_subject_id(self.correct_id, dm_config)
        assert str(ident) == self.correct_id

    def test_valid_kcni_id_accepted(self, dm_config):
        valid_kcni = "AND01_CMH_0210_01_SE01_MR"
        ident = utils.validate_subject_id(valid_kcni, dm_config)
        assert str(ident) == self.correct_id

    def test_catches_invalid_project_in_datman_id(self, dm_config):
        with pytest.raises(ParseException):
            bad_proj = "OPT01_CMH_0210_01_01"
            utils.validate_subject_id(bad_proj, dm_config)

    def test_catches_invalid_project_in_kcni_id(self, dm_config):
        with pytest.raises(ParseException):
            bad_proj = "OPT01_CMH_0210_01_SE01_MR"
            utils.validate_subject_id(bad_proj, dm_config)

    def test_catches_invalid_site_in_datman_id(self, dm_config):
        with pytest.raises(ParseException):
            bad_site = "ANDT_UFO_0406_01_01"
            utils.validate_subject_id(bad_site, dm_config)

    def test_catches_invalid_site_in_kcni_id(self, dm_config):
        with pytest.raises(ParseException):
            bad_site = "AND01_UFO_0408_01_SE01_MR"
            utils.validate_subject_id(bad_site, dm_config)


class FindTechNotes(unittest.TestCase):
    notes = "TechNotes.pdf"
    jpg_notes = "TechNotes.jpg"
    other_pdf1 = "SomeFile.pdf"
    other_pdf2 = "otherFile.pdf"
    path = "./resources"

    def test_doesnt_crash_with_broken_path(self):
        found_file = utils.find_tech_notes(self.path)
        assert not found_file

    @patch('os.walk', autospec=True)
    def test_doesnt_crash_when_no_tech_notes_exist(self, mock_walk):
        mock_walk.return_value = self.__mock_file_system(
            randint(1, 10), add_pdf_notes=False)

        found_file = utils.find_tech_notes(self.path)

        assert not found_file

    @patch('os.walk', autospec=True)
    def test_tech_notes_found_regardless_of_depth(self, mock_walk):
        mock_walk.return_value = self.__mock_file_system(randint(1, 10))

        found_file = utils.find_tech_notes(self.path)

        assert os.path.basename(found_file) == self.notes

    @patch('os.walk', autospec=True)
    def test_returns_tech_notes_when_multiple_pdfs_present(self, mock_walk):
        mock_walk.return_value = self.__mock_file_system(
            randint(1, 10), add_pdf=True)

        found_file = utils.find_tech_notes(self.path)

        assert os.path.basename(found_file) == self.notes

    @patch('os.walk', autospec=True)
    def test_first_file_returned_when_multiple_pdfs_but_no_tech_notes(
            self, mock_walk):
        mock_walk.return_value = self.__mock_file_system(
            randint(1, 10), add_pdf_notes=False, add_pdf=True)

        found_file = utils.find_tech_notes(self.path)

        assert os.path.basename(found_file) == self.other_pdf1

    @patch('os.walk', autospec=True)
    def test_finds_non_pdf_tech_notes(self, mock_walk):
        mock_walk.return_value = self.__mock_file_system(
            randint(1, 10), add_pdf_notes=False, add_pdf=True,
            add_jpg_notes=True)

        found_file = utils.find_tech_notes(self.path)

        assert os.path.basename(found_file) == self.jpg_notes

    @patch('os.walk', autospec=True)
    def test_doesnt_pick_similarly_named_file(self, mock_walk):
        mock_walk.return_value = self.__mock_file_system(
            randint(1, 10), add_pdf_notes=False, add_pdf=True,
            add_jpg_notes=True, add_jpgs=True)

        found_file = utils.find_tech_notes(self.path)

        assert os.path.basename(found_file) == self.jpg_notes

    @patch('os.walk', autospec=True)
    def test_prefers_pdf_notes_over_other_formats(self, mock_walk):
        mock_walk.return_value = self.__mock_file_system(
            randint(1, 10), add_pdf_notes=True, add_jpg_notes=True,
            add_pdf=True, add_jpgs=True)

        found_file = utils.find_tech_notes(self.path)

        assert os.path.basename(found_file) == self.notes

    def __mock_file_system(self, depth, add_pdf_notes=True, add_jpgs=False,
                           add_jpg_notes=False, add_pdf=False):
        walk_list = []
        cur_path = self.path
        file_list = ["file1.txt", "file2"]
        if add_pdf:
            file_list.extend([self.other_pdf1, self.other_pdf2])
        if add_jpg_notes:
            file_list.extend([self.jpg_notes])
        if add_pdf_notes:
            file_list.append(self.notes)
        if add_jpgs:
            file_list.extend(['SpiralView.jpg', 'RANotes.jpg'])
        for num in range(1, depth + 1):
            cur_path = cur_path + "/dir{}".format(num)
            dirs = ("dir{}".format(num + 1), )
            files = ("file1.txt", "file2")
            if num == depth:
                files = tuple(file_list)
            level = (cur_path, dirs, files)
            walk_list.append(level)
        return walk_list


@patch('datman.utils.write_metadata')
@patch('datman.utils.read_checklist')
@patch('datman.utils.locate_metadata')
@patch('datman.utils.dashboard')
class TestUpdateChecklist:
    def test_entry_with_repeat_num_doesnt_crash_when_updating_file(
            self, mock_dash, mock_locate, mock_read, mock_write
    ):
        mock_dash.dash_found = False
        mock_locate.return_value = '/some/path/checklist.csv'
        mock_read.return_value = {}

        utils.update_checklist(
            {'STUDY_SITE_SUB001_01_01': 'comment'}, study='STUDY'
        )
