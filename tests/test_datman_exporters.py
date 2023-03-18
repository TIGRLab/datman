import os

import pytest
from mock import Mock, patch, mock_open

import datman.exporters as exporters
from datman.config import TagInfo
from datman.scanid import parse


class TestNiiLinkExporter:

    def test_match_dm_to_bids_matches_configured_scans_correctly(
            self, config, session, experiment):

        exporter = exporters.NiiLinkExporter(config, session, experiment)

        dm_names = {
            'T1': [f'{experiment.name}_T1_03_T1w'],
            'DTI-ABCD': [f'{experiment.name}_DTI-ABCD_05_Ax-DTI-60plus5']
        }

        bids_dwi = f'{session.bids_path}/dwi/sub-CMH0000_ses-01_dwi'
        bids_t1 = f'{session.bids_path}/anat/sub-CMH0000_ses-01_T1w'

        bids_names = [bids_dwi, bids_t1]

        json_contents = {
            bids_dwi:
                '{"SeriesNumber": "5", "SeriesDescription": "Ax-DTI-60plus5"}',
            bids_t1:
                '{"SeriesNumber": "3", "SeriesDescription": "T1w"}'
        }

        fake_jsons = replace_sidecars(json_contents)

        with patch('datman.exporters.open', new=fake_jsons) as mock_fh:
            matches = exporter.match_dm_to_bids(dm_names, bids_names)

        assert len(matches) == 1
        assert dm_names['T1'][0] in matches
        assert matches[dm_names['T1'][0]] == bids_names[1]

    def test_match_dm_to_bids_works_when_tag_count_greater_than_one(
            self, config, session, experiment):

        exporter = exporters.NiiLinkExporter(config, session, experiment)

        dm_names = {
            'T1': [f'{experiment.name}_T1_03_T1w'],
            'NBK': [
                f'{experiment.name}_NBK_07_Nback-fMRI',
                f'{experiment.name}_NBK_12_Nback-fMRI'
            ]
        }

        bids_dwi = f'{session.bids_path}/dwi/sub-CMH0000_ses-01_dwi'
        bids_nback1 = (
            f'{session.bids_path}/func/sub-CMH0000_ses-01_task-nback_'
            'run-02_bold'
        )
        bids_t1 = f'{session.bids_path}/anat/sub-CMH0000_ses-01_T1w'
        bids_nback2 = (
            f'{session.bids_path}/func/sub-CMH0000_ses-01_task-nback_'
            'run-01_bold'
        )

        bids_names = [bids_dwi, bids_nback1, bids_t1, bids_nback2]

        json_contents = {
            bids_dwi:
                '{"SeriesNumber": "5", "SeriesDescription": "Ax-DTI-60Plus5"}',
            bids_nback1:
                '{"SeriesNumber": "12", "SeriesDescription": "Nback-fMRI"}',
            bids_t1:
                '{"SeriesNumber": "3", "SeriesDescription": "T1w"}',
            bids_nback2:
                '{"SeriesNumber": "7", "SeriesDescription": "Nback-fMRI"}'
        }

        fake_jsons = replace_sidecars(json_contents)

        with patch('datman.exporters.open', new=fake_jsons) as mock_fh:
            matches = exporter.match_dm_to_bids(dm_names, bids_names)

        assert len(matches) == 3
        assert dm_names['NBK'][0] in matches
        assert matches[dm_names['NBK'][0]] == bids_names[3]
        assert dm_names['NBK'][1] in matches
        assert matches[dm_names['NBK'][1]] == bids_names[1]

    def test_match_dm_to_bids_matches_files_when_dm_name_not_assigned(
            self, config, session, experiment):

        exporter = exporters.NiiLinkExporter(config, session, experiment)

        dm_names = {'T1': [f'{experiment.name}_T1_03_T1w']}

        bids_t1 = f'{session.bids_path}/anat/sub-CMH0000_ses-01_T1w'
        bids_cbf = f'{session.bids_path}/perf/sub-CMH0000_ses-01_cbf'
        bids_m0 = f'{session.bids_path}/perf/sub-CMH0000_ses-01_m0scan'

        bids_names = [bids_t1, bids_cbf]

        json_contents = {
            bids_t1:
                '{"SeriesNumber": "3", "SeriesDescription": "T1w"}',
            bids_cbf:
                '{"SeriesNumber": "8", "SeriesDescription": "CBF"}',
        }

        fake_jsons = replace_sidecars(json_contents)

        with patch('datman.exporters.open', new=fake_jsons) as mock_fh:
            matches = exporter.match_dm_to_bids(dm_names, bids_names)

        expected_name = f'{experiment.name}_CBF_08_CBF'
        assert len(matches) == 2
        assert expected_name in matches
        assert matches[expected_name] == bids_names[1]

    def test_match_dm_to_bids_makes_correct_filenames_for_split_field_maps(
                self, config, session, experiment):
        fmap = Mock()
        fmap.names = []
        fmap.description = 'Rs_FieldMap'
        fmap.series = 7
        experiment.scans = [fmap]

        exporter = exporters.NiiLinkExporter(config, session, experiment)

        dm_names = {}

        fmap_ap = (
            f'{session.bids_path}/fmap/sub-CMH0000_ses-01_acq-rest_dir-AP_epi'
        )
        fmap_pa = (
            f'{session.bids_path}/fmap/sub-CMH0000_ses-01_acq-rest_dir-PA_epi'
        )

        bids_names = [fmap_ap, fmap_pa]

        json_contents = {
            fmap_ap:
                '{"SeriesNumber": "1007", "SeriesDescription": "Rs_FieldMap"}',
            fmap_pa:
                '{"SeriesNumber": "7", "SeriesDescription": "Rs_FieldMap"}'
        }

        fake_jsons = replace_sidecars(json_contents)

        with patch('datman.exporters.open', new=fake_jsons) as mock_fh:
            matches = exporter.match_dm_to_bids(dm_names, bids_names)

        assert len(matches) == 2
        expected_ap = "STUDY01_CMH_0000_01_01_FMAP-AP_07_Rs-FieldMap"
        expected_pa = "STUDY01_CMH_0000_01_01_FMAP-PA_07_Rs-FieldMap"

        assert expected_ap in matches
        assert matches[expected_ap] == bids_names[0]

        assert expected_pa in matches
        assert matches[expected_pa] == bids_names[1]

    def test_match_dm_to_bids_handles_multiple_split_field_maps(
                self, config, session, experiment):
        for series in [7, 13]:
            mock_scan = Mock()
            mock_scan.names = []
            mock_scan.description = 'Rs_FieldMap'
            mock_scan.series = series
            experiment.scans.append(mock_scan)

        exporter = exporters.NiiLinkExporter(config, session, experiment)

        dm_names = {}

        fmap_ap1 = (
            f'{session.bids_path}/fmap/sub-CMH0000_ses-01_acq-rest_'
            'dir-AP_run-01_epi'
        )
        fmap_pa1 = (
            f'{session.bids_path}/fmap/sub-CMH0000_ses-01_acq-rest_'
            'dir-PA_run-01_epi'
        )
        fmap_ap2 = (
            f'{session.bids_path}/fmap/sub-CMH0000_ses-01_acq-rest_'
            'dir-AP_run-02_epi'
        )
        fmap_pa2 = (
            f'{session.bids_path}/fmap/sub-CMH0000_ses-01_acq-rest_'
            'dir-PA_run-02_epi'
        )

        bids_names = [fmap_ap1, fmap_pa1, fmap_ap2, fmap_pa2]

        json_contents = {
            fmap_ap1:
                '{"SeriesNumber": "1007", "SeriesDescription": "Rs_FieldMap"}',
            fmap_pa1:
                '{"SeriesNumber": "7", "SeriesDescription": "Rs_FieldMap"}',
            fmap_ap2:
                '{"SeriesNumber": "1013", "SeriesDescription": "Rs_FieldMap"}',
            fmap_pa2:
                '{"SeriesNumber": "13", "SeriesDescription": "Rs_FieldMap"}',
        }

        fake_jsons = replace_sidecars(json_contents)

        with patch('datman.exporters.open', new=fake_jsons) as mock_fh:
            matches = exporter.match_dm_to_bids(dm_names, bids_names)

        assert len(matches) == 4
        expected_ap1 = "STUDY01_CMH_0000_01_01_FMAP-AP_07_Rs-FieldMap"
        expected_pa1 = "STUDY01_CMH_0000_01_01_FMAP-PA_07_Rs-FieldMap"
        expected_ap2 = "STUDY01_CMH_0000_01_01_FMAP-AP_13_Rs-FieldMap"
        expected_pa2 = "STUDY01_CMH_0000_01_01_FMAP-PA_13_Rs-FieldMap"
        expected_names = [expected_ap1, expected_pa1,
                         expected_ap2, expected_pa2]

        for idx, expected_name in enumerate(expected_names):
            assert expected_name in matches
            assert matches[expected_name] == bids_names[idx]

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
            },
            'FMAP-AP': {
                'Bids': {
                    'class': 'fmap',
                    'modality_label': 'AP',
                    'match_acq': ['rest', 'nback']
                },
                'Count': 1
            },
            'FMAP-PA': {
                'Bids': {
                    'class': 'fmap',
                    'modality_label': 'PA',
                    'match_acq': ['rest', 'nback']
                },
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
        session._ident = parse("STUDY01_CMH_0000_01_01")
        session.nii_path = "/some/study/data/nii/STUDY01_CMH_0000_01"
        session.bids_path = "/some/study/data/bids/sub-CMH0000/ses-01"
        return session

    @pytest.fixture
    def experiment(self):
        exp = Mock()
        exp.name = 'STUDY01_CMH_0000_01_01'
        exp.scans = []
        return exp


def replace_sidecars(contents_dict):
    """Used to provide JSON side car contents to open() calls.
    """
    def open_contents(filename):
        filename = filename.replace(".json", "")
        try:
            contents = contents_dict[filename]
        except KeyError:
            raise FileNotFoundError(filename)
        file_object = mock_open(read_data=contents).return_value
        return file_object
    return open_contents


# class NiiExporter:
#
#     def test_split_series_doesnt_export_same_file_with_two_names(self):
#         assert False
