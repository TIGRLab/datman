#!/usr/bin/env python

import os
import unittest
import logging

from nose.tools import raises
from mock import patch

import datman.utils as utils

logging.disable(logging.CRITICAL)


@patch('os.environ')
class TestCheckDependencyConfigured(unittest.TestCase):

    fake_env = {'PATH': '/some/path', 'FSLDIR': '/path/to/fsl'}

    @raises(EnvironmentError)
    @patch('datman.utils.run')
    def test_EnvironmentError_raised_if_command_not_found(self, mock_run,
                                                          mock_env):
        mock_run.return_value = (0, '')

        utils.check_dependency_configured('FreeSurfer', shell_cmd='recon-all')

    @raises(EnvironmentError)
    def test_EnvironmentError_raised_if_any_env_variable_not_defined(self,
                                                                     mock_env):
        mock_env.__getitem__.side_effect = lambda x: self.fake_env[x]

        variables = ['PATH', 'FREESURFER_HOME']
        utils.check_dependency_configured('MyProgram', env_vars=variables)

        assert False

    def test_doesnt_require_list_for_single_env_var(self, mock_env):
        mock_env.__getitem__.side_effect = lambda x: self.fake_env[x]

        utils.check_dependency_configured('SomeProgram', env_vars='PATH')
        # If function exits without error, this test should always pass
        assert True

    @patch('datman.utils.run')
    def test_exits_successfully_when_command_path_found_and_vars_set(self,
                                                                     mock_run,
                                                                     mock_env):
        mock_env.__getitem__.side_effect = lambda x: self.fake_env[x]

        cmd = 'fsl'

        def which(name):
            if name == 'which {}'.format(cmd):
                return (0, '/some/path')
            return (0, '')

        mock_run.side_effect = which
        variables = ['FSLDIR']

        utils.check_dependency_configured('FSL', shell_cmd=cmd,
                                          env_vars=variables)
        assert True
