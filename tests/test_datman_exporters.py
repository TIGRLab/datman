import os

import pytest
from mock import Mock, patch

import datman.exporters as exporters
from datman.config import TagInfo


class TestNiiLinkExporter:

    def test_match_dm_to_bids_matches_configured_scans_correctly(
            self, config, session, experiment):

        exporter = exporters.NiiLinkExporter(config, session, experiment)

        dm_names = {
            'T1': [f'{experiment.name}_T1_03_T1w'],
            'DTI-ABCD': [f'{experiment.name}_DTI-ABCD_05_Ax-DTI-60plus5']
        }

        bids_names = [
            f'{session.bids_path}/dwi/sub-CMH0000_ses-01_dwi',
            f'{session.bids_path}/anat/sub-CMH0000_ses-01_T1w'
        ]

        matches = exporter.match_dm_to_bids(dm_names, bids_names)

        assert len(matches) == 1
        assert dm_names['T1'][0] in matches
        assert matches[dm_names['T1'][0]] == bids_names[1]

    def test_match_dm_to_bids_works_when_tag_count_greater_than_one(
            self, config, session, experiment):

        exporter = exporters.NiiLinkExporter(config, session, experiment)

        dm_names = {
            'NBK': [
                f'{experiment.name}_NBK_07_Nback-fMRI',
                f'{experiment.name}_NBK_12_Nback-fMRI'
            ]
        }

        bids_names = [
            f'{session.bids_path}/dwi/sub-CMH0000_ses-01_dwi',
            (f'{session.bids_path}/func/sub-CMH0000_ses-01_task-nback_'
                'run-02_bold'),
            f'{session.bids_path}/anat/sub-CMH0000_ses-01_T1w',
            (f'{session.bids_path}/func/sub-CMH0000_ses-01_task-nback_'
                'run-01_bold')
        ]

        matches = exporter.match_dm_to_bids(dm_names, bids_names)

        assert len(matches) == 2
        assert dm_names['NBK'][0] in matches
        assert matches[dm_names['NBK'][0]] == bids_names[3]
        assert dm_names['NBK'][1] in matches
        assert matches[dm_names['NBK'][1]] == bids_names[1]

    def test_match_dm_to_bids_matches_files_when_dm_name_not_assigned(
            self, config, session, experiment):

        exporter = exporters.NiiLinkExporter(config, session, experiment)

        dm_names = {}
        bids_names = [
            f'{session.bids_path}/dwi/sub-CMH0000_ses-01_dwi',
            f'{session.bids_path}/perf/sub-CMH0000_ses-01_cbf',
            f'{session.bids_path}/perf/sub-CMH0000_ses-01_m0scan'
        ]

        matches = exporter.match_dm_to_bids(dm_names, bids_names)

        expected_name = f'{experiment.name}_CBF_08_cbf'
        assert len(matches) == 1
        assert expected_name in matches
        assert matches[expected_name] == bids_names[0]


    @pytest.fixture
    def config(self):
        """Create a mock datman config object, with tags defined.
        """
        test_tags = {
            'T1': {
                'Bids': {'class': 'anat', 'modality_label': 'T1w'},
                'Count': 1
            },
            'NBK': {
                'Bids': {
                    'class': 'func',
                    'contrast_label': 'bold',
                    'task': 'nback'
                },
                'Count': 2
            },
            'CBF': {
                'Bids': {'class': 'perf', 'modality_label': 'cbf'},
                'Count': 1
            }
        }

        def get_tags(site=None):
            return TagInfo(test_tags)

        config = Mock()
        config.get_tags = get_tags

        return config

    @pytest.fixture
    def session(self):
        session = Mock()
        session.nii_path = "/some/study/data/nii/STUDY01_CMH_0000_01"
        session.bids_path = "/some/study/data/bids/sub-CMH0000/ses-01"
        return session

    @pytest.fixture
    def experiment(self):
        exp = Mock()
        exp.name = 'STUDY01_CMH_0000_01_01'
        exp.scans = []
        return exp


# class NiiExporter:
#
#     def test_split_series_doesnt_export_same_file_with_two_names(self):
#         assert False
