import os.path
import unittest
import importlib
import nose.tools
from nose.tools import raises
import subprocess as proc

fs = importlib.import_module('bin.dm-proc-freesurfer')

FIXTURE_DIR = "tests/fixture_dm-proc-freesurfer"

def test_get_qced_subject_list():
    checklist = os.path.join(FIXTURE_DIR, "metadata/checklist.csv")
    sublist = fs.get_qced_subject_list(checklist)

    actual_qced = ["STUDY_SITE_CODE_01", "PHAIL_SITE_CODE_01", "STUDY_CAMH_CODE_01"]
    extra_subs = list(set(sublist) - set(actual_qced))

    assert extra_subs == []
    assert "STUDY_SITE_CODE_01" in sublist
    assert "PHAIL_SITE_CODE_01" in sublist
    assert "STUDY_CAMH_CODE_01" in sublist

@raises(SystemExit)
def test_get_qced_subject_list_catches_nonexistent_checklist():
    bad_path = os.path.join(FIXTURE_DIR, "metadata/does-not-exist.csv")
    sublist = fs.get_qced_subject_list(bad_path)

    assert sublist == 1

def test_get_subject_list_removes_phantoms():
    inputdir = os.path.join(FIXTURE_DIR, "data/nii")
    subjects = fs.get_subject_list(inputdir, None, None)

    assert "STUDY_SITE_CODE_PHA_03" not in subjects

def test_get_subject_list_removes_nonphantom_PHA_subid():
    ## It's a known issue that datman removes all subids with
    ## any occurence of 'PHA' when removing phantoms. This test is
    ## here as a reminder that this behavior is shown in this module.
    ## Rewrite/remove this test if this behavior is corrected.
    inputdir = os.path.join(FIXTURE_DIR, "data/nii")
    subjects = fs.get_subject_list(inputdir, None, None)

    assert "PHAIL_SITE_CODE_01" not in subjects

def test_get_subject_list_tag2_returns_only_tagged_subjects():
    inputdir = os.path.join(FIXTURE_DIR, "data/nii")
    subjects = fs.get_subject_list(inputdir, "CAMH", None)

    assert subjects == ["STUDY_CAMH_CODE_01"]

def test_get_subject_list_QC_file_returns_only_qced_subjects():
    inputdir = os.path.join(FIXTURE_DIR, "data/nii")
    checklist = os.path.join(FIXTURE_DIR, "metadata/checklist.csv")

    subjects = fs.get_subject_list(inputdir, None, checklist)
    actual_subjects = ["STUDY_SITE_CODE_01", "STUDY_CAMH_CODE_01"]
    extra_subs = list(set(subjects) - set(actual_subjects))

    assert extra_subs == []
    assert "STUDY_SITE_CODE_01" in subjects
    assert "STUDY_CAMH_CODE_01" in subjects

### Make integration tests on main?
def test_get_run_script_names():
    tag = 'TAG'
    only_post = False
    no_post = False

    run_scripts = fs.get_run_script_names(tag, only_post, no_post)
    assert run_scripts == ['run_freesurfer_TAG.sh', 'postfreesurfer.sh']
    tag = None

    only_post = True
    run_scripts = fs.get_run_script_names(tag, only_post, no_post)
    assert run_scripts == ['postfreesurfer.sh']
    only_post = False

    no_post = True
    run_scripts = fs.get_run_script_names(tag, only_post, no_post)
    assert run_scripts == ['run_freesurfer.sh']

@raises(SystemExit)
def test_postFS_settings_resolved():
    assert True == False
