import os
import unittest
import importlib
import logging

from mock import patch, mock_open

fs = importlib.import_module("bin.dm_proc_freesurfer")

logging.disable(logging.CRITICAL)

class TestGetFreesurferFolders(unittest.TestCase):

    @patch('os.path.exists')
    @patch('os.listdir')
    def test_doesnt_crash_when_bad_subject_names_given(self, mock_listdir,
            mock_exists):
        # To ensure subjects arent skipped for not existing
        mock_listdir.return_value = ['somefile.txt']
        qc_subjects = ['STUDY_CMH_ID_01_01', 'STUDY_CMH_SUBJECT12345',
                'STUDY_CMH_ID2_01_02']

        fs_folders = fs.get_freesurfer_folders('/some/path/freesurfer',
                qc_subjects)

        assert fs_folders

        selected_subjects = [os.path.basename(path) for path in fs_folders['CMH']]
        assert 'STUDY_CMH_SUBJECT12345' not in selected_subjects

    @patch('os.listdir')
    @patch('os.path.exists')
    def test_skips_subjects_with_no_outputs(self, mock_exists, mock_listdir):
        # Pretend all subjects exist
        mock_exists.return_value = True
        # Pretend only ID2 has outputs
        subject2 = 'STUDY_CMH_ID2_01_02'
        mock_listdir.side_effect = lambda path: ['somefile.txt'] if subject2 \
                in path else []
        qc_subjects = ['STUDY_CMH_ID_01_01', subject2, 'STUDY_CMH_ID3_01_01']

        fs_folders = fs.get_freesurfer_folders('/some/path/freesurfer',
                qc_subjects)

        assert fs_folders
        assert len(fs_folders['CMH']) == 1
        assert os.path.basename(fs_folders['CMH'][0]) == subject2
