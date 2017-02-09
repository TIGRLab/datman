import os
import unittest
import importlib
import logging

from nose.tools import raises
from mock import patch, MagicMock, call, mock_open

import datman.config

# Silence all logging during tests.
logging.disable(logging.CRITICAL)

maget = importlib.import_module('bin.dm_proc_maget_brain')

class TestSetNumTemplates(object):
    requested_num = 31
    even_requested = 42
    num_subjects = 120
    small_num_subjects = 16

    def test_returns_requested_num_when_enough_subjects_present(self):
        actual_number = maget.set_num_templates(self.requested_num,
                self.num_subjects)
        expected_number = self.requested_num
        assert actual_number == expected_number

    def test_ensures_template_num_is_odd_if_requested_num_is_even(self):
        actual_number = maget.set_num_templates(self.even_requested,
                self.num_subjects)
        expected_number = self.even_requested - 1
        assert actual_number == expected_number

    def test_sets_num_no_larger_than_number_of_subjects(self):
        actual_number = maget.set_num_templates(self.requested_num,
                self.small_num_subjects)
        expected_number = self.small_num_subjects - 1
        assert actual_number == expected_number

class TestMangleSeriesName(object):

    def test_adds_tag_correctly(self):
        series = "STUDY_SITE_ID_01_01_T2_04_series-descr.nii"
        tag = "t2"

        actual = maget.mangle_series_name(series, tag)
        expected = "STUDY_SITE_ID_01_01_T2_04_series-descr_t2.nii"

    def test_handles_file_with_complex_extension(self):
        series = "STUDY_SITE_ID_01_01_T1_04_series-descr.nii.gz"
        tag = "t1"

        actual = maget.mangle_series_name(series, tag)
        expected = "STUDY_SITE_ID_01_01_T1_04_series-descr_t1.nii.gz"

        assert actual == expected

class TestLinkSubjects(object):

    @patch('bin.dm_proc_maget_brain.make_link')
    @patch('glob.glob')
    def test_makes_links_for_matching_subset_of_subjects_data(self, mock_glob,
                mock_link):
        # Set up
        base_path = '/some/path/STUDY_SITE_ID_01'
        file_names = ['STUDY_SITE_ID_01_01_DTI60_10_Ax-DTI60.nii.gz',
                      'STUDY_SITE_ID_01_01_T1_04_SagT1.nii.gz',
                      'STUDY_SITE_ID_01_01_T2_05_OblAx-T2.nii.gz',
                      'STUDY_SITE_ID_01_01_PD_05_OblAx-PD.nii.gz']
        subject_paths = self.__make_subject_paths(base_path, file_names)
        mock_glob.return_value = subject_paths

        # Init arguments
        tag_dict = {'T1': 't1', 'PD' : 'pd'}
        destination = "/somewhere/magetbrain/input/subject"

        maget.link_subjects([base_path], destination, tag_dict)

        expected = [call(subject_paths[1],
                         '{}/STUDY_SITE_ID_01_01_T1_04_SagT1_t1.nii.gz'.format(
                         destination)),
                    call(subject_paths[3],
                         '{}/STUDY_SITE_ID_01_01_PD_05_OblAx-PD_pd.nii.gz'.format(
                         destination))]

        assert mock_link.call_count == 2
        assert sorted(mock_link.call_args_list) == sorted(expected)

    def __make_subject_paths(self, base_path, file_names):
        paths = [os.path.join(base_path, series) for series in file_names]
        return paths

class TestMagetConfig(object):

    maget_dir = '/somewhere/pipelines/magetbrain'
    atlas = 'some_atlas'
    labels_csv = 'some_atlas_labels.csv'
    atlas_dir = '/somewhere/datman/atlases'
    subject_tags = {'T2': 't2', 'PD': 'pd'}
    num_templates = 11

    @raises(SystemExit)
    def test_exits_gracefully_if_magetbrain_output_dir_not_set(self):
        config = self.__make_mock_config(path=False)
        maget_config = maget.MagetConfig(config)
        # Should raise SystemError before reaching this assertion.
        assert False

    @raises(SystemExit)
    def test_exits_gracefully_if_atlases_location_not_set(self):
        config = self.__make_mock_config(atlas_path=False)
        maget_config = maget.MagetConfig(config)
        assert False

    @raises(SystemExit)
    def test_exits_gracefully_if_atlas_dir_does_not_exist(self):
        config = self.__make_mock_config()
        maget_config = maget.MagetConfig(config)
        assert False

    @raises(SystemExit)
    def test_exits_gracefully_if_study_settings_not_given(self):
        config = self.__make_mock_config(settings=False)
        maget_config = maget.MagetConfig(config)
        assert False

    @raises(SystemExit)
    def test_exits_gracefully_when_no_atlases_listed(self):
        config = self.__make_mock_config(atlas_list=False)
        maget_config = maget.MagetConfig(config)
        assert False

    @raises(SystemExit)
    @patch('os.path.exists')
    def test_exits_gracefully_when_requested_atlas_cannot_be_found(self,
            mock_exists):
        config = self.__make_mock_config()
        atlas_base_dir = config.system_config['ATLASES']
        atlas_name = os.path.join(atlas_base_dir,
                                  self.atlas)
        mock_exists.side_effect = lambda x: {atlas_base_dir : True,
                                             atlas_name : False}[x]
        maget_config = maget.MagetConfig(config)
        assert False

    @patch('os.path.exists')
    def test_atlases_attribute_returns_list_of_requested_atlases(self,
            mock_exists):
        mock_exists.return_value = True
        config = self.__make_mock_config()
        maget_config = maget.MagetConfig(config)

        actual = maget_config.atlases

        atlas_base_dir = config.system_config['ATLASES']
        atlas_name = os.path.join(atlas_base_dir, self.atlas)
        expected = [atlas_name]

        assert sorted(actual) == sorted(expected)

    @patch('os.path.exists')
    def test_get_subject_tags_uses_default_T1_tag_when_no_tags_given(self,
            mock_exists):
        mock_exists.return_value = True
        config = self.__make_mock_config(subject_tags=False)

        maget_config = maget.MagetConfig(config)

        actual = maget_config.subject_tags
        expected = {'T1' : 't1'}
        assert actual == expected

    @patch('os.path.exists')
    def test_get_subject_tags_adds_default_T1_tag_when_not_given(self,
            mock_exists):
        mock_exists.return_value = True
        config = self.__make_mock_config()

        settings_tag_dict = config.get_key('magetbrain')['subject_tags']
        assert 'T1' not in settings_tag_dict.keys()

        maget_config = maget.MagetConfig(config)

        assert maget_config.subject_tags['T1'] == 't1'

    @patch('os.path.exists')
    def test_get_subject_tags_returns_expected_tag_dict(self, mock_exists):
        mock_exists.return_value = True
        config = self.__make_mock_config()

        expected_dict = config.get_key('magetbrain')['subject_tags']
        expected_dict['T1'] = 't1'

        maget_config = maget.MagetConfig(config)

        assert maget_config.subject_tags == expected_dict

    @patch('os.path.exists')
    def test_get_number_of_templates_uses_default_when_option_not_set(self,
            mock_exists):
        mock_exists.return_value = True
        config = self.__make_mock_config(templates=False)

        maget_config = maget.MagetConfig(config)

        assert maget_config.num_templates == 21

    @patch('os.path.exists')
    def test_get_number_of_templates_returns_expected_value(self, mock_exists):
        mock_exists.return_value = True
        config = self.__make_mock_config()

        maget_config = maget.MagetConfig(config)

        expected_num = config.get_key('magetbrain')['templates']
        assert maget_config.num_templates == expected_num

    def __make_mock_config(self, path=True, atlas_path=True, settings=True,
                           atlas_list=True, subject_tags=True, templates=True):
        mock_config = MagicMock()
        mock_config.get_path.side_effect = self.__set_value(path,
                self.maget_dir)
        atlas_dict = {}
        if atlas_path:
            atlas_dict['ATLASES'] = self.atlas_dir
        mock_config.system_config = atlas_dict
        settings_dict = {}
        if atlas_list:
            settings_dict['atlases'] = {self.atlas: self.labels_csv}
        if subject_tags:
            settings_dict['subject_tags'] = dict.copy(self.subject_tags)
        if templates:
            settings_dict['templates'] = self.num_templates
        mock_config.get_key.side_effect = self.__set_value(settings,
                settings_dict)
        return mock_config

    def __set_value(self, include, value):
        if include:
            return lambda x: value
        return self.func_keyerror

    def func_keyerror(self, input):
        raise KeyError

    # @patch('os.path.exists')
    # def test_get_label_file_contents_returns_empty_list_when_file_unreadable(self,
    #         mock_exists):
    #     mock_exists.return_value = True
    #     config = self.__make_mock_config()
    #
    #     maget_config = maget.MagetConfig(config)
    #
    #     info_path = maget_config.get_label_info_path(self.atlas)
    #     contents = maget_config.get_label_info_contents(info_path)
    #
    #     assert not contents

    # @patch('os.path.exists')
    # def test_read_info_returns_expected_data(self, mock_exists):
    #     mock_exists.return_value = True
    #     config = self.__make_mock_config()
    #
    #     maget_config = maget.MagetConfig(config)
    #
    #     label_info = ['thalamus, (x == 1)\n',
    #                   'hippocampus, (x == 2)\n',
    #                   'banana, (x > 3 && x < 6)\n']
    #     expected = {'thalamus' : '(x == 1)',
    #                 'hippocampus' : '(x == 2)',
    #                 'banana' : '(x > 3 && x < 6)'}
    #
    #     with patch('__builtin__.open', mock_open()) as info_stream:
    #         info_stream.return_value.readlines.return_value = label_info
    #
    #         labels = maget_config.read_label_info(self.atlas)
    #
    #         assert labels == expected

    # @patch('os.path.exists')
    # def test_get_labels_info_path_returns_empty_string_when_atlas_not_recognized(
    #         self, mock_exists):
    #     mock_exists.return_value = True
    #     config = self.__make_mock_config()
    #
    #     maget_config = maget.MagetConfig(config)
    #     csv_path = maget_config.get_label_info_path('unrecognized_atlas_name')
    #
    #     assert csv_path is ''

    # @patch('os.path.exists')
    # def test_get_label_info_path_returns_full_path_to_label_info(self,
    #         mock_exists):
    #     mock_exists.return_value = True
    #     config = self.__make_mock_config()
    #
    #     maget_config = maget.MagetConfig(config)
    #
    #     actual = maget_config.get_label_info_path(self.atlas)
    #     expected = os.path.join(self.atlas_dir, self.atlas, self.labels_csv)
    #
    #     assert actual == expected
