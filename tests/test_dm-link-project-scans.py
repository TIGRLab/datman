import os
import unittest
import logging
import importlib

from mock import patch, mock_open

import datman.scanid

# Disable logging for tests
logging.disable(logging.CRITICAL)

link_scans = importlib.import_module('bin.dm_link_project_scans')

class CopyChecklistEntry(unittest.TestCase):
    source = datman.scanid.parse("STUDY_CMH_ID1_01_01")
    target = datman.scanid.parse("STUDY2_CMH_ID2_01_01")
    path = "./target_checklist.csv"

    @patch('bin.dm_link_project_scans.update_file')
    @patch('datman.utils.check_checklist')
    def test_does_nothing_when_target_checklist_has_entry(self, mock_check,
            mock_update):
        mock_check.return_value = "signed off"

        link_scans.copy_checklist_entry(self.source, self.target, self.path)

        assert mock_update.call_count == 0

    @patch('bin.dm_link_project_scans.update_file')
    @patch('datman.utils.check_checklist')
    def test_does_nothing_when_no_relevant_entries_in_source(self, mock_check,
            mock_update):
        mock_check.return_value = None

        link_scans.copy_checklist_entry(self.source, self.target, self.path)

        assert mock_update.call_count == 0

    @patch('bin.dm_link_project_scans.update_file')
    @patch('datman.utils.check_checklist')
    def test_updates_with_correct_entry(self, mock_check, mock_update):
        comment = "signed off"
        target_id_timepoint = self.target.get_full_subjectid_with_timepoint()
        source_id_timepoint = self.source.get_full_subjectid_with_timepoint()
        mock_check.side_effect = lambda subid, study=None: {
                                  str(target_id_timepoint): None,
                                  str(source_id_timepoint): comment}[subid]

        link_scans.copy_checklist_entry(self.source, self.target, self.path)

        expected_entry = "qc_{}.html {}\n".format(target_id_timepoint, comment)

        assert mock_update.call_count == 1
        mock_update.assert_called_once_with(self.path, expected_entry)

    @patch('bin.dm_link_project_scans.delete_old_checklist_entry')
    @patch('bin.dm_link_project_scans.update_file')
    @patch('datman.utils.check_checklist')
    def test_no_repeats_when_checklist_entry_exists_but_not_signed_off(self,
            mock_check, mock_update, mock_delete):
        comment = "signed off"
        target_id_timepoint = self.target.get_full_subjectid_with_timepoint()
        source_id_timepoint = self.source.get_full_subjectid_with_timepoint()

        ## Currently datman.utils.check_comment is used to find checklist
        ## entries, and this function returns an empty string when there's
        ## an entry that's not signed off or None when there's no entry at all.
        ## Therefore: target_id_timepoint gives an empty string to indicate
        ## only the comment needs to be added
        mock_check.side_effect = lambda subid, study=None: {
                                  str(target_id_timepoint): '',
                                  str(source_id_timepoint): comment}[subid]

        link_scans.copy_checklist_entry(self.source, self.target, self.path)

        page_name = 'qc_{}.html'.format(target_id_timepoint)
        assert mock_delete.call_count == 1
        mock_delete.assert_called_once_with(self.path, page_name)

        expected_entry = "{} {}\n".format(page_name, comment)
        assert mock_update.call_count == 1
        mock_update.assert_called_once_with(self.path, expected_entry)

class GetBlacklistScans(unittest.TestCase):
    subject_id = "STUDY_SITE_0001_01_01"
    new_id = "STUDY2_SITE2_9999_01_01"
    blacklist_entries = ['STUDY_SITE_0002_01_01_TAG_NUM_DESCRIPTION --corrupted',
                         'STUDY_SITE_0001_01_01_TAG_01_DESCRIPTION --corrupted',
                         'STUDY_SITE_0005_01_01_TAG_NUM_DESCRIPTION',
                         'STUDY_SITE_0001_01_01_TAG_02_DESCRIPTION',
                         'STUDY_SITE_0001_01_02_TAG_03_DESCRIPTION --corrupted']

    def test_returns_only_matching_blacklist_entries(self):
        mock_blacklist = mock_open(read_data=self.blacklist_entries)
        with patch('__builtin__.open', mock_blacklist) as mock_stream:
            mock_stream.return_value.readlines.return_value = self.blacklist_entries
            actual = link_scans.get_blacklist_scans(self.subject_id,
                                                    './mock_blacklist.csv')

        expected = ['STUDY_SITE_0001_01_01_TAG_01_DESCRIPTION --corrupted',
                    'STUDY_SITE_0001_01_01_TAG_02_DESCRIPTION']

        assert sorted(actual) == sorted(expected)

    def test_doesnt_crash_when_blacklist_doesnt_exist(self):
        blacklist = "./fake_blacklist.csv"
        assert os.path.exists(blacklist) is False

        blacklist_scans = link_scans.get_blacklist_scans(self.subject_id,
                                                         './mock_blacklist.csv')

        assert blacklist_scans == []

    def test_updates_subjectid_in_found_entries_if_newid_given(self):
        mock_blacklist = mock_open(read_data=self.blacklist_entries)
        with patch('__builtin__.open', mock_blacklist) as mock_stream:
            mock_stream.return_value.readlines.return_value = self.blacklist_entries
            actual = link_scans.get_blacklist_scans(self.subject_id,
                                                    './mock_blacklist.csv',
                                                    new_id=self.new_id)

        expected = ['STUDY2_SITE2_9999_01_01_TAG_01_DESCRIPTION --corrupted',
                    'STUDY2_SITE2_9999_01_01_TAG_02_DESCRIPTION']

        assert sorted(actual) == sorted(expected)

class TagsMatch(unittest.TestCase):

    tags = ["T1", "PDT2", "DTI60"]

    def test_doesnt_crash_with_empty_line(self):
        entry = ""

        tags_match = link_scans.tags_match(entry, self.tags)

        assert tags_match is False

    def test_returns_false_with_unparseable_entry(self):
        entry = "BAD_ID_01_DTI60_15_Ax-DTI-60plus5 --corrupted-data"

        tags_match = link_scans.tags_match(entry, self.tags)

        assert tags_match is False

    def test_returns_false_with_excluded_tag(self):
        entry = "STUDY_SITE_ID_01_01_T2_num_description --corrupted-data"

        tags_match = link_scans.tags_match(entry, self.tags)

        assert tags_match is False

    def test_returns_true_with_matching_tag(self):
        entry = "STUDY_SITE_ID_01_01_DTI60_15_Ax-DTI-60plus5 --corrupted-data"

        tags_match = link_scans.tags_match(entry, self.tags)

        assert tags_match is True

class CopyBlacklistData(unittest.TestCase):
    source = 'STUDY_SITE_ID1_01_01'
    source_list = './fake_dir/blacklist1.csv'
    target = 'STUDY2_SITE_ID2_01_01'
    target_list = './fake_dir/blacklist2.csv'
    tags = ['T1', 'DTI60']

    @patch('bin.dm_link_project_scans.update_file')
    @patch('bin.dm_link_project_scans.get_blacklist_scans')
    def test_does_nothing_without_relevant_source_blacklist_entries(self,
                mock_scans, mock_update):
        target_entries = self._make_blacklist_entries(self.target,
                                ['_TAG_NUM_DESCRIPTION --COMMENT'])
        mock_scans.side_effect = lambda subid, fname,new_id=None: {
                                self.source: [],
                                self.target: target_entries}[subid]

        link_scans.copy_blacklist_data(self.source, self.source_list,
                                       self.target, self.target_list,
                                       self.tags)

        assert mock_update.call_count == 0

    @patch('bin.dm_link_project_scans.update_file')
    @patch('bin.dm_link_project_scans.get_blacklist_scans')
    def test_does_nothing_if_all_entries_present_in_target_blacklist(self,
                mock_scans, mock_update):
        entry = "_DTI60_05_Ax-DTI-60plus5 --corrupted"
        all_entries = self._make_blacklist_entries(self.source, [entry])
        target_entries = all_entries

        mock_scans.side_effect = lambda subid, fname, new_id=None: {
                                self.source: all_entries,
                                self.target: target_entries}[subid]

        link_scans.copy_blacklist_data(self.source, self.source_list,
                                       self.target, self.target_list,
                                       self.tags)

        assert mock_update.call_count == 0

    @patch('bin.dm_link_project_scans.update_file')
    @patch('bin.dm_link_project_scans.get_blacklist_scans')
    def test_adds_missing_entries_with_matched_tags(self, mock_scans,
                mock_update):
        entry1 = "_DTI60_05_Ax-DTI-60plus5 --corrupted"
        entry2 = "_T1_06_SagT1Bravo"
        entry3 = "_PDT2_07_OblAx-T2DEfseXL --corrupted"

        all_entries = self._make_blacklist_entries(self.target, [entry1,
                                                      entry2, entry3])
        target_entries = self._make_blacklist_entries(self.target, [entry1])

        mock_scans.side_effect = lambda subid, fname, new_id=None: {
                                self.source: all_entries,
                                self.target: target_entries}[subid]

        link_scans.copy_blacklist_data(self.source, self.source_list,
                                       self.target, self.target_list,
                                       self.tags)

        missing_entry = self._make_blacklist_entries(self.target, [entry2])[0]

        assert mock_update.call_count == 1
        mock_update.assert_called_once_with(self.target_list, missing_entry)

    def _make_blacklist_entries(self, subid, entry_list):
        entries = []
        for entry in entry_list:
            new_entry = subid + entry
            entries.append(new_entry)
        return entries
