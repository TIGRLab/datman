import os
import unittest
import importlib
import logging

from mock import patch, mock_open

fs = importlib.import_module("bin.dm_proc_freesurfer")

logging.disable(logging.CRITICAL)

class TestGetRunScript(unittest.TestCase):

    @patch('os.path.isfile')
    def test_chooses_site_script_if_present(self, mock_isfile):
        # Pretend a site and a generic run script both exist
        mock_isfile.return_value = True

        run_script = fs.get_run_script('/some/path/freesurfer', 'CMH')

        assert run_script.endswith('_CMH.sh')

    @patch('os.path.isfile')
    def test_chooses_generic_script_if_site_script_unavailable(self, mock_isfile):
        # Pretend only a generic run script exists
        mock_isfile.side_effect = lambda x: True if x.endswith(
                'run_freesurfer.sh') else False

        run_script = fs.get_run_script('/some/path/freesurfer', 'CMH')

        assert run_script.endswith('run_freesurfer.sh')

    def test_returns_none_if_no_script_found(self):
        run_script = fs.get_run_script('/some/path/freesurfer', 'CMH')

        assert run_script is None

class TestGetSiteStandards(unittest.TestCase):

    @patch('bin.dm_proc_freesurfer.get_run_script')
    def test_returns_none_if_run_script_not_found(self, mock_get_run):
        mock_get_run.return_value = None

        site_standards = fs.get_site_standards('/some/path/freesurfer', 'CMH',
                '/some/path/freesurfer/SUBJECT12345')

        assert site_standards is None

    @patch('bin.dm_proc_freesurfer.get_run_script')
    def test_returns_none_if_recon_all_command_cant_be_read(self, mock_get_run):
        mock_get_run.return_value = '/some/path/bin/run_freesurfer.sh'

        # Mock an empty file
        mock_contents = mock_open(read_data=[])
        with patch("__builtin__.open", mock_contents) as mock_file:
            mock_file.return_value.readlines.return_value = []

            standards = fs.get_site_standards('/some/path/freesurfer', 'CMH',
                    '/some/path/freesurfer/SUBJECT12345')

        assert standards is None

    @patch('bin.dm_proc_freesurfer.get_run_script')
    def test_returns_none_if_no_arguments_read_from_recon_all(self,
            mock_get_run):
        mock_get_run.return_value = '/some/path/bin/run_freesurfer.sh'
        run_script_data = ['SUBJECT=${1}\n', 'shift\n', 'T1MAPS=${@}\n',
                'recon-all -subjid ${SUBJECT} ${T1MAPS}\n']

        mock_contents = mock_open(read_data=run_script_data)
        with patch("__builtin__.open", mock_contents) as mock_file:
            mock_file.return_value.readlines.return_value = run_script_data

            standards = fs.get_site_standards('/some/path/freesurfer', 'CMH',
                    'SUBJECT12345')

        assert standards is None

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
