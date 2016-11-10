import unittest

import datman.project_config as pc

FIXTURE = "/projects/dawn/current/datman/tests/fixture_project_settings/" \
          "project_settings.yml"

class TestProjectConfig(unittest.TestCase):
    config = pc.Config(FIXTURE)

    def test_reads_project_settings(self):
        assert self.config.settings_path == FIXTURE

        expected_paths = ['meta', 'dcm', 'nii', 'resources', 'qc', 'std', 'log']
        assert sorted(self.config.paths.keys()) == sorted(expected_paths)

        expected_sites = ['CMH', 'MRP']
        assert sorted(self.config.sites.keys()) == sorted(expected_sites)

    def test_get_path_returns_empty_string_with_bad_path_key(self):
        key = 'home'
        path = self.config.get_path(key)

        assert path == ""

    def test_get_export_info_returns_empty_ExportInfo_with_bad_site(self):
        site = 'YORK'
        export_settings = self.config.get_export_info(site)

        assert isinstance(export_settings, pc.ExportInfo)
        assert export_settings.export_info == {}
        assert export_settings.tags == []

class TestExportInfo(unittest.TestCase):
    config = pc.Config(FIXTURE)
    export_settings = config.get_export_info('CMH')

    def test_get_tag_info_returns_tag_dict(self):
        tag_info = self.export_settings.get_tag_info('RST')

        expected = {'Pattern': ['Resting', 'Rest'], 'Count': 1,
                    'Order': [1, 7, 3]}
        assert tag_info == expected

    def test_get_tag_info_returns_empty_dict_with_bad_key(self):
        tag_info = self.export_settings.get_tag_info('somekey')

        assert tag_info == {}
