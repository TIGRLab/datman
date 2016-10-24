#!/usr/bin/env python
"""
Tests for datman/proc.py
"""

import os
import unittest

import nose.tools
from nose.tools import raises

import datman.proc as proc

FIXTURE_DIR = "tests/fixture_dm-proc-all"

def test_get_qced_subjects():
    checklist = os.path.join(FIXTURE_DIR, "metadata/checklist.csv")
    sublist = proc.get_qced_subjects(checklist)

    actual_qced = ["STUDY_SITE_CODE_01", "PHAIL_SITE_CODE_01",
        "STUDY_CAMH_CODE_01"]
    extra_subs = list(set(sublist) - set(actual_qced))

    assert extra_subs == []
    assert "STUDY_SITE_CODE_01" in sublist
    assert "PHAIL_SITE_CODE_01" in sublist
    assert "STUDY_CAMH_CODE_01" in sublist

@raises(SystemExit)
def test_get_qced_subject_list_exits_with_nonexistent_checklist():
    bad_path = os.path.join(FIXTURE_DIR, "metadata/does-not-exist.csv")
    sublist = proc.get_qced_subjects(bad_path)

def test_get_subject_list_removes_phantoms():
    inputdir = os.path.join(FIXTURE_DIR, "data/nii")
    subjects = proc.get_subject_list(inputdir, None, None)

    assert "STUDY_SITE_CODE_PHA_03" not in subjects

def test_get_subject_list_removes_nonphantom_PHA_subid():
    ## It's a known issue that datman removes all subids with
    ## any occurence of 'PHA' when removing phantoms. This test is
    ## here as a reminder that this behavior is shown in this module.
    ## Rewrite/remove this test if this behavior is corrected.
    inputdir = os.path.join(FIXTURE_DIR, "data/nii")
    subjects = proc.get_subject_list(inputdir, None, None)

    assert "PHAIL_SITE_CODE_01" not in subjects

def test_get_subject_list_tag2_returns_only_tagged_subjects():
    inputdir = os.path.join(FIXTURE_DIR, "data/nii")
    subjects = proc.get_subject_list(inputdir, "CAMH", None)

    assert subjects == ["STUDY_CAMH_CODE_01"]

def test_get_subject_list_QC_file_returns_only_qced_subjects():
    inputdir = os.path.join(FIXTURE_DIR, "data/nii")
    checklist = os.path.join(FIXTURE_DIR, "metadata/checklist.csv")

    subjects = proc.get_subject_list(inputdir, None, checklist)
    actual_subjects = ["STUDY_SITE_CODE_01", "STUDY_CAMH_CODE_01"]
    extra_subs = list(set(subjects) - set(actual_subjects))

    assert extra_subs == []
    assert "STUDY_SITE_CODE_01" in subjects
    assert "STUDY_CAMH_CODE_01" in subjects

def test_add_new_subjects_to_checklist():
    columns = ['id', 'T1_nii', 'date_ran','qc_rator', 'qc_rating', 'notes']

    checklist_path = os.path.join(FIXTURE_DIR, "empty_checklist.csv")
    checklist = proc.load_checklist(checklist_path, columns)
    assert checklist.id.empty == True

    subjects = ["subject_1", "subject_2"]
    checklist = proc.add_new_subjects_to_checklist(subjects, checklist, columns)
    assert checklist.id.tolist() == ["subject_1", "subject_2"]

    subjects2 = ["subject_4", "subject_2", "subject_3"]
    checklist = proc.add_new_subjects_to_checklist(subjects2, checklist, columns)
    assert checklist.id.tolist() == ["subject_1", "subject_2",
                                     "subject_4", "subject_3"]

def test_find_images_finds_T1s():
    checklist, input_dir = find_images_setup()

    # T1_nii is initially empty
    assert checklist.T1_nii.dropna().tolist() == []

    checklist = proc.find_images(checklist, 'T1_nii', input_dir, '_T1_')

    expected = ['STUDY_CAMH_CODE_01_01_T1_02_SagT1-BRAVO.nii.gz',
                'STUDY_SITE_CODE_02_01_T1_SagT1Bravo-9mm.nii.gz',
                '> 1 _T1_ found']
    actual = checklist.T1_nii.dropna().tolist()
    assert actual == expected

def test_find_images_finds_subject_filtered_T1s():
    checklist, input_dir = find_images_setup()

    # T1_nii is initially empty
    assert checklist.T1_nii.dropna().tolist() == []

    subject_filter = 'CAMH'
    checklist = proc.find_images(checklist, 'T1_nii', input_dir,  '_T1_',
        subject_filter)

    expected = ['STUDY_CAMH_CODE_01_01_T1_02_SagT1-BRAVO.nii.gz']
    actual = checklist.T1_nii.dropna().tolist()
    assert  actual == expected

def test_find_images_finds_image_filtered_T1s():
    checklist, input_dir = find_images_setup()

    # T1_nii is initially empty
    assert checklist.T1_nii.dropna().tolist() == []

    image_filter = '9mm'
    checklist = proc.find_images(checklist, 'T1_nii', input_dir,  '_T1_',
        image_filter=image_filter)

    expected = ['No _T1_ found.',
                'STUDY_SITE_CODE_02_01_T1_SagT1Bravo-9mm.nii.gz',
                'STUDY_SITE_CODE_01_01_T1_02_SagT1Bravo-9mm.nii.gz']
    actual = checklist.T1_nii.dropna().tolist()
    assert  actual == expected

def test_find_images_allows_multiple_images():
    checklist, input_dir = find_images_setup()

    # T1_nii is initially empty
    assert checklist.T1_nii.dropna().tolist() == []

    checklist = proc.find_images(checklist, 'T1_nii', input_dir, '_T1_',
        allow_multiple=True)

    expected = ['STUDY_CAMH_CODE_01_01_T1_02_SagT1-BRAVO.nii.gz',
                'STUDY_SITE_CODE_02_01_T1_SagT1Bravo-9mm.nii.gz',
                'STUDY_SITE_CODE_01_01_T1_02_SagT1Bravo-9mm.nii.gz;STUDY_SITE_CODE_01_01_T1_03_SagT1.nii.gz']
    actual = checklist.T1_nii.dropna().tolist()
    assert actual == expected

#################################################################
## Helper Functions

def find_images_setup():
    input_dir = os.path.join(FIXTURE_DIR, "data/nii")
    subjects = proc.get_subject_list(input_dir, None, None)

    checklist_path = os.path.join(FIXTURE_DIR, "empty_checklist.csv")
    columns = ['id', 'T1_nii', 'date_ran','qc_rator', 'qc_rating', 'notes']
    checklist = proc.load_checklist(checklist_path, columns)

    checklist = proc.add_new_subjects_to_checklist(subjects, checklist, columns)

    return checklist, input_dir
