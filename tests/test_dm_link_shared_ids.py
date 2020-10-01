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
                          'shared_parid_8': 'OTHER_CMH_1234_01_01',
                          'cmts': 'No comment.'}
    mock_kcni_record = {'par_id': 'STU01_ABC_0001_01_SE01_MR',
                        'record_id': 1,
                        'shared_parid_1': 'STU02_ABC_0002_01_SE01_MR',
                        'shared_parid_2': 'STUDY3_ABC_0003_01_SE01_MR',
                        'cmts': 'Test comment.'}

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

        assert bad_id not in record.shared_ids

    def test_finds_all_shared_ids_in_record(self):
        record = link_shared.Record(self.mock_redcap_record)

        expected = [self.mock_redcap_record['shared_parid_1'],
                    self.mock_redcap_record['shared_parid_2'],
                    self.mock_redcap_record['shared_parid_8']]

        assert sorted(record.shared_ids) == sorted(expected)

    def test_correctly_handles_kcni_main_id(self):
        id_map = {
            'STUDY': {
                'STU01': 'STUDY',
            },
            'SITE': {
                'ABC': 'SITE'
            }
        }

        record = link_shared.Record(self.mock_kcni_record, id_map)

        assert str(record.id) == 'STUDY_SITE_0001_01_01'

    def test_correctly_handles_kcni_shared_ids(self):
        id_map = {
            'STUDY': {
                'STU02': 'STUDY2',
            },
            'SITE': {
                'ABC': 'SITE'
            }
        }

        record = link_shared.Record(self.mock_kcni_record, id_map)

        assert 'STUDY2_SITE_0002_01_01' in record.shared_ids
