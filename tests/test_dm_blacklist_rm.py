import os
import unittest
import importlib

from mock import MagicMock, patch

remove = importlib.import_module('bin.dm_blacklist_rm')

FIXTURE = 'tests/fixture_dm_blacklist_rm'

class GetBlacklist(unittest.TestCase):
    whitespace_bl = os.path.join(FIXTURE, 'blacklist.csv')
    comma_bl = os.path.join(FIXTURE, 'blacklist_commas.csv')
    bad_comment_bl = os.path.join(FIXTURE, 'blacklist_bad_comment.csv')
    expected_bl = ['STUDY_SITE_0001_TIMEPOINT_SESSION_TAG_SERIESNUM_DESCR',
                   'STUDY_SITE_9999_TIMEPOINT_SESSION_TAG_SERIESNUM_DESCR',
                   'STUDY_SITE_1234_TIMEPOINT_SESSION_TAG_SERIESNUM_DESCR']
    # Not used in any of these tests, just a required argument
    config = MagicMock()

    def test_retrieves_expected_data_from_whitespace_separated_list(self):
        actual_blacklist = remove.get_blacklist(self.whitespace_bl, None,
                                                self.config)
        assert actual_blacklist == self.expected_bl

    def test_retrieves_expected_data_from_comma_separated_list(self):
        actual_blacklist = remove.get_blacklist(self.comma_bl, None,
                                                self.config)
        assert actual_blacklist == self.expected_bl

    def test_parses_data_correctly_when_spaces_present_in_comment(self):
        actual_blacklist = remove.get_blacklist(self.bad_comment_bl, None,
                                                self.config)
        assert actual_blacklist == self.expected_bl

    def test_doesnt_read_blacklist_when_series_given(self):
        new_series = 'STUDY_SITE_7777_01_01_DTI-1000_01_DESCR'
        actual_blacklist = remove.get_blacklist(self.whitespace_bl, new_series,
                                                self.config)
        assert actual_blacklist == [new_series]

class GetSearchPaths(unittest.TestCase):
    config = MagicMock()
    config_paths = {'std' : '', 'qc' : '', 'dicom' : '',
                    'nrrd' : '', 'mnc': '', 'nii' : '',
                    'resources' : ''}

    def test_filters_out_ignored_paths(self):
        self.config.get_key.return_value = self.config_paths
        ignored_paths = ['qc', 'resources', 'std']

        search_paths = remove.get_search_paths(self.config, ignored_paths)

        expected = ['dicom', 'nrrd', 'mnc', 'nii']

        assert sorted(search_paths) == sorted(expected)

    def test_returns_all_paths_when_ignored_list_is_empty(self):
        self.config.get_key.return_value = self.config_paths
        ignored_paths = []

        search_paths = remove.get_search_paths(self.config, ignored_paths)

        expected = self.config_paths.keys()

        assert sorted(search_paths) == sorted(expected)

class FindFiles(unittest.TestCase):
    search_path = '/some/path/some/where'
    item = 'STUDY_SITE_ID_01_01_TAG_NUM_DESCR'

    @patch('datman.utils.run')
    def test_returns_empty_list_when_no_results(self, mock_find):
        mock_find.return_value = (0, '')

        actual_result = remove.find_files(self.search_path, self.item)
        expected_result = []

        assert actual_result == expected_result

    @patch('datman.utils.run')
    def test_doesnt_include_empty_string_in_result_list(self, mock_find):
        # Without the .strip() argument, the empty string will always appear as
        # as the last item in the returned list. This test should fail if it is
        # removed for any reason, to guard against this problem.
        mock_find.return_value = (0, '{}/{}.dcm\n'.format(self.search_path,
                self.item))

        actual_result = remove.find_files(self.search_path, self.item)
        expected_result = ['{}/{}.dcm'.format(self.search_path, self.item)]

        assert actual_result == expected_result

    @patch('datman.utils.run')
    def test_correctly_splits_string_with_multiple_matches(self, mock_find):
        mock_find.return_value = (0, '{path}/{item}.nii\n{path}/{item}.bval\n'
                    '{path}/{item}.bvec\n'.format(path=self.search_path,
                    item=self.item))

        actual_result = remove.find_files(self.search_path, self.item)
        expected_result = ['{}/{}.nii'.format(self.search_path, self.item),
                           '{}/{}.bval'.format(self.search_path, self.item),
                           '{}/{}.bvec'.format(self.search_path, self.item)]

        assert sorted(actual_result) == sorted(expected_result)
