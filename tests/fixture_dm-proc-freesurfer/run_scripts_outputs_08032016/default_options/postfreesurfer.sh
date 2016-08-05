#!/bin/bash

export SUBJECTS_DIR=tests/fixture_dm-proc-freesurfer/run_scripts_outputs_08032016/default_options

## Prints loaded modules to the log
module list

ENGIMA_ExtractCortical.sh ${SUBJECTS_DIR} STU
ENGIMA_ExtractSubcortical.sh ${SUBJECTS_DIR} STU
