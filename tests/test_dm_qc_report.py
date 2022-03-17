import os
import logging
import importlib

import pytest
from mock import patch

import datman.config
import datman.exceptions

logging.disable(logging.CRITICAL)

qc = importlib.import_module("bin.dm_qc_report")

FIXTURE_SETTINGS="tests/fixture_project_settings/site_config.yaml"
FIXTURE_SYSTEM="local"

config = datman.config.config(
    filename=FIXTURE_SETTINGS,
    system=FIXTURE_SYSTEM,
    study="STUDY"
)


@patch("bin.dm_qc_report.docopt")
class TestMakeQCCommand:

    study = "TEST"
    subid = "TST01_CMH_0001_01_01"

    def test_command_generates_with_expected_subject(self, mock_docopt):
        mock_docopt.return_value = {
            "<study>": self.study
        }

        result = qc.make_command(self.subid)

        assert result == f"{qc.__file__} {self.study} {self.subid}"

    def test_boolean_options_set_correctly(self, mock_docopt):
        mock_docopt.return_value = {
            "<study>": self.study,
            "--option1": True,
            "--option2": False
        }

        result = qc.make_command(self.subid)

        assert result == f"{qc.__file__} {self.study} {self.subid} --option1"

    def test_options_with_input_value_pass_value_correctly(self, mock_docopt):
        mock_docopt.return_value = {
            "<study>": self.study,
            "--path": "/some/path"
        }

        result = qc.make_command(self.subid)
        expected = f"{qc.__file__} {self.study} {self.subid} --path /some/path"

        assert result == expected

    def test_options_with_input_value_ignored_when_not_set(self, mock_docopt):
        mock_docopt.return_value = {
            "<study>": self.study,
            "--path": None
        }

        result = qc.make_command(self.subid)

        assert result == f"{qc.__file__} {self.study} {self.subid}"


@patch.dict(os.environ, {"DM_CONFIG": FIXTURE_SETTINGS,
                         "DM_SYSTEM": FIXTURE_SYSTEM}
)
class TestGetConfig:

    @patch("os.path.exists")
    def test_returns_config_when_paths_exist_and_study_defined(
            self, mock_exists):
        mock_exists.return_value = True
        config = qc.get_config(study="STUDY")
        assert config is not None
        assert type(config) == datman.config.config

    @patch("os.path.exists")
    def test_exits_gracefully_with_bad_study(self, mock_exists):
        mock_exists.return_value = True
        with pytest.raises(datman.exceptions.ConfigException):
            qc.get_config(study="madeupcode")

    @patch('datman.config.config')
    def test_exits_gracefully_when_paths_missing_from_config(
            self, mock_config):
        def mock_get_path(key):
            if key == "nii":
                return ""
            raise datman.exceptions.UndefinedSetting
        mock_config.return_value.get_path = mock_get_path

        with pytest.raises(datman.exceptions.UndefinedSetting):
            qc.get_config("STUDY")


class TestPrepareScan:
    subid = "STUDY_SITE_ID_01"
    in_dir = os.path.join(config.get_path("nii"), subid)

    def test_exits_gracefully_with_bad_subject_id(self):
        with pytest.raises(datman.exceptions.ParseException):
            qc.prepare_scan("STUDYSITE_ID", config)

    @patch("os.path.exists")
    def test_exits_gracefully_when_input_dir_doesnt_exist(self, mock_exists):
        mock_exists.side_effect = lambda x: x != self.in_dir
        with pytest.raises(datman.exceptions.InputException):
            qc.prepare_scan(self.subid, config)

    @patch("os.path.exists")
    @patch("datman.utils.remove_empty_files")
    @patch("datman.utils.define_folder")
    def test_creates_output_dir_if_doesnt_exist(self, mock_define,
                                                mock_remove, mock_exists):
        mock_exists.side_effect = lambda x: x == self.in_dir
        assert mock_define.call_count == 0
        qc.prepare_scan(self.subid, config)
        assert mock_define.call_count == 1


# Test is_outdated_header_diffs from dashboard side
# Test header qc runs when header qc is outdated from datman side
