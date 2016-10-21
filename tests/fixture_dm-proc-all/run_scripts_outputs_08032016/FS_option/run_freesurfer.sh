#!/bin/bash

export SUBJECTS_DIR=tests/fixture_dm-proc-all/run_scripts_outputs_08032016/FS_option

## Prints loaded modules to the log
module list

SUBJECT=${1}
shift
T1MAPS=${@}

recon-all -all -nondefault1 -nondefault2 -subjid ${SUBJECT} ${T1MAPS} -qcache
