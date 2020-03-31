import unittest
import importlib
import logging

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
        '1.2.840.113619.2.80.142631515.25030.1412106138.1.0.2'
    ]
    archive_experiment_id = '1.2.840.113619.6.336.' \
                            '254801968553430904107911738210738061468'

    @patch('bin.dm_xnat_upload.resource_data_exists')
    @patch('datman.utils.get_archive_headers')
    def test_raises_exception_if_scan_uids_mismatch(self, mock_headers,
                                                    mock_resources_exist):
        # Set up
        mock_headers.return_value = self.__generate_mock_headers(bad_id=True)
        mock_resources_exist.return_value = True
        xnat_session = self.__get_xnat_session(self.session)

        xnat = MagicMock()

        # Run
        data_exists, resources_exist = upload.check_files_exist(
            self.archive, xnat_session.experiments["STUDY_SITE_9999_01_01"],
            xnat)

        # Should raise an exception, so assertion is never reached
        assert data_exists
        assert resources_exist

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
        return datman.xnat.XNATSubject(xnat_session)
