import os
import unittest
import importlib

import nose.tools
from nose.tools import raises
import pandas as pd

import datman.utils
import datman.proc

fs = importlib.import_module('bin.dm-proc-freesurfer')

FIXTURE_DIR = "tests/fixture_dm-proc-all"

def test_make_FS_command():
    run_dir = FIXTURE_DIR
    sh_name = "test_command.sh"
    subid = "SUBJECT_1"
    T1s = ['T1_map1', 'T1_map2']
    job_name_prefix = "proc-freesurfer"
    log_dir = FIXTURE_DIR
    wall_time = "24:00:00"

    actual_command = fs.make_FS_command(run_dir, sh_name, job_name_prefix,
                                        log_dir, wall_time, subid, T1s)
    expected = 'echo "bash -l tests/fixture_dm-proc-all/test_command.sh '\
               'SUBJECT_1 T1_map1 T1_map2" | qbatch -N proc-freesurferSUBJECT_1 '\
               '--logdir tests/fixture_dm-proc-all --walltime 24:00:00 -'
    assert actual_command == expected

    actual_post_command = fs.make_FS_command(run_dir, sh_name, job_name_prefix,
                                             log_dir, wall_time)
    expected = 'echo "bash -l tests/fixture_dm-proc-all/test_command.sh" | '\
               'qbatch -N proc-freesurferpost '\
               '--logdir tests/fixture_dm-proc-all '\
               '--walltime 24:00:00 --afterok proc-freesurfer* -'
    assert actual_post_command == expected

def test_make_Freesurfer_runsh_default_options():
    ## If script format changes, update the fixtures with new examples of
    ## correct run scripts to make this test pass.
    fixture_path = os.path.join(FIXTURE_DIR,
                            "run_scripts_outputs_08032016/default_options")
    script_name = "run_freesurfer.sh"
    prefix = "STU"
    FS_option = None

    with datman.utils.make_temp_directory() as test_runsh_dir:
        test_runsh, out = make_scripts_and_check_diff(script_name,
                                test_runsh_dir, fixture_path, FS_option, prefix)

        ## No differences
        assert out == ""
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
        test_runsh, out = make_scripts_and_check_diff(script_name,
                            test_runsh_dir, fixture_path, FS_option, prefix)

        ## No differences
        assert out == ""
        ## Script has been made executable
        assert os.access(test_runsh, os.X_OK) == True

def test_make_Freesurfer_postsh():
    fixture_path = os.path.join(FIXTURE_DIR,
                            "run_scripts_outputs_08032016/default_options")
    script_name = "postfreesurfer.sh"
    prefix = "STU"
    FS_option = None

    with datman.utils.make_temp_directory() as test_runsh_dir:
        test_runsh, out = make_scripts_and_check_diff(script_name,
                                test_runsh_dir, fixture_path, FS_option, prefix)
        ## No differences
        assert out == ""
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

##########################################################################
### Helper functions

def make_scripts_and_check_diff(script_name, test_runsh_dir, fixture_path, FS_option, prefix):
    test_runsh = os.path.join(test_runsh_dir, script_name)
    correct_runsh = os.path.join(fixture_path, script_name)
    fs.make_Freesurfer_runsh(test_runsh, fixture_path, FS_option, prefix)
    cmd = "diff {} {}".format(test_runsh, correct_runsh)
    _, out = datman.utils.run(cmd)
    return test_runsh, out
