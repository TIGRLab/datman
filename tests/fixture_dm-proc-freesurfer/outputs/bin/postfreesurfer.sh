#!/bin/bash

export SUBJECTS_DIR=/projects/dawn/current/datman/tests/fixture_dm-proc-freesurfer/outputs

## Prints loaded modules to the log
module list

ENGIMA_ExtractCortical.sh ${SUBJECTS_DIR} STU
ENGIMA_ExtractSubcortical.sh ${SUBJECTS_DIR} STU
