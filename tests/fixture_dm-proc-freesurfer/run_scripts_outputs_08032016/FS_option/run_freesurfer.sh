#!/bin/bash

export SUBJECTS_DIR=/projects/dawn/current/datman/tests/fixture_dm-proc-freesurfer/output2

## Prints loaded modules to the log
module list

SUBJECT=${1}
shift
T1MAPS=${@}

recon-all -all -nondefault1 -nondefault2 -subjid ${SUBJECT} ${T1MAPS} -qcache
