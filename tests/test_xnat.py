import os
import unittest
import logging

from mock import Mock, patch
import pytest

import datman.xnat
# Used only to act as a spec for Mock
from datman.config import config as Config

# Dont care about logging for these tests
logging.disable(logging.CRITICAL)


class TestGetPortStr(unittest.TestCase):
    def _set_config_port(self, port):
        self.mock_config.get_key.side_effect = lambda key: {
            'XNATPORT': port
        }[key]

    def setUp(self):
        self.mock_config = Mock(spec=Config)
        self.mock_config.get_key.side_effect = lambda key: {}[key]

    def test_raises_KeyError_when_given_port_is_None_and_config_doesnt_define(
            self):
        with pytest.raises(KeyError):
            datman.xnat.get_port_str(self.mock_config, None)

    def test_retrieves_port_from_config_file_when_port_is_None(self):
        expected = ":443"
        self._set_config_port(expected)

        actual = datman.xnat.get_port_str(self.mock_config, None)

        assert actual == expected

    def test_ignores_config_when_port_is_not_None(self):
        config_port = ":443"
        given_port = ":22"
        self._set_config_port(config_port)

        result = datman.xnat.get_port_str(self.mock_config, given_port)

        assert result == given_port

    def test_prepends_colon_when_missing_from_given_port(self):
        port = "443"
        expected_result = ":443"

        actual_result = datman.xnat.get_port_str(self.mock_config, port)

        assert actual_result == expected_result

    def test_prepends_colon_when_missing_from_config_port(self):
        config_port = "22"
        expected_result = ":22"
        self._set_config_port(config_port)

        actual_result = datman.xnat.get_port_str(self.mock_config, None)

        assert actual_result == expected_result

    def test_handles_integer_inputs(self):
        port = 443
        expected_result = ":443"

        actual_result = datman.xnat.get_port_str(self.mock_config, port)

        assert actual_result == expected_result


class TestGetServer(unittest.TestCase):
    def _set_server_config(self, url, port=None):
        config_dict = {'XNATSERVER': url}
        if port:
            config_dict['XNATPORT'] = port
        self.mock_config.get_key.side_effect = lambda key: config_dict[key]

    def setUp(self):
        self.mock_config = Mock(spec=Config)
        self.mock_config.get_key.side_effect = lambda key: {}[key]

    def test_server_retrieved_from_config_files_when_not_given_url(self):
        config_server = 'https://fakeserver.ca'

        self._set_server_config(config_server)
        returned_server = datman.xnat.get_server(self.mock_config)

        assert returned_server == config_server, ("Returned server {} doesnt "
                                                  "match {}".format(
                                                      returned_server,
                                                      config_server))

    def test_ignores_config_file_when_given_url(self):
        config_server = 'https://fakeserver.ca'
        provided_server = 'https://someotherserver.ca'

        self._set_server_config(config_server)
        returned_server = datman.xnat.get_server(self.mock_config,
                                                 url=provided_server)

        assert returned_server != config_server

    def test_raises_KeyError_when_server_not_given_and_config_setting_missing(
            self):
        with pytest.raises(KeyError):
            datman.xnat.get_server(self.mock_config)

    def test_adds_https_protocol_when_no_protocol_in_url(self):
        server = 'someserver.ca'
        expected_url = 'https://{}'.format(server)

        returned_url = datman.xnat.get_server(self.mock_config, server)

        assert returned_url == expected_url, ('Protocol not added when server '
                                              'given as arg')

        self._set_server_config(server)
        returned_server = datman.xnat.get_server(self.mock_config)

        assert returned_server == expected_url, ('Protocol not added when '
                                                 'server read from config '
                                                 'file')

    def test_adds_config_port_when_no_port_given(self):
        url = "https://testserver.ca"
        port = ":443"
        self._set_server_config(url, port)

        expected = url + port
        result = datman.xnat.get_server(self.mock_config)

        assert result == expected

    def test_doesnt_use_config_port_when_user_gives_url_but_no_port(self):
        url = "https://testserver.ca"
        config_port = ":443"
        self._set_server_config(url, config_port)

        expected = url
        result = datman.xnat.get_server(self.mock_config, url)

        assert result == expected

    def test_user_port_overrides_config_port(self):
        url = "https://testserver.ca"
        config_port = ":443"
        user_port = ":22"
        self._set_server_config(url, config_port)

        expected = url + user_port
        result = datman.xnat.get_server(self.mock_config, url, user_port)

        assert result == expected

    def test_appending_port_to_url_ending_in_slash_produces_valid_url(self):
        url = "https://testserver.ca"
        port = ":443"

        expected = url + port
        result = datman.xnat.get_server(self.mock_config, url + "/", port)

        assert result == expected


class TestGetAuth(unittest.TestCase):
    @patch('getpass.getpass')
    def test_asks_user_to_enter_password_if_username_provided(self, mock_pass):
        datman.xnat.get_auth('someuser')
        assert mock_pass.call_count == 1

    def test_raises_KeyError_if_username_not_given_and_not_set_in_env(self):
        with pytest.raises(KeyError):
            with patch.dict(os.environ, {}, clear=True):
                datman.xnat.get_auth()

    def test_raises_KeyError_if_username_found_in_env_and_password_not_set(
            self):
        env = {'XNAT_USER': 'someuser'}
        with pytest.raises(KeyError):
            with patch.dict('os.environ', env, clear=True):
                datman.xnat.get_auth()
