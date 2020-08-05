import importlib

import pytest
from mock import Mock

from datman.scanid import ParseException
import datman.config

rc = importlib.import_module('bin.dm_redcap_scan_completed')


class TestParseID:

    datman_id = "ABC01_DEF_0001_01_01"

    def test_datman_id_parsed_correctly(self, config):
        rc.cfg = config
        parsed = rc.parse_id(self.datman_id)

        assert str(parsed) == self.datman_id

    def test_kcni_id_parsed_correctly(self, config):
        rc.cfg = config
        kcni_id = 'ABC01_DEF_0001_01_SE01_MR'

        parsed = rc.parse_id(kcni_id)

        assert str(parsed) == self.datman_id

    def test_kcni_id_with_diff_site_code_parsed_correctly(self, config):
        def mock_get_key(key):
            if key != 'ID_MAP':
                raise datman.config.UndefinedSetting
            settings = {
                'SITE': {
                    'XYZ': 'DEF'
                }
            }
            return settings
        config.get_key.side_effect = mock_get_key
        rc.cfg = config
        kcni_id = 'ABC01_XYZ_0001_01_SE01_MR'

        parsed = rc.parse_id(kcni_id)

        assert str(parsed) == self.datman_id

    def test_bad_id_raises_parse_exception(self, config):
        rc.cfg = config
        bad_id = 'ABC01-9999'
        with pytest.raises(ParseException):
            rc.parse_id(bad_id)

    @pytest.fixture
    def config(self):
        conf = Mock(spec=datman.config.config)

        def mock_get_key(key):
            raise datman.config.UndefinedSetting

        conf.get_key.side_effect = mock_get_key
        return conf
