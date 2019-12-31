import unittest
import logging
import importlib

from mock import patch

import datman.scanid

# Disable logging for tests
logging.disable(logging.CRITICAL)

link_scans = importlib.import_module('bin.dm_link_project_scans')


class CopyChecklistEntry(unittest.TestCase):
    source = datman.scanid.parse("STUDY_CMH_ID1_01_01")
    target = datman.scanid.parse("STUDY2_CMH_ID2_01_01")
    path = "./target_checklist.csv"

    @patch('datman.utils.update_checklist')
    @patch('datman.utils.read_checklist')
    def test_does_nothing_when_target_checklist_has_entry(self,
                                                          mock_read,
                                                          mock_update):
        mock_read.side_effect = lambda subject=None: \
                {self.target: "signed_off",
                 self.source: "signed_off"}[subject]

        link_scans.copy_checklist_entry(self.source, self.target, self.path)

        assert mock_update.call_count == 0

    @patch('datman.utils.update_checklist')
    @patch('datman.utils.read_checklist')
    def test_does_nothing_when_no_relevant_entries_in_source(self,
                                                             mock_read,
                                                             mock_update):
        mock_read.return_value = None

        link_scans.copy_checklist_entry(self.source, self.target, self.path)

        assert mock_update.call_count == 0

    @patch('datman.utils.update_checklist')
    @patch('datman.utils.read_checklist')
    def test_updates_with_correct_entry(self, mock_read, mock_update):
        comment = "signed_off"
        mock_read.side_effect = lambda subject=None: \
            {self.source: comment,
             self.target: None}[subject]

        link_scans.copy_checklist_entry(self.source, self.target, self.path)

        expected_entry = {self.target: comment}

        assert mock_update.call_count == 1
        mock_update.assert_called_once_with(expected_entry, path=self.path)


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

    @patch('datman.utils.update_blacklist')
    @patch('datman.utils.read_blacklist')
    def test_does_nothing_without_source_blacklist_entries_to_copy(
                self,
                mock_read,
                mock_update):

        mock_read.return_value = {}

        link_scans.copy_blacklist_data(self.source, self.source_list,
                                       self.target, self.target_list,
                                       self.tags)

        assert mock_update.call_count == 0

    @patch('datman.utils.update_blacklist')
    @patch('datman.utils.read_blacklist')
    def test_does_nothing_if_all_entries_present_in_target_blacklist(
                self,
                mock_read,
                mock_update):

        post_fix = "_DTI60_05_Ax-DTI-60plus5"

        def mock_blacklist(subject, path):
            if path == self.target_list and subject == self.target:
                return {self.target + post_fix: '--corrupted'}
            if path == self.source_list and subject == self.source:
                return {self.source + post_fix: '--corrupted'}
            return {}

        mock_read.side_effect = mock_blacklist
        link_scans.copy_blacklist_data(self.source, self.source_list,
                                       self.target, self.target_list,
                                       self.tags)

        assert mock_update.call_count == 0

    @patch('datman.utils.update_blacklist')
    @patch('datman.utils.read_blacklist')
    def test_adds_missing_entries_with_matched_tags(self,
                                                    mock_read,
                                                    mock_update):

        fname1 = "_DTI60_05_Ax-DTI-60plus5"
        fname2 = "_T1_06_SagT1Bravo"
        fname3 = "_PDT2_07_OblAx-T2DEfseXL"
        comments = ["--corrupted", "", "--corrupted"]

        def mock_blacklist(subject, path):
            if path == self.target_list and subject == self.target:
                return self._make_entries(self.target,
                                          [fname1], comments)
            if path == self.source_list and subject == self.source:
                return self._make_entries(self.source,
                                          [fname1, fname2, fname3],
                                          comments)
            return {}

        mock_read.side_effect = mock_blacklist

        link_scans.copy_blacklist_data(self.source, self.source_list,
                                       self.target, self.target_list,
                                       self.tags)

        missing_entries = self._make_entries(self.target,
                                             [fname2],
                                             [""])

        assert mock_update.call_count == 1
        mock_update.assert_called_once_with(missing_entries,
                                            path=self.target_list)

    def _make_entries(self, subject, fnames, comments):
        entries = {}
        for num, fname in enumerate(fnames):
            entries[subject + fname] = comments[num]
        return entries
