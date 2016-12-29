import unittest
import logging
import importlib

# Disable logging for tests
logging.disable(logging.CRITICAL)

link_scans = importlib.import_module('bin.dm-link-project-scans')

class CopyChecklistEntry(unittest.TestCase):
    def test_does_nothing_when_target_checklist_has_entry(self):
        assert False

    def test_does_nothing_when_no_relevant_entries_in_source(self):
        assert False

    def test_updates_with_correct_entry(self):
        assert False

class GetBlacklistScans(unittest.TestCase):
    def test_returns_expected_blacklist_entries(self):
        assert False

    def test_doesnt_crash_when_blacklist_doesnt_exist(self):
        assert False

    def test_updates_subjectid_in_found_entries_if_newid_given(self):
        assert False

class TagsMatch(unittest.TestCase):

    tags = ["T1", "PDT2", "DTI60"]

    def test_doesnt_crash_with_empty_line(self):
        entry = ""

        tags_match = link_scans.tags_match(entry, self.tags)
        assert tags_match is False

    def test_returns_false_with_unparseable_entry(self):
        assert False

    def test_returns_false_with_excluded_tag(self):
        assert False

    def test_returns_true_with_matching_tag(self):
        assert False

class CopyBlacklistData(unittest.TestCase):
    def test_does_nothing_without_relevant_source_blacklist_entries(self):
        assert False

    def test_does_nothing_if_all_entries_present_in_target_blacklist(self):
        assert False

    def test_adds_missing_entries_with_matched_tags(self):
        assert False
