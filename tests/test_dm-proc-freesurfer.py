import os
import unittest
import importlib
import nose.tools
from nose.tools import raises
import mock
import subprocess as proc
import datman.utils
import pandas as pd


fs = importlib.import_module('bin.dm-proc-freesurfer')

FIXTURE_DIR = "tests/fixture_dm-proc-freesurfer"

def test_get_qced_subjects():
    checklist = os.path.join(FIXTURE_DIR, "metadata/checklist.csv")
    sublist = fs.get_qced_subjects(checklist)

    actual_qced = ["STUDY_SITE_CODE_01", "PHAIL_SITE_CODE_01", "STUDY_CAMH_CODE_01"]
    extra_subs = list(set(sublist) - set(actual_qced))

    assert extra_subs == []
    assert "STUDY_SITE_CODE_01" in sublist
    assert "PHAIL_SITE_CODE_01" in sublist
    assert "STUDY_CAMH_CODE_01" in sublist

@raises(SystemExit)
def test_get_qced_subject_list_exits_with_nonexistent_checklist():
    bad_path = os.path.join(FIXTURE_DIR, "metadata/does-not-exist.csv")
    sublist = fs.get_qced_subjects(bad_path)

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

def test_make_Freesurfer_runsh_default_options():
    ## If script format changes, update the fixtures with new examples of
    ## correct run scripts to make this test pass.
    fixture_path = os.path.join(FIXTURE_DIR,
                            "run_scripts_outputs_08032016/default_options")
    script_name = "run_freesurfer.sh"
    prefix = "STU"
    FS_option = None

    with datman.utils.make_temp_directory() as test_runsh_dir:
        test_runsh, out, err = make_scripts_and_check_diff(script_name,
                                test_runsh_dir, fixture_path, FS_option, prefix)

        ## No differences
        assert out == ""
        assert err == ""
        ## Script has been made executable
        assert os.access(test_runsh, os.X_OK) == True

def test_make_Freesurfer_runsh_FS_options_respected():
    ## If script format changes, update the fixtures with new examples of
    ## correct run scripts to make this test pass.
    fixture_path = os.path.join(FIXTURE_DIR,
                            "run_scripts_outputs_08032016/FS_option")
    script_name = "run_freesurfer.sh"
    prefix = "STU"
    FS_option = "-nondefault1 -nondefault2"

    with datman.utils.make_temp_directory() as test_runsh_dir:
        test_runsh, out, err = make_scripts_and_check_diff(script_name,
                                test_runsh_dir, fixture_path, FS_option, prefix)

        ## No differences
        assert out == ""
        assert err == ""
        ## Script has been made executable
        assert os.access(test_runsh, os.X_OK) == True

def test_make_Freesurfer_postsh():
    fixture_path = os.path.join(FIXTURE_DIR,
                            "run_scripts_outputs_08032016/default_options")
    script_name = "postfreesurfer.sh"
    prefix = "STU"
    FS_option = None

    with datman.utils.make_temp_directory() as test_runsh_dir:
        test_runsh, out, err = make_scripts_and_check_diff(script_name,
                                test_runsh_dir, fixture_path, FS_option, prefix)
        ## No differences
        assert out == ""
        assert err == ""
        ## Script has been made executable
        assert os.access(test_runsh, os.X_OK) == True

def test_check_runsh_does_nothing_if_options_unchanged():
    fixture_path = os.path.join(FIXTURE_DIR,
                            "run_scripts_outputs_08032016/default_options")
    old_script = os.path.join(fixture_path, "run_freesurfer.sh")
    FS_option = None
    prefix = "STU"

    last_modified_time = os.stat(old_script).st_mtime

    # Functions implicitly return None if there's no return statement.
    # Checks that check_runsh just exits if options haven't changed
    result = fs.check_runsh(old_script, fixture_path, FS_option, prefix)
    assert result == None

    # Script still exists
    assert os.path.exists(old_script) == True
    # Script unmodified
    assert os.stat(old_script).st_mtime == last_modified_time

@raises(SystemExit)
def test_check_runsh_raises_exit_if_options_changed():
    fixture_path = os.path.join(FIXTURE_DIR,
                            "run_scripts_outputs_08032016/default_options")
    old_script = os.path.join(fixture_path, "run_freesurfer.sh")
    FS_option = "-new_option"
    prefix = "STU"

    fs.check_runsh(old_script, fixture_path, FS_option, prefix)


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

def test_add_new_subjects_to_checklist():
    checklist_path = os.path.join(FIXTURE_DIR, "freesurfer_checklist.csv")
    checklist = fs.load_checklist(checklist_path)
    assert checklist.id.empty == True

    subjects = ["subject_1", "subject_2"]
    checklist = fs.add_new_subjects_to_checklist(subjects, checklist)
    assert checklist.id.tolist() == ["subject_1", "subject_2"]

    subjects2 = ["subject_4", "subject_2", "subject_3"]
    checklist = fs.add_new_subjects_to_checklist(subjects2, checklist)
    assert checklist.id.tolist() == ["subject_1", "subject_2",
                                     "subject_4", "subject_3"]

def test_update_T1_images_finds_T1s():
    checklist, inputdir = T1_images_setup()

    # T1_nii is initially empty
    assert checklist.T1_nii.dropna().tolist() == []

    checklist = fs.find_T1_images(checklist, '_T1_', None, inputdir, None)

    expected = ['STUDY_CAMH_CODE_01_01_T1_02_SagT1-BRAVO.nii.gz',
                'STUDY_SITE_CODE_02_01_T1_SagT1Bravo-9mm.nii.gz']
    actual = checklist.T1_nii.dropna().tolist()
    assert actual == expected

def test_find_T1_images_finds_TAG2_T1s():
    checklist, inputdir = T1_images_setup()

    # T1_nii is initially empty
    assert checklist.T1_nii.dropna().tolist() == []

    checklist = fs.find_T1_images(checklist, '_T1_', 'CAMH', inputdir, None)

    expected = ['STUDY_CAMH_CODE_01_01_T1_02_SagT1-BRAVO.nii.gz']
    actual = checklist.T1_nii.dropna().tolist()
    assert  actual == expected

def test_update_T1_images_respects_MULTI_tag():
    checklist, inputdir = T1_images_setup()

    # T1_nii is initially empty
    assert checklist.T1_nii.dropna().tolist() == []

    checklist = fs.find_T1_images(checklist, '_T1_', None, inputdir, True)

    expected = ['STUDY_CAMH_CODE_01_01_T1_02_SagT1-BRAVO.nii.gz',
                'STUDY_SITE_CODE_02_01_T1_SagT1Bravo-9mm.nii.gz',
                'STUDY_SITE_CODE_01_01_T1_02_SagT1Bravo-9mm.nii.gz;STUDY_SITE_CODE_01_01_T1_03_SagT1.nii.gz']
    actual = checklist.T1_nii.dropna().tolist()
    assert actual == expected

##########################################################################
### Helper functions

def make_scripts_and_check_diff(script_name, test_runsh_dir, fixture_path, FS_option, prefix):
    test_runsh = os.path.join(test_runsh_dir, script_name)
    correct_runsh = os.path.join(fixture_path, script_name)
    fs.make_Freesurfer_runsh(test_runsh, fixture_path, FS_option, prefix)
    cmd = "diff {} {}".format(test_runsh, correct_runsh)
    out, err = run_cmd(cmd)
    return test_runsh, out, err

def run_cmd(cmd):
    p = proc.Popen(cmd, shell=True, stdout=proc.PIPE, stderr=proc.PIPE)
    out, err = p.communicate()
    return out, err

def T1_images_setup():
    checklist_path = os.path.join(FIXTURE_DIR, "freesurfer_checklist.csv")
    checklist = fs.load_checklist(checklist_path)
    inputdir = os.path.join(FIXTURE_DIR, "data/nii")
    subjects = fs.get_subject_list(inputdir, None, None)
    checklist = fs.add_new_subjects_to_checklist(subjects, checklist)
    return checklist, inputdir
