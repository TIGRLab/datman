import os
import unittest
import importlib
import logging
import zipfile

from nose.tools import raises
from mock import patch, MagicMock

import datman
import datman.xnat
import datman.scanid

# Disable all logging for the duration of testing
logging.disable(logging.CRITICAL)

upload = importlib.import_module('bin.dm_xnat_upload')
FIXTURE = "tests/fixture_xnat_upload/"


class CheckFilesExist(unittest.TestCase):
    ident = datman.scanid.parse("STUDY_SITE_9999_01_01")
    archive = "some_dir/STUDY_SITE_9999_01_01.zip"
    session = FIXTURE + "xnat_session.txt"
    session_no_resources = FIXTURE + "xnat_session_missing_resources.txt"
    session_missing_data = FIXTURE + "xnat_session_missing_scan_data.txt"
    archive_scan_uids = [
            '1.2.840.113619.2.336.4120.8413787.19465.1412083372.445',
            '1.2.840.113619.2.336.4120.8413787.19465.1412083372.444',
            '1.2.840.113619.2.336.4120.8413787.19465.1412083372.447',
            '1.2.840.113619.2.336.4120.8413787.19465.1412083372.446',
            '1.2.840.113619.2.336.4120.8413787.19465.1412083372.440',
            '1.2.840.113619.2.80.142631515.25030.1412106144.3.0.2',
            '1.2.840.113619.2.336.4120.8413787.19465.1412083372.443',
            '1.2.840.113619.2.336.4120.8413787.19465.1412083372.442',
            '1.2.840.113619.2.5.18242516414121059301412105930313000',
            '1.2.840.113619.2.80.142631515.25030.1412106138.1.0.2']
    archive_experiment_id = '1.2.840.113619.6.336.' \
                             '254801968553430904107911738210738061468'

    @raises(Exception)
    @patch('bin.dm_xnat_upload.missing_resource_data')
    @patch('datman.utils.get_archive_headers')
    def test_raises_exception_if_scan_uids_mismatch(self, mock_headers,
                mock_missing_resources):
        # Set up
        mock_headers.return_value = self.__generate_mock_headers(bad_id=True)
        mock_missing_resources.return_value = False
        xnat_session = self.__get_xnat_session(self.session)

        # Run
        files_exist = upload.check_files_exist(self.archive, xnat_session,
                                               self.ident)

        # Should raise an exception, so assertion is never reached
        assert False

##### To do:
    # Test that false is returned when a resource is missing, or when a scan is
    # missing

    def __generate_mock_headers(self, bad_id=False):
        headers = {}
        for num, item in enumerate(self.archive_scan_uids):
            scan = MagicMock()
            scan.SeriesInstanceUID = item
            scan.StudyInstanceUID = self.archive_experiment_id
            headers[num] = scan
        if bad_id:
            bad_scan = headers[0]
            bad_scan.StudyInstanceUID = '1.1.111.111111.1.111.111111111111111'
            headers[0] = bad_scan
        return headers

    def __get_xnat_session(self, text_file):
        with open(text_file, 'r') as session_data:
            xnat_session = eval(session_data.read())
        return xnat_session

class GetResources(unittest.TestCase):
    name_list = ['some_zipfile_name/',
                 'some_zipfile_name/dicom_file1.dcm',
                 'some_zipfile_name/dicom_file2.dcm',
                 'some_zipfile_name/bvals.txt',
                 'some_zipfile_name/gradOrs.txt',
                 'some_zipfile_name/dicom_file3.dcm',
                 'some_zipfile_name/Name_info.txt',
                 'some_zipfile_name/subjectid_EmpAcc.log']

    @patch('bin.dm_xnat_upload.is_dicom')
    @patch('io.BytesIO')
    def test_returns_all_resources(self, mock_IO, mock_isdicom):
        # Set up inputs
        archive_zip = MagicMock(spec=zipfile.ZipFile)
        archive_zip.return_value.namelist.return_value = self.name_list
        expected_resources = ['some_zipfile_name/bvals.txt',
                              'some_zipfile_name/gradOrs.txt',
                              'some_zipfile_name/Name_info.txt',
                              'some_zipfile_name/subjectid_EmpAcc.log']

        # Stop get_resources from verifying 'dicoms' in the mock zipfile
        archive_zip.return_value.read.side_effect = lambda x: x
        mock_IO.side_effect = lambda x: x
        mock_isdicom.side_effect = lambda x: True if '.dcm' in x else False

        actual_resources = upload.get_resources(archive_zip.return_value)

        assert sorted(actual_resources) == sorted(expected_resources)
