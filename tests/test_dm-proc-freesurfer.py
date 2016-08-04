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


#########################################################################
# makeFreesurferrunsh

# def test_make_fs_runsh():
#     ## If the correct way to write the run scripts changes the fixtures
#     ## must be updated
#
#     ## Call makeFreesurferrunsh with FS
#     ## call with post
#
#     ## 1. New default runscript = fixture.
#     fix_sh = os.join(FIXTURE_DIR, "run_scripts_outputs_08032016/default_options/run_freesurfer.sh")
#     new_sh = fs.makeFreesurferrunsh("run_freesurfer.sh")
#     cmd = "diff {} {}".format(fix_sh, new_sh)
#     p = proc.Popen(cmd, shell=True, stdout=proc.PIPE, stderr=proc.PIPE)
#     out, err = p.communicate()
#     # No diffs, no output. None? empty list?
#     assert out == ""
#
#     ## 2. New post = fixture post
#     fix_sh = os.join(FIXTURE_DIR, "run_scripts_outputs_08032016/default_options/postfreesurfer.sh")
#     new_sh = fs.makeFreesurferrunsh("postfreesurfer.sh")
#     cmd = "diff {} {}".format(fix_sh, new_sh)
#     p = proc.Popen(cmd, shell=True, stdout=proc.PIPE, stderr=proc.PIPE)
#     out, err = p.communicate()
#     # No diffs, no output. None? empty list?
#     assert out == ""

    ## 3. New options set as
    # python ../bin/dm-proc-freesurfer.py --FS-option "-nondefault1 -nondefault2" --T1 /projects/dawn/current/datman/tests/fixture_dm-proc-freesurfer/data/nii /projects/dawn/current/datman/tests/fixture_dm-proc-freesurfer/output2
    ## equals the output for fixture fs_options

    ## 4. outputs are executable

#########################################################################
# generate run scripts

    # 1. respects POSTFS_ONLY (i.e. only creates post script)
    # 2. If old scripts, doesn't change them.

#########################################################################
# checkrunsh

    # If options differ returns message (equivalent to exit status == 1)
    # If no difference returns 0 (passes None)

#########################################################################
# RUN_TAG

#########################################################################
# POSTFS_ONLY

#########################################################################
# loadchecklist

    ## 1. No existing checklist. Check that dataframe id column == sublist (defaults)
    ## 2. Existing checklist passed in : make dataframe from it.
    ##      2a. Checklist == total sublist == no change to dataframe
    ##          (not to other columns either)
    ##      2b. Checklist == sublist of eligible subjects = old unchanged, new added.
    ##      2c. when tag2 set, checklist only updated with camh pt

#########################################################################
# find_T1images

    ## 1. If tag2 set, dataframe should only have file added for camh person
    ## 2.


# find_T1images:
    # If Tag2: doesn't add subid even if new if Tag2 not in nifti name
    # If nii field is empty, finds all new niftis and if multi allowed all added

# If postFS-only called, block that submits first job is skipped
    # Else
        # If has completed previously, does nothing (recon-all present)
        # If halted previously, adds checklist notes
        # Creates T1 array with -i fullpath to image for each image in T1_nii field

        # Check the command output... ?
        # Ensure date ran field is updated properly

# Post: check the command submitted

# Check output?
