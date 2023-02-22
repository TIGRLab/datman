import pytest
from mock import Mock, patch

import datman.exporters as exporters


class TestNiiLinkExporter:

    # Needs:
    #   - list of expected tags with 'Bids' config
    #   - experiment.name in case of error
    #   - dict of {TAG: [names]} for datman matches
    #   - list of full path bids file names (all rooted in a folder, no ext)

    def test_match_dm_to_bids_correctly_matches_t1_anat(self, config):

        assert False

    # def test_match_dm_to_bids_works_when_tag_count_greater_than_one(self):
    #     assert False
    #
    # def test_match_dm_to_bids_matches_split_series_correctly(self):
    #     assert False
    #
    # def test_match_dm_to_bids_matches_files_when_dm_name_not_assigned(self):
    #     assert False
    #
    # def test_match_dm_to_bids_doesnt_match_unneeded_files(self):
    #     # Must match CBF with unknown description, but not accidentally
    #     # grab other random series
    #     assert False

    # def test_sidecars_and_other_files_get_links_if_nii_does(self):
    #     assert False
    @pytest.fixture
    def config(self):
        """Create a mock datman config object, with tags defined.
        """
        test_tags = {
            'T1': {
                'Bids': {'class': 'anat', 'modality_label': 'T1w'},
                'Pattern': 'T1',
                'Count': 1
            },
        }

        config = Mock()
        config.get_tags = lambda x: test_tags

    @pytest.fixture
    def experiment(self):
        exp = Mock()
        exp.name = 'STUDY01_CMH_0000_01_01'

        return exp


# class NiiExporter:
#
#     def test_split_series_doesnt_export_same_file_with_two_names(self):
#         assert False
