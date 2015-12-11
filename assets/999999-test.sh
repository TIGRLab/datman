#!/bin/bash
set -e
                                                                              
# This is a slightly-modified epitome script.                                   
# More on epitome here: https://github.com/josephdviviano/epitome               
# script generated on 2015-15-12                                          
                                                                                
# -----                                                                         
# init EPI (delete 4 TRs, despike, slice time correct == alt+z)                                                                   
# linreg_calc_FSL
# nonlinreg_calc_FSL
# linreg fs2epi                                                                 
# filter (ted method + compcor)
# lowpass (0.1 Hz, butterworth)
# volsmooth (blur2FWHM 10 mm)                                          
# nonlinreg_to_MNI (3 mm ISO)

module load matlab/R2013b_concurrent                                            
module load FSL/5.0.7                                                           
module load FIX/1.061                                                           
module load R/3.1.1                                                             
module load R-extras/3.1.1                                                      
module load AFNI/2014.12.16                                                     
module load freesurfer/5.3.0                                                    
module load python/2.7.9-anaconda-2.1.0-150119                                  
module load python-extras/2.7.8 

export DIR_DATA=${1}                                                            
export DELTR=${2}                                                               
                                                                                
# adds epitome to path
export DIR_PIPE='/archive/data-2.0/code/datman/assets/epitome/151012-spins'     
export PATH=${DIR_PIPE}'/bin':$PATH                        
export PYTHONPATH=${DIR_PIPE}:$PYTHONPATH

export DIR_AFNI=/opt/quarantine/AFNI/2014.12.16/build
export DIR_EXPT=TEMP
export DATA_TYPE=FUNC
export ID=DATMAN
export SUB=SUBJ

echo '*** MODULE: fakeout. I do what I want. ***'

# loop through sessions
DIR_SESS=`ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/`
for SESS in ${DIR_SESS}; do
    SESS=`basename ${SESS}`
    DIR=`echo ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}`
    DIR_T1=`echo ${DIR_DATA}/${DIR_EXPT}/${SUB}/T1`
    
    # make the output folder for the paramaters
    if [ ! -d ${SESS}/PARAMS ]; then
        mkdir ${SESS}/PARAMS
    fi

    # loop through runs
    DIR_RUNS=`ls -d -- ${SESS}/RUN*`
    for RUN in ${DIR_RUNS}; do
        NUM=`basename ${RUN} | sed 's/[^0-9]//g'`
        FILE=`echo ${RUN}/*.nii.gz`

        # fake functional data
        cp ${FILE} ${DIR}/${SESS}/func_MNI-nonlin.DATMAN.01.nii.gz

        # fake epi mask
        ${DIR_T1}/SESS01/anat_T1_brain.nii.gz ${DIR}/${SESS}/anat_EPI_mask_MNI-nonlin.nii.gz
        
        # fake reg-to-TAL
        ${DIR_T1}/SESS01/anat_T1_brain.nii.gz ${DIR}/${SESS}/reg_T1_to_TAL.nii.gz

        # fake nonlinear-reg
        ${DIR_T1}/SESS01/anat_T1_brain.nii.gz ${DIR}/${SESS}/reg_nlin_TAL.nii.gz

        # fake motion
        echo ':D' > ${SESS}/PARAMS/motion.DATMAN.01.1D

        fi
    done
done
