#!/bin/bash

# Master script for IMOB: IMOB.
# Generated: 2015/03/31 -- 15:23:07 by jdv.

## Setup
export DIR_PIPE=/projects/spins/code/epitome/150331-spins
export DIR_DATA=/projects/jdv/data/epitome/
export DIR_AFNI=/opt/quarantine/AFNI/2014.12.16/build
export DIR_EXPT=IMOB
export DATA_TYPE=IMOB
export ID=150331-spins

export PROC=proclist_150331_152307_150331-spins.sh
export CMD=cmd_150331_152307_150331-spins.sh

export AFNI_DECONFLICT=OVERWRITE
export SUBJECTS=$(python ${DIR_PIPE}/epitome/utilities.py ${DIR_DATA} ${DIR_EXPT})

## Freesurfer
epi-fsrecon ${DIR_DATA} ${DIR_EXPT} ${DATA_TYPE} ${DIR_DATA}/${DIR_EXPT}/${PROC}
. ${DIR_PIPE}/epitome/modules/freesurfer/fsexport ${DIR_DATA} ${DIR_EXPT} >> ${DIR_DATA}/${DIR_EXPT}/${PROC}

## Begin Pipeline
for SUB in ${SUBJECTS}; do

cat > ${DIR_DATA}/${DIR_EXPT}/${SUB}/${CMD} << EOF
export DIR_PIPE=${DIR_PIPE}
export DIR_DATA=${DIR_DATA}
export DIR_AFNI=${DIR_AFNI}
export DIR_EXPT=${DIR_EXPT}
export DATA_TYPE=${DATA_TYPE}
export ID=${ID}
export SUB=${SUB}
McRetroTS='/home/jdv/epitome/150331-spins/bin/run_McRetroTS.sh /opt/quarantine/matlab/matlab_concurrent_all/MATLAB_R2013b'
EOF

. ${DIR_PIPE}/epitome/modules/pre/init_epi high 0 on alt+z scale loose >> ${DIR_DATA}/${DIR_EXPT}/${SUB}/${CMD}
. ${DIR_PIPE}/epitome/modules/pre/linreg_calc_fsl high corratio 6 >> ${DIR_DATA}/${DIR_EXPT}/${SUB}/${CMD}
. ${DIR_PIPE}/epitome/modules/pre/nonlinreg_calc_fsl >> ${DIR_DATA}/${DIR_EXPT}/${SUB}/${CMD}
. ${DIR_PIPE}/epitome/modules/pre/linreg_fs2epi_fsl >> ${DIR_DATA}/${DIR_EXPT}/${SUB}/${CMD}
. ${DIR_PIPE}/epitome/modules/pre/filter scaled 4 on off off on 5 off >> ${DIR_DATA}/${DIR_EXPT}/${SUB}/${CMD}
. ${DIR_PIPE}/epitome/modules/pre/volsmooth filtered EPI_mask 8.0 normal >> ${DIR_DATA}/${DIR_EXPT}/${SUB}/${CMD}
. ${DIR_PIPE}/epitome/modules/pre/nonlinreg_epi2mni_fsl volsmooth 3.0 >> ${DIR_DATA}/${DIR_EXPT}/${SUB}/${CMD}

chmod 750 ${DIR_DATA}/${DIR_EXPT}/${SUB}/${CMD}
# append this subject to the process queue
echo bash ${DIR_DATA}/${DIR_EXPT}/${SUB}/${CMD} >> ${DIR_DATA}/${DIR_EXPT}/${PROC}
done

# calls to QC programs

