import importlib
import unittest
import copy
import logging

# Disable all logging output for tests
logging.disable(logging.CRITICAL)

link_shared = importlib.import_module('bin.dm_link_shared_ids')


class TestRecord(unittest.TestCase):
    mock_redcap_record = {'par_id': 'STUDY_SITE_0001_01_01',
                          'record_id': 0,
                          'shared_parid_1': 'STUDY_SITE_0002_01_01',
                          'shared_parid_2': 'STUDY2_CMH_9999_01_01',
                          'shared_parid_8': 'OTHER_CMH_1234_01_01'}
    mock_kcni_record = {'par_id': 'STU01_ABC_0001_01_SE01_MR',
                        'record_id': 1,
                        'shared_parid_1': 'STU02_ABC_0002_01_SE01_MR',
                        'shared_parid_2': 'STUDY3_ABC_0003_01_SE01_MR'}
    mock_diff_fields_record = {'mri_sub_id': 'STU01_ABC_0001_01_SE01_MR',
                               'id': 2,
                               'shared_id': 'STU02_DEF_0002_04_SE01_MR'}

    def test_ignores_records_with_bad_subject_id(self):
        bad_redcap_record = {'par_id': 'STUDY_0001_01',
                             'record_id': 0,
                             'shared_parid_1': '',
                             'cmts': ''}

        record = link_shared.Record(bad_redcap_record)

        assert record.id is None
        assert record.study is None
        assert not record.matches_study('STUDY')

    def test_ignores_badly_named_shared_ids(self):
        bad_shared_id = copy.copy(self.mock_redcap_record)
        bad_id = 'STUDY_0001_01'
        bad_shared_id['shared_parid_4'] = bad_id

        record = link_shared.Record(bad_shared_id)

        assert bad_id not in [str(item) for item in record.shared_ids]

    def test_finds_all_shared_ids_in_record(self):
        record = link_shared.Record(self.mock_redcap_record)

        expected = [self.mock_redcap_record['shared_parid_1'],
                    self.mock_redcap_record['shared_parid_2'],
                    self.mock_redcap_record['shared_parid_8']]

        actual_ids = [str(item) for item in record.shared_ids]
        assert sorted(actual_ids) == sorted(expected)

    def test_correctly_handles_kcni_main_id(self):
        id_map = {
            'Study': {
                'STU01': 'STUDY',
            },
            'Site': {
                'ABC': 'SITE'
            }
        }

        record = link_shared.Record(self.mock_kcni_record, id_map)

        assert str(record.id) == 'STUDY_SITE_0001_01_01'

    def test_correctly_handles_kcni_shared_ids(self):
        id_map = {
            'Study': {
                'STU02': 'STUDY2',
            },
            'Site': {
                'ABC': 'SITE'
            }
        }

        record = link_shared.Record(self.mock_kcni_record, id_map)

        shared_ids = [str(item) for item in record.shared_ids]
        assert 'STUDY2_SITE_0002_01_01' in shared_ids

    def test_handles_nonstandard_field_names(self):
        id_map = {
            'Study': {
                'STU01': 'STUDY',
                'STU02': 'STUDY2'
            },
            'Site': {
                'ABC': 'SITE',
                'DEF': 'SITE2'
            }
        }

        record = link_shared.Record(
            self.mock_diff_fields_record,
            id_map,
            record_id_field='id',
            id_field='mri_sub_id',
            shared_id_prefix_field='shared_id')

        assert str(record.id) == 'STUDY_SITE_0001_01_01'
        shared_ids = [str(item) for item in record.shared_ids]
        assert 'STUDY2_SITE2_0002_04_01' in shared_ids

    def test_uses_default_for_misconfigured_record_id_field(self):
        id_map = {
            'Study': {
                'STU01': 'STUDY',
                'STU02': 'STUDY2'
            },
            'Site': {
                'ABC': 'SITE'
            }
        }

        record = link_shared.Record(
            self.mock_kcni_record,
            id_map,
            record_id_field='bad_record_id_field'
        )

        assert str(record.id) == 'STUDY_SITE_0001_01_01'

        shared_ids = [str(item) for item in record.shared_ids]
        assert 'STUDY2_SITE_0002_01_01' in shared_ids

    def test_uses_default_for_misconfigured_id_field(self):
        id_map = {
            'Study': {
                'STU01': 'STUDY',
                'STU02': 'STUDY2'
            },
            'Site': {
                'ABC': 'SITE'
            }
        }

        record = link_shared.Record(
            self.mock_kcni_record,
            id_map,
            id_field='bad_id_field'
        )

        assert str(record.id) == 'STUDY_SITE_0001_01_01'

        shared_ids = [str(item) for item in record.shared_ids]
        assert 'STUDY2_SITE_0002_01_01' in shared_ids
