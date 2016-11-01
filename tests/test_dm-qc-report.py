import unittest
import importlib

import nose.tools
from mock import patch, mock_open, call

qc = importlib.import_module('bin.dm-qc-report')

@patch('os.listdir')
@patch('bin.dm-qc-report.make_qc_command')
@patch('bin.dm-qc-report.submit_qc_jobs')
@patch('datman.utils.run')
def test_qc_all_scans_handles_phantoms_and_subjects(mock_run, mock_submit,
        mock_cmd, mock_dirs):
    """
    Tests that qc_all_scans submits subjects to the queue but runs phantoms
    directly with datman.utils.run
    """
    config_file = qc_all_scans_setup(mock_run, mock_dirs, mock_cmd)

    qc.qc_all_scans('/data/nii', config_file)

    # Expected calls to submit_qc_jobs should include subjects only
    expected = ['dm-qc-report.py {} --subject STUDY_SITE_0001_01'.format(config_file),
                'dm-qc-report.py {} --subject STUDY_SITE_0002_01'.format(config_file)]
    mock_submit.assert_called_once_with(expected)

    # Expected calls to datman.utils.run should include phantoms only
    phantom1 = 'dm-qc-report.py {} --subject STUDY_SITE_PHA_0001'.format(config_file)
    phantom2 = 'dm-qc-report.py {} --subject STUDY_SITE_PHA_0002'.format(config_file)
    calls = [call(phantom1), call(phantom2)]
    assert mock_run.call_count == 2
    mock_run.assert_has_calls(calls, any_order=True)

@patch('time.strftime')
@patch('datman.utils.run')
def test_submit_qc_jobs(mock_run, mock_time):
    time = '19001231-23:59:59'
    mock_time.return_value = time
    # Prevents a ValueError from trying to access return and out of utils.run
    mock_run.return_value = (0, '')

    commands = ['dm-qc-report.py config_file.yaml --subject STUDY_SITE_ID_01']
    qc.submit_qc_jobs(commands)

    job_name = 'qc_report_{}_0'.format(time)
    expected = 'echo {} | qsub -V -q main.q -o ' \
            '/tmp/{job}.log -e /tmp/{job}.err -N {job}'.format(commands[0],
                    job=job_name)

    mock_run.assert_called_once_with(expected)

@patch('glob.glob')
@patch('datman.utils.run')
def test_run_header_qc_does_nothing_with_empty_dicom_dir(mock_run, mock_glob):
    """
    Checks that run_header_qc doesn't crash or behave badly with an empty dicom
    directory
    """
    dicoms, standards, log = run_header_qc_setup()

    mock_glob.side_effect = lambda path: {
         './dicoms/subject_id/*': [],
         './standards/*': ['SITE_CAMH_0001_01_01_T1_02_SagT1-BRAVO.dcm']
         }[path]

    qc.run_header_qc(dicoms, standards, log)
    assert mock_run.call_count == 0

@patch('glob.glob')
@patch('datman.utils.run')
def test_run_header_qc_does_nothing_without_matching_standards(mock_run,
        mock_glob):
    """
    Checks that run_header_qc doesn't crash or behave badly without standards
    """
    dicoms, standards, log = run_header_qc_setup()

    mock_glob.side_effect = lambda path: {
        './dicoms/subject_id/*': ['./dicoms/subject_id/' \
                'STUDY_SITE1_0002_01_01_OBS_09_Ax-Observe-Task.dcm'],
        './standards/*': ['./standards/' \
                'SITE_CAMH_0001_01_01_T1_02_SagT1-BRAVO.dcm']
        }[path]

    qc.run_header_qc(dicoms, standards, log)
    assert mock_run.call_count == 0

@patch('glob.glob')
@patch('datman.utils.run')
def test_run_header_qc_makes_expected_qcmon_call(mock_run, mock_glob):
    dicoms, standards, log = run_header_qc_setup()

    mock_glob.side_effect = lambda path: {
        './dicoms/subject_id/*': ['./dicoms/subject_id/' \
                'STUDY_CAMH_0001_01_01_OBS_09_Ax-Observe-Task.dcm',
                './dicoms/subject_id/STUDY_CAMH_0001_01_01_T1_02_SagT1-BRAVO.dcm'],
        './standards/*': ['./standards/' \
                'STUDY_CAMH_9999_01_01_T1_99_SagT1-BRAVO.dcm']
        }[path]
    qc.run_header_qc(dicoms, standards, log)

    matched_dicom = './dicoms/subject_id/' \
            'STUDY_CAMH_0001_01_01_T1_02_SagT1-BRAVO.dcm'
    matched_standard = './standards/' \
            'STUDY_CAMH_9999_01_01_T1_99_SagT1-BRAVO.dcm'
    log_dir = './qc/subject_id/header-diff.log'

    expected = 'qc-headers {} {} {}'.format(matched_dicom,
            matched_standard, log_dir)

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
    assert arg_list == [call(checklist, 'r'), call(checklist, 'a')]
    checklist_mock().write.assert_called_once_with(report + "\n")


def test_add_report_to_checklist_doesnt_repeat_entry():
    checklist, checklist_data = add_report_to_checklist_set_up()

    report = "qc_subject1.html"
    call_count, arg_list, checklist_mock = mock_add_report(report,
            checklist, checklist_data)

    assert call_count == 1
    assert arg_list == [call(checklist, 'r')]
    assert not checklist_mock().write.called

def test_add_report_to_checklist_doesnt_repeat_qced_entry():
    checklist, checklist_data = add_report_to_checklist_set_up()

    report = "qc_subject2.html"
    call_count, arg_list, checklist_mock = mock_add_report(report,
            checklist, checklist_data)

    assert call_count == 1
    assert arg_list == [call(checklist, 'r')]
    assert not checklist_mock().write.called

def test_add_report_to_checklist_doesnt_repeat_entry_with_new_extension():
    checklist, checklist_data = add_report_to_checklist_set_up()

    report = "qc_subject5.html"
    call_count, arg_list, checklist_mock = mock_add_report(report,
            checklist, checklist_data)

    assert call_count == 1
    assert arg_list == [call(checklist, 'r')]
    assert not checklist_mock().write.called

###################################################################
# Helper functions
def qc_all_scans_setup(mock_run, mock_dirs, mock_cmd):
    config_file = './site_config.yaml'
    # Prevents a ValueError from trying to access return and out of utils.run
    mock_run.return_value = (0, '')
    mock_dirs.return_value = ['/data/nii/STUDY_SITE_0001_01',
                              '/data/nii/STUDY_SITE_PHA_0001',
                              '/data/nii/STUDY_SITE_PHA_0002',
                              '/data/nii/STUDY_SITE_0002_01']
    mock_cmd.side_effect = lambda subject, config: 'dm-qc-report.py {} ' \
            '--subject {}'.format(config, subject)

    return config_file

def run_header_qc_setup():
    dicom_dir = './dicoms/subject_id'
    standard_dir = './standards'
    log_file = './qc/subject_id/header-diff.log'
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
