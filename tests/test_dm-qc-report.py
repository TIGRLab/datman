import os
import unittest
import importlib

import nose.tools
from mock import patch, mock_open

qc = importlib.import_module('bin.dm-qc-report')

FIXTURE_DIR = "tests/fixture_dm-qc-report"

@patch('datman.utils.run')
def test_run_header_qc_does_nothing_with_empty_dicom_dir(mock_run):
    """
    Checks that run_header_qc doesn't crash or behave badly under this condition
    """
    dicoms, standards, log = run_header_qc_setup("data/dcm/STUDY_SITE_0001_01")

    qc.run_header_qc(dicoms, standards, log)
    assert mock_run.call_count == 0

@patch('datman.utils.run')
def test_run_header_qc_does_nothing_without_matching_standards(mock_run):
    """
    Checks that run_header_qc doesn't crash or behave badly under this condition
    """
    dicoms, standards, log = run_header_qc_setup("data/dcm/STUDY_SITE_0002_01")

    qc.run_header_qc(dicoms, standards, log)
    assert mock_run.call_count == 0

@patch('datman.utils.run')
def test_run_header_qc_makes_expected_qcmon_call(mock_run):
    dicoms, standards, log = run_header_qc_setup("data/dcm/STUDY_CAMH_0001_01")
    qc.run_header_qc(dicoms, standards, log)

    d = 'tests/fixture_dm-qc-report/data/dcm/' \
            'STUDY_CAMH_0001_01/STUDY_CAMH_0001_01_01_T1_02_SagT1-BRAVO.dcm'
    s = 'tests/fixture_dm-qc-report/metadata/standards/' \
            'SITE_CAMH_0001_01_01_T1_02_SagT1-BRAVO.dcm'
    l = 'tests/fixture_dm-qc-report/data/dcm/' \
            'STUDY_CAMH_0001_01/header-diff.log'
    expected = 'qc-headers {} {} {}'.format(d, s, l)

    mock_run.assert_called_once_with(expected)

def test_add_report_to_checklist_updates_list():
    checklist, checklist_data = add_report_to_checklist_set_up()

    # With empty string, no update should be performed
    report = ""
    call_count, arg_list, _ = mock_add_report(report, checklist, checklist_data)

    assert call_count == 0
    assert arg_list == []

    # qc_subject3.html written to checklist, and nothing else
    report = "qc_subject3.html"
    call_count, arg_list, checklist_mock = mock_add_report(report,
            checklist, checklist_data)

    assert call_count == 2
    assert arg_list == [((checklist, 'r'),), ((checklist, 'a'),)]
    checklist_mock().write.assert_called_once_with(report + "\n")


def test_add_report_to_checklist_doesnt_repeat_entry():
    checklist, checklist_data = add_report_to_checklist_set_up()

    report = "qc_subject1.html"
    call_count, arg_list, checklist_mock = mock_add_report(report,
            checklist, checklist_data)

    assert call_count == 1
    assert arg_list == [((checklist, 'r'),)]
    assert not checklist_mock().write.called

def test_add_report_to_checklist_doesnt_repeat_qced_entry():
    checklist, checklist_data = add_report_to_checklist_set_up()

    report = "qc_subject2.html"
    call_count, arg_list, checklist_mock = mock_add_report(report,
            checklist, checklist_data)

    assert call_count == 1
    assert arg_list == [((checklist, 'r'),)]
    assert not checklist_mock().write.called

def test_add_report_to_checklist_doesnt_repeat_entry_with_new_extension():
    checklist, checklist_data = add_report_to_checklist_set_up()

    report = "qc_subject5.html"
    call_count, arg_list, checklist_mock = mock_add_report(report,
            checklist, checklist_data)

    assert call_count == 1
    assert arg_list == [((checklist, 'r'),)]
    assert not checklist_mock().write.called

###################################################################
# Helper functions

def run_header_qc_setup(path):
    dicom_dir = os.path.join(FIXTURE_DIR, path)
    standard_dir = os.path.join(FIXTURE_DIR, "metadata/standards")
    log_file = os.path.join(dicom_dir, "header-diff.log")
    return dicom_dir, standard_dir, log_file

def add_report_to_checklist_set_up():
    checklist = "./checklist.csv"
    checklist_data = ["qc_subject1.html\n", "qc_subject2.html   signed-off\n",
                      "qc_subject4.pdf\n", "qc_subject5\n"]

    return checklist, checklist_data

def mock_add_report(report, checklist, checklist_data):
    checklist_mock = mock_open(read_data=checklist_data)
    with patch("__builtin__.open", checklist_mock) as mock_file:
        # This line is needed because mock_open wont allow iteration
        # over a file handler otherwise
        mock_file.return_value.__iter__.return_value = checklist_data
        qc.add_report_to_checklist(report, checklist)

        return mock_file.call_count, mock_file.call_args_list, checklist_mock
