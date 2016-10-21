#!/bin/bash

export SUBJECTS_DIR=tests/fixture_dm-proc-all/run_scripts_outputs_08032016/default_options

## Prints loaded modules to the log
module list

SUBJECT=${1}
shift
T1MAPS=${@}

recon-all -all -subjid ${SUBJECT} ${T1MAPS} -qcache
