#!/bin/bash
#
# This is a slightly-modified epitome script that we are using to analyze the
# EA data.
#
# More on epitome here: https://github.com/josephdviviano/epitome
#
# script generated on 2014-12-12

# -----
# init EPI
# linreg_calc_FSL
# nonlinreg_calc_FSL
# volsmooth
# nonlinreg_to_MNI
# runs registration QC

# import sum modulez
module load matlab/R2013b_concurrent
module load FSL/5.0.7
module load FIX/1.061
module load R/3.1.1
module load R-extras/3.1.1
module load AFNI/2014.12.16
module load freesurfer/5.3.0
module load python/2.7.8-anaconda-2.1.0
module load python-extras/2.7.8

export DIR_DATA=${1}

export DIR_EPITOME=/projects/jdv/code/epitome
export DIR_AFNI=/opt/quarantine/AFNI/2014.12.16/build
export DIR_EXPT=TEMP
export DATA_TYPE=FUNC
export ID=DATMAN
export SUB=SUBJ
McRetroTS='/home/jdv/epitome/EA/bin/run_McRetroTS.sh/opt/quarantine/matlab/R2013'

###############################################################################
echo '************************************************************************'
echo ' Pre-processing of T1 data'
echo ''
echo ' This analysis does not make use of freesurfer, so we are just going'
echo ' to reorient and deskull the T1 manually.'
echo ''
echo '************************************************************************'

cd /tmp

# loop through sessions
DIR_SESS=`ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/T1/*/`
for SESS in ${DIR_SESS}; do
     # loop through runs
     DIR_RUNS=`ls -d -- ${SESS}/RUN*`
     for RUN in ${DIR_RUNS}; do
         NUM=`basename ${RUN} | sed 's/[^0-9]//g'`
         FILE=`echo ${RUN}/*.nii.gz`

         # Reorient T1
         if [ ! -f ${SESS}/anat_T1.nii.gz ]; then
             3daxialize \
                 -prefix ${SESS}/anat_T1.nii.gz \
                 -axial \
                 ${FILE}
         fi

         # Deskull T1
         if [ ! -f ${SESS}/anat_T1_brain.nii.gz ]; then
             3dSkullStrip \
                 -prefix ${SESS}/anat_T1_brain.nii.gz \
                 -input ${SESS}/anat_T1.nii.gz
         fi
    done
done

export DATA_QUALITY=high
export DELTR=0
export TPATTERN=alt+z
export NORMALIZE=scale
export MASKING=loose


echo '************************************************************************'
echo '                  General pre-processing for all fMRI data'
echo ''
echo '   Running on experiment '${DIR_EXPT}', image modality '${DATA_TYPE}'.'
echo '   - Using data quality: '${DATA_QUALITY}','
echo '   - Orients data to RAI,'
echo '   - Deletes '${DELTR}' TRs from the beginning of each run,'
echo '   - Removes time-series outliers, or "despikes", the data,'
echo '   - Corrects for slice timing using the pattern '${TPATTERN}','
echo '   - Deobliques the data,'
echo '   - Motion correction (also outputs motion parameters + 1st lag),'
echo '   - Creates deskulled template EPI and '${MASKING}' whole-brain mask,'
echo '   - Scales each voxel using '${NORMALIZE}','
echo '   - Calculates global mean & DVARS (Power et al., 2012).'
echo ''
echo '************************************************************************'

cd /tmp

# loop through sessions
DIR_SESS=`ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/`
for SESS in ${DIR_SESS}; do
    
    # make the output folder for the paramaters
    mkdir ${SESS}/PARAMS

    # loop through runs
    DIR_RUNS=`ls -d -- ${SESS}/RUN*`
    for RUN in ${DIR_RUNS}; do
        NUM=`basename ${RUN} | sed 's/[^0-9]//g'`
        FILE=`echo ${RUN}/*.nii.gz`

        # 1: Reorient, delete initial TRs, despike, slice time correct 
        if [ ! -f ${SESS}/func_tshift.${ID}.${NUM}.nii.gz ]; then
            # ensure all data is in RAI
            3daxialize \
                -prefix ${SESS}/func_tmp_RAI.${ID}.${NUM}.nii.gz \
                -axial \
                ${FILE} 
            
            # retain 1st TR from 1st run
            if [ ${DATA_QUALITY} = 'low' ] && [ ${NUM} = 01 ]; then
                # strip off the pre-stabilization TR
                3dcalc \
                    -prefix ${SESS}/anat_EPI_tmp_initTR.nii.gz \
                    -a ${SESS}/func_tmp_RAI.${ID}.${NUM}.nii.gz[0] \
                    -expr 'a'
            fi

            # Generate physiological noise regressors if they exist
            if [ -f ${RUN}/resp.*.phys ] && [ -f ${RUN}/card.*.phys ]; then
                
                # get x, y, z, t dims, and TR length
                X=`fslhd ${RUN}/*.nii.gz | sed -n 6p | cut -c 5-`

                Y=`fslhd ${RUN}/*.nii.gz | sed -n 7p | cut -c 5-`

                Z=`fslhd ${RUN}/*.nii.gz | sed -n 8p | cut -c 5-`

                NTRS=`fslhd ${RUN}/*.nii.gz | sed -n 9p | cut -c 5-`

                TR=`fslhd ${RUN}/*.nii.gz | sed -n 22p | cut -c 9-`
                
                # find the smallest dimension in x, y, z 
                XYZ=($X $Y $Z)
                SLICE=`echo ${XYZ[*]} | python -c \
                      "print sorted(map(int,raw_input().split(' ')))[0]"`

                # get the number of samples in physio logs
                SAMP=`cat ${RUN}/resp.*.phys | wc -w`

                # compute sampling rate of physio recording
                UNITS=`fslhd ${RUN}/*.nii.gz | sed -n 14p | cut -c 11- | xargs`
                
                # convert ms to seconds, if necessary
                if [ ${UNITS} = 's' ]; then
                    TIME=`perl -e "print ${NTRS} * ${TR}"`
                elif [ ${UNITS} = 'ms' ]; then
                    TIME=`perl -e "print ${NTRS} * ${TR} / 1000"`
                fi 

                # get the sampling rate in Hz
                FS=`perl -e "print ${SAMP} / ${TIME}"`
                
                # Run McRetroTS -- Respfile Cardfile VolTR Nslices PhysFS Graph
                # NB! Right now we are NOT using the slice-wise information,
                # as the slice-wise information assumes alternating+Z! Jeesh!
                ${McRetroTS} \
                    ${RUN}/resp.*.phys ${RUN}/card.*.phys \
                          ${TR} ${SLICE} ${FS} 0

                # Output both the single-slice and multi-slice data
                1dcat \
                    oba.slibase.1D[0..12]{${DELTR}..$} \
                    > ${SESS}/PARAMS/phys.${ID}.${NUM}.1D

                1dcat \
                    oba.slibase.1D[0..$]{${DELTR}..$} \
                    > ${SESS}/PARAMS/phys_slicewise.${ID}.${NUM}.1D

            fi

            # delete initial time points
            3dcalc \
                -prefix ${SESS}/func_tmp_del.${ID}.${NUM}.nii.gz \
                -a ${SESS}/func_tmp_RAI.${ID}.${NUM}.nii.gz[${DELTR}..$] \
                -expr 'a'

            # despike
            3dDespike \
                -prefix ${SESS}/func_tmp_despike.${ID}.${NUM}.nii.gz \
                -ssave ${SESS}/PARAMS/spikes.${ID}.${NUM}.nii.gz \
                 ${SESS}/func_tmp_del.${ID}.${NUM}.nii.gz

            # slice time correction (can include specified timings)
            #NB -- Physio regression must happen BEFORE NOW if we want to
            # include slice-wise regressors!
            # But it isn't clear to me how important this is.
            if [ -f ${RUN}/slice_timing.1D ]; then
                3dTshift \
                    -prefix ${SESS}/func_tshift.${ID}.${NUM}.nii.gz \
                    -verbose \
                    -Fourier \
                    -tpattern @ ${RUN}/slice_timing.1D \
                    ${SESS}/func_tmp_despike.${ID}.${NUM}.nii.gz
            else
                3dTshift \
                    -prefix ${SESS}/func_tshift.${ID}.${NUM}.nii.gz \
                    -verbose -Fourier \
                    -tpattern ${TPATTERN} \
                    ${SESS}/func_tmp_despike.${ID}.${NUM}.nii.gz
            fi
        fi

        # 2: Deoblique, motion correct, and scale data
        if [ ! -f ${SESS}/func_motion.${ID}.${NUM}.nii.gz ]; then
            # deoblique run
            3dWarp \
                -prefix ${SESS}/func_ob.${ID}.${NUM}.nii.gz \
                -deoblique \
                -quintic \
                -verb \
                -gridset ${SESS}/func_tshift.${ID}.01.nii.gz \
                ${SESS}/func_tshift.${ID}.${NUM}.nii.gz

            # motion correct to 9th sub-brick of 1st run
            3dvolreg \
                -prefix ${SESS}/func_motion.${ID}.${NUM}.nii.gz \
                -base ${SESS}'/func_ob.'${ID}'.01.nii.gz[8]' \
                -twopass \
                -twoblur 3 \
                -twodup \
                -Fourier \
                -zpad 2 \
                -float \
                -1Dfile ${SESS}/PARAMS/motion.${ID}.${NUM}.1D \
                -1Dmatrix_save ${SESS}/PARAMS/3dvolreg.${ID}.${NUM}.aff12.1D \
                ${SESS}/func_ob.${ID}.${NUM}.nii.gz

            # create lagged motion regressors
            if [ ! -f ${SESS}/PARAMS/lag.motion.${ID}.${NUM}.1D ]; then
                1dcat \
                    ${SESS}/PARAMS/motion.${ID}.${NUM}.1D'{0}' > \
                    ${SESS}/PARAMS/lag.motion.${ID}.${NUM}.1D

                1dcat \
                    ${SESS}/PARAMS/motion.${ID}.${NUM}.1D'{0..$}' >> \
                    ${SESS}/PARAMS/lag.motion.${ID}.${NUM}.1D
            fi

            # make a registration volume for low-quality data if required
            if [ ${DATA_QUALITY} = 'low' ] && [ ${NUM} = 01 ]; then
                # deoblique registration volume
                3dWarp \
                    -prefix ${SESS}/anat_EPI_tmp_initTR_ob.nii.gz \
                    -deoblique \
                    -quintic \
                    -verb \
                    -gridset ${SESS}/func_tshift.01.nii.gz \
                    ${SESS}/anat_EPI_tmp_initTR.nii.gz

                # align registration volume with the motion correction TR
                3dvolreg \
                    -prefix ${SESS}/anat_EPI_initTR.nii.gz \
                    -base ${SESS}'/func_ob.01.nii.gz[8]' \
                    -twopass \
                    -twoblur 3 \
                    -twodup \
                    -Fourier \
                    -zpad 2 \
                    -float \
                    ${SESS}/anat_EPI_tmp_initTR_ob.nii.gz
            fi
        fi
        
        # create TS mean for each run
        if [ ! -f ${SESS}/anat_EPI_brain.nii.gz ]; then
            3dTstat \
                -prefix ${SESS}/anat_EPI_tmp_ts_mean.${ID}.${NUM}.nii.gz \
                ${SESS}/func_motion.${ID}.${NUM}.nii.gz
        fi

    done

    ## create session 3D EPI brain + mask (loosened peels)
    if [ ! -f ${SESS}/anat_EPI_brain.nii.gz ]; then
        # create mean over all runs
        3dMean \
            -prefix ${SESS}/anat_EPI_tmp_mean.nii.gz \
            ${SESS}/anat_EPI_tmp_ts_mean.${ID}.*
        
        3dTstat \
            -prefix ${SESS}/anat_EPI_tmp_vol.nii.gz \
            ${SESS}/anat_EPI_tmp_mean.nii.gz
        
        # set masking variables given each preset
        if [ ${MASKING} == 'loosest' ]; then
            CLFRAC=0.15
            PEELS=1
        fi

        if [ ${MASKING} == 'loose' ]; then
            CLFRAC=0.3
            PEELS=1
        fi

        if [ ${MASKING} == 'normal' ]; then
            CLFRAC=0.5
            PEELS=3
        fi

        if [ ${MASKING} == 'tight' ]; then
            CLFRAC=0.7
            PEELS=3
        fi

        # compute the mask
        3dAutomask \
            -prefix ${SESS}/anat_EPI_mask.nii.gz \
            -clfrac ${CLFRAC} \
            -peels ${PEELS} \
            ${SESS}/anat_EPI_tmp_vol.nii.gz
        
        3dcalc \
            -prefix ${SESS}/anat_EPI_brain.nii.gz \
            -a ${SESS}/anat_EPI_tmp_vol.nii.gz \
            -b ${SESS}/anat_EPI_mask.nii.gz \
            -expr 'a*b'

        if [ ${DATA_QUALITY} = 'low' ]; then
            3dcalc \
                -prefix ${SESS}/anat_EPI_initTR_brain.nii.gz \
                -a ${SESS}/anat_EPI_initTR.nii.gz \
                -b ${SESS}/anat_EPI_mask.nii.gz \
                -expr 'a*b'
        fi

    fi

    DIR_RUNS=`ls -d -- ${SESS}/RUN*`
    for RUN in ${DIR_RUNS}; do
        NUM=`basename ${RUN} | sed 's/[^0-9]//g'`

        if [ ! -f ${SESS}/func_scaled.${ID}.${NUM}.nii.gz ]; then

            # calculate time series mean
            3dTstat \
                -prefix ${SESS}/func_tmp_mean.${ID}.${NUM}.nii.gz \
                -mean \
                ${SESS}/func_motion.${ID}.${NUM}.nii.gz

            # OFF: Image multiplied by whole brain mask only
            if [ ${NORMALIZE} == 'off' ]; then
                3dcalc \
                    -prefix ${SESS}/func_scaled.${ID}.${NUM}.nii.gz \
                    -datum float \
                    -a ${SESS}/func_motion.${ID}.${NUM}.nii.gz \
                    -b ${SESS}/anat_EPI_mask.nii.gz \
                    -expr "a*b"
            fi

            # % SIGNAL CHANGE: mean = 100, 1% == 1, normalized by mean
            if [ ${NORMALIZE} == 'pct' ]; then
                3dcalc \
                   -prefix ${SESS}/func_scaled.${ID}.${NUM}.nii.gz \
                   -datum float \
                   -a ${SESS}/func_motion.${ID}.${NUM}.nii.gz \
                   -b ${SESS}/func_tmp_mean.${ID}.${NUM}.nii.gz \
                   -c ${SESS}/anat_EPI_mask.nii.gz \
                   -expr "(a-b)/b*c"
            fi
 
            # SCALE: set global mean = 1000, arbitrary units, no normalization
            if [ ${NORMALIZE} == 'scale' ]; then
                MEAN=`3dmaskave \
                    -quiet \
                    -mask ${SESS}/anat_EPI_brain.nii.gz \
                    ${SESS}/func_tmp_mean.${ID}.${NUM}.nii.gz`

                3dcalc \
                    -prefix ${SESS}/func_scaled.${ID}.${NUM}.nii.gz \
                    -datum float \
                    -a ${SESS}/func_motion.${ID}.${NUM}.nii.gz \
                    -b ${SESS}/anat_EPI_mask.nii.gz \
                    -expr "a*(1000/${MEAN})*b"
            fi

        fi

        # % signal change DVARS (Power et. al Neuroimage 2012)
        if [ ! -f ${SESS}/PARAMS/DVARS.${ID}.${NUM}.1D ]; then
            3dcalc \
                -a ${SESS}/func_scaled.${ID}.${NUM}.nii.gz \
                -b 'a[0,0,0,-1]' \
                -expr '(a - b)^2' \
                -prefix ${SESS}/func_tmp_backdif.${ID}.${NUM}.nii.gz
           
            3dmaskave \
                -mask ${SESS}/anat_EPI_mask.nii.gz \
                -quiet ${SESS}/func_tmp_backdif.${ID}.${NUM}.nii.gz \
                > ${SESS}/PARAMS/tmp_backdif.${ID}.${NUM}.1D
            
            1deval \
                -a ${SESS}/PARAMS/tmp_backdif.${ID}.${NUM}.1D \
                -expr 'sqrt(a)' \
                > ${SESS}/PARAMS/DVARS.${ID}.${NUM}.1D
        fi

        # Global mean
        if [ ! -f ${SESS}/PARAMS/global_mean.${ID}.${NUM}.1D ]; then
            3dmaskave \
                -mask ${SESS}/anat_EPI_mask.nii.gz \
                -quiet ${SESS}/func_scaled.${ID}.${NUM}.nii.gz \
                > ${SESS}/PARAMS/global_mean.${ID}.${NUM}.1D
        fi

    done
    rm ${SESS}/anat_EPI_tmp*.nii.gz >& /dev/null
    rm ${SESS}/func_tmp*.nii.gz >& /dev/null
    rm ${SESS}/PARAMS/tmp*.1D >& /dev/null
done
cd ${DIR_PIPE}

export DATA_QUALITY=high
export COST=corratio
export REG_DOF=12


echo '************************************************************************'
echo '               FSL: Linear registration pathway calculator'
echo ''
echo '   Calculates EPI <--> T1 <--> MNI152 (included in AFNI distribution)'
echo '   - Using data quality: '${DATA_QUALITY}','
echo '   - Cost function: '${COST}','
echo '   - Degrees of freedom preset '${REG_DOF}','
echo '   - Generates EPI template registered to T1 & vice-versa (sessionwise),'
echo ''
echo '************************************************************************'

cd /tmp

# Copy MNI brain to experiment directory
if [ ! -f ${DIR_DATA}/${DIR_EXPT}/anat_MNI.nii.gz ]; then
    3dcopy \
        ${DIR_AFNI}/MNI_avg152T1+tlrc ${DIR_DATA}/${DIR_EXPT}/anat_MNI.nii.gz
fi

DIR_SESS=`ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/`
for SESS in `basename ${DIR_SESS}`; do
    DIR=`echo ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}`
    DIR_T1=`echo ${DIR_DATA}/${DIR_EXPT}/${SUB}/T1`

    # If we have a T1 for each session, we register to the session T1. 
    # Otherwise, we go to the first session.
    if [ `ls -l ${DIR} | grep ^d | wc -l` -eq \
         `ls -l ${DIR_T1} | grep ^d | wc -l` ]; then
        ANAT_T1=`echo ${DIR_T1}/${SESS}/anat_T1_brain.nii.gz`
    else
        ANAT_T1=`echo ${DIR_T1}/SESS01/anat_T1_brain.nii.gz`
    fi

    # Set EPI data file (for low vs high quality data).
    if [ ${DATA_QUALITY} = 'low' ]; then
        ANAT_EPI=`echo ${DIR}/${SESS}/anat_EPI_initTR_brain.nii.gz`
    else
        ANAT_EPI=`echo ${DIR}/${SESS}/anat_EPI_brain.nii.gz`
    fi

    # calculate registration of EPI to T1
    if [ ! -f ${DIR}/${SESS}/mat_T1_to_EPI.mat ]; then
        flirt \
            -in ${ANAT_EPI} \
            -ref ${ANAT_T1} \
            -out ${DIR}/${SESS}/reg_EPI_to_T1.nii.gz \
            -omat ${DIR}/${SESS}/mat_EPI_to_T1.mat \
            -dof ${REG_DOF} \
            -cost ${COST} \
            -searchcost ${COST} \
            -searchrx -180 180 -searchry -180 180 -searchrz -180 180 \
            -v

        # invert flirt transform
        convert_xfm \
            -omat ${DIR}/${SESS}/mat_T1_to_EPI.mat \
            -inverse \
            ${DIR}/${SESS}/mat_EPI_to_T1.mat
    fi

    # produce T1 registered to EPI
    if [ ! -f ${DIR}/${SESS}/reg_T1_to_EPI.nii.gz ]; then
        # T1 to EPI -- FSL
        flirt \
            -in ${ANAT_T1} \
            -ref ${ANAT_EPI} \
            -out ${DIR}/${SESS}/reg_T1_to_EPI.nii.gz \
            -applyxfm \
            -init ${DIR}/${SESS}/mat_T1_to_EPI.mat \
            -v
    fi

    # calculate registration of T1 to reg_T1_to_TAL
    if [ ! -f ${DIR}/${SESS}/reg_TAL_to_T1.mat ]; then
        flirt \
            -in ${DIR_T1}/${SESS}/anat_T1_brain.nii.gz \
            -ref ${DIR_DATA}/${DIR_EXPT}/anat_MNI.nii.gz \
            -out ${DIR}/${SESS}/reg_T1_to_TAL.nii.gz \
            -omat ${DIR}/${SESS}/mat_T1_to_TAL.mat \
            -dof ${REG_DOF} \
            -searchcost corratio \
            -cost ${COST} \
            -searchcost ${COST} \
            -searchrx -180 180 -searchry -180 180 -searchrz -180 180 \
            -v

        # invert flirt transform
        convert_xfm \
            -omat ${DIR}/${SESS}/mat_TAL_to_T1.mat \
            -inverse \
            ${DIR}/${SESS}/mat_T1_to_TAL.mat
    fi

    # concatenate transformations
    if [ ! -f ${DIR}/${SESS}/reg_TAL_to_EPI.mat ]; then

        convert_xfm \
            -omat ${DIR}/${SESS}/mat_EPI_to_TAL.mat \
            -concat ${DIR}/${SESS}/mat_T1_to_TAL.mat \
                    ${DIR}/${SESS}/mat_EPI_to_T1.mat 

        convert_xfm \
            -omat ${DIR}/${SESS}/mat_TAL_to_EPI.mat \
            -concat ${DIR}/${SESS}/mat_T1_to_EPI.mat \
                    ${DIR}/${SESS}/mat_TAL_to_T1.mat
    fi

    # Clean up leftovers in /tmp
    rm anat_*
    rm __tt*
    rm template*
    rm pre.*
done

echo '************************************************************************'
echo '              FSL: NonLinear registration pathway calculator'
echo ''
echo '************************************************************************'

cd /tmp

# Copy MNI brain to experiment directory
if [ ! -f ${DIR_DATA}/${DIR_EXPT}/anat_MNI.nii.gz ]; then
    3dcopy \
        ${DIR_AFNI}/MNI_avg152T1+tlrc ${DIR_DATA}/${DIR_EXPT}/anat_MNI.nii.gz
fi

DIR_SESS=`ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/`
for SESS in `basename ${DIR_SESS}`; do
    DIR=`echo ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}`
    DIR_T1=`echo ${DIR_DATA}/${DIR_EXPT}/${SUB}/T1`

    # calculate registration of EPI to T1
    if [ ! -f ${DIR}/${SESS}/reg_nlin_TAL_WARP.nii.gz ]; then
        # fnirt --iout=highres2standard_head --in=highres_head --aff=highres2standard.mat --cout=highres2standard_warp --iout=highres2standard --jout=highres2highres_jac --con+ 
        
        fnirt \
            --ref=${DIR_DATA}/${DIR_EXPT}/anat_MNI.nii.gz \
            --in=${DIR}/${SESS}/reg_T1_to_TAL.nii.gz \
            --config=T1_2_MNI152_2mm \
            --iout=${DIR}/${SESS}/reg_nlin_TAL.nii.gz \
            --fout=${DIR}/${SESS}/reg_nlin_TAL_FIELD.nii.gz \
            --cout=${DIR}/${SESS}/reg_nlin_TAL_WARP.nii.gz \
            --intout=${DIR}/${SESS}/reg_nlin_TAL_INTOUT.nii.gz \
            --interp=spline

        # --refmask='a mask of the MNI-space brain'
    fi

    # Clean up leftovers in /tmp
    rm anat_*
    rm __tt*
    rm template*
    rm pre.*
done
cd ${DIR_PIPE}

export INPUT=func_scaled
export MASK=anat_EPI_mask
export FWHM=6.0


echo '************************************************************************'
echo '     Smooths data in volumetric space, obeying mask label boundaries'
echo '   Anything labeled zero in the mask will become zeroed in the output.'
echo ''
echo '************************************************************************'


#Loop through sessions, runs
DIR_SESS=`ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/`
for SESS in ${DIR_SESS}; do
    DIR_RUNS=`ls -d -- ${SESS}/RUN*`
    for RUN in ${DIR_RUNS}; do
        NUM=`basename ${RUN} | sed 's/[^0-9]//g'`
        
        # resample input mask to match dimensions of first run
        if [ ! -f ${SESS}/anat_smoothmask.nii.gz ]; then 
            3dresample \
                -prefix ${SESS}/anat_smoothmask.nii.gz \
                -master ${SESS}/${INPUT}.${ID}.01.nii.gz \
                -rmode NN \
                -inset ${SESS}/${MASK}.nii.gz
        fi

        # resample mask to single-run space, then smooth
        if [ ! -f ${SESS}/func_volsmooth.${ID}.${NUM}.nii.gz ]; then
            3dBlurInMask \
                -prefix ${SESS}/func_volsmooth.${ID}.${NUM}.nii.gz \
                -Mmask ${SESS}/anat_smoothmask.nii.gz \
                -FWHM ${FWHM} \
                -input ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz

        fi
    done
done

cd ${DIR_PIPE}

export INPUT=func_volsmooth
export DIMS=3.0


echo '************************************************************************'
echo '                       FSL MNI-transform data'
echo ''
echo '   - Resamples '${INPUT}' data to MNI space at '${DIMS}'^3mm,'
echo '   - Transforms whole-brain masks to MNI space,'
echo '   - Creates 1 concatenated run per participant in run order.'
echo ''
echo '             DO NOT RUN LINREG_EPI2MNI_FSL BEFORE THIS!!!'
echo '                    This does that part for you :)'
echo ''
echo '************************************************************************'

cd /tmp

DIR_SESS=`ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/`
for SESS in `basename ${DIR_SESS}`; do
    
    DIR=`echo ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/${SESS}`
    DIR_T1=`echo ${DIR_DATA}/${DIR_EXPT}/${SUB}/T1/${SESS}`

    # create registration dummy for FSL
    3dresample -dxyz ${DIMS} ${DIMS} ${DIMS} \
               -prefix ${DIR}/anat_EPI_reg_target.nii.gz \
               -inset ${DIR}/reg_nlin_TAL.nii.gz

    DIR_RUNS=`ls -d -- ${DIR}/RUN*`
    for RUN in ${DIR_RUNS}; do
        NUM=`basename ${RUN} | sed 's/[^0-9]//g'`

        # register runs with MNI
        if [ ! -f ${DIR}/func_MNI-nonlin.${ID}.${NUM}.nii.gz ]; then
            applywarp \
                --ref=${DIR}/anat_EPI_reg_target.nii.gz \
                --in=${DIR}/${INPUT}.${ID}.${NUM}.nii.gz \
                --warp=${DIR}/reg_nlin_TAL_WARP.nii.gz \
                --premat=${DIR}/mat_EPI_to_TAL.mat \
                --interp=spline \
                --out=${DIR}/func_MNI-nonlin.${ID}.${NUM}.nii.gz
        fi
    done
    
    
    # register session masks with MNI-lin
    if [ ! -f ${DIR}/anat_EPI_mask_MNI-lin.nii.gz ]; then
        flirt \
            -in ${DIR}/anat_EPI_mask.nii.gz \
            -ref ${DIR}/anat_EPI_reg_target.nii.gz \
            -applyxfm -init ${DIR}/mat_EPI_to_TAL.mat \
            -interp nearestneighbour \
            -out ${DIR}/anat_EPI_mask_MNI-lin.nii.gz
    fi

    # register session masks with MNI-nonlin
    if [ ! -f ${DIR}/anat_EPI_mask_MNI-nonlin.nii.gz ]; then
        applywarp \
            --ref=${DIR}/anat_EPI_reg_target.nii.gz \
            --in=${DIR}/anat_EPI_mask.nii.gz \
            --warp=${DIR}/reg_nlin_TAL_WARP.nii.gz \
            --premat=${DIR}/mat_EPI_to_TAL.mat \
            --interp=nn \
            --out=${DIR}/anat_EPI_mask_MNI-nonlin.nii.gz
    fi
done

cd ${DIR_PIPE}

