#!/usr/bin/env python

import unittest
import logging

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
            "STUDY": {
                "AND01": "ANDT"
            }
        }

        tags = {
            "ANDT": ["CMH"]
        }

        def get_key(key):
            if key == "ID_MAP":
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
