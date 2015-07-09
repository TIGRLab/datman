#!/bin/bash
#
# This is a slightly-modified epitome script.
# More on epitome here: https://github.com/josephdviviano/epitome
# script generated on 2015-04-09

# -----
# init EPI
# linreg_calc_FSL
# nonlinreg_calc_FSL
# linreg fs2epi
# filter (anaticor)
# volsmooth (blur2FWHM)
# nonlinreg_to_MNI

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

SCRIPTDIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
export DIR_PIPE=${SCRIPTDIR}/epitome/150331-spins

# adds compcor program to path
export PATH=${DIR_PIPE}'/bin':$PATH

export DIR_AFNI=/opt/quarantine/AFNI/2014.12.16/build
export DIR_EXPT=TEMP
export DATA_TYPE=FUNC
export ID=DATMAN
export SUB=SUBJ
McRetroTS=${SCRIPTDIR}'/epitome/150331-spins/bin/run_McRetroTS.sh /opt/quarantine/matlab/matlab_concurrent_all/MATLAB_R2013b'

###############################################################################

export DATA_QUALITY=high
export DESPIKE=on
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
echo '   - Optionally removes time-series outliers, '${DESPIKE}','
echo '   - Corrects for slice timing using the pattern '${TPATTERN}','
echo '   - Deobliques the data,'
echo '   - Motion correction (also outputs motion parameters + 1st lag),'
echo '   - Creates deskulled template EPI and '${MASKING}' whole-brain mask,'
echo '   - Scales each voxel using '${NORMALIZE}','
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
            if [ ${DESPIKE} == 'on' ]; then
                3dDespike \
                    -prefix ${SESS}/func_tmp_despike.${ID}.${NUM}.nii.gz \
                    -ssave ${SESS}/PARAMS/spikes.${ID}.${NUM}.nii.gz \
                     ${SESS}/func_tmp_del.${ID}.${NUM}.nii.gz
            else
                cp ${SESS}/func_tmp_del.${ID}.${NUM}.nii.gz \
                   ${SESS}/func_tmp_despike.${ID}.${NUM}.nii.gz
            fi

            # slice time correction (can include specified timings)
            #NB -- Physio regression must happen BEFORE NOW if we want to
            # include slice-wise regressors!
            # But it isn't clear to me how important this is.
            if [ ${TPATTERN} != 'none' ]; then
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
            # if tpattern == 'none', we just copy to make the output
            else
                cp ${SESS}/func_tmp_despike.${ID}.${NUM}.nii.gz \
                   ${SESS}/func_tshift.${ID}.${NUM}.nii.gz
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
            ${SESS}/anat_EPI_tmp_ts_mean.${ID}.*.nii.gz
        
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

            # % SIGNAL CHANGE: mean = 0, 1% == 1 (normalized by mean)
            # careful using this with event-related designs
            if [ ${NORMALIZE} == 'pct' ]; then
                3dcalc \
                   -prefix ${SESS}/func_scaled.${ID}.${NUM}.nii.gz \
                   -datum float \
                   -a ${SESS}/func_motion.${ID}.${NUM}.nii.gz \
                   -b ${SESS}/func_tmp_mean.${ID}.${NUM}.nii.gz \
                   -c ${SESS}/anat_EPI_mask.nii.gz \
                   -expr "(a-b)/b*c*100"
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
    done
    rm ${SESS}/anat_EPI_tmp*.nii.gz >& /dev/null
    rm ${SESS}/func_tmp*.nii.gz >& /dev/null
    rm ${SESS}/PARAMS/tmp*.1D >& /dev/null
done

export DATA_QUALITY=high
export COST=corratio
export REG_DOF=6

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
    if [ ! -f ${DIR}/${SESS}/mat_TAL_to_T1.mat ]; then
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
    if [ ! -f ${DIR}/${SESS}/mat_TAL_to_EPI.mat ]; then
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
echo '               FSL: Nonlinear registration pathway calculator'
echo ''
echo '   Calculates MNI linreg --> MNI nonlinreg using FSL FNIRT'
echo ''
echo '   - Generates T1 template warped to MNI and associated transforms,'
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


echo '************************************************************************'
echo '         FSL Brings Freesurfer atlases to single-subject space          '
echo ''
echo '************************************************************************'

cd /tmp

DIR_SESS=`ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/`
for SESS in `basename ${DIR_SESS}`; do
    
    DIR=`echo ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/${SESS}`
    DIR_T1=`echo ${DIR_DATA}/${DIR_EXPT}/${SUB}/T1/${SESS}`
    # register aparc atlas to EPI
    if [ ! -f ${DIR}/anat_aparc_reg.nii.gz ]; then
        flirt -in ${DIR_T1}/anat_aparc_brain.nii.gz \
              -ref ${DIR}/anat_EPI_brain.nii.gz \
              -applyxfm -init ${DIR}/mat_T1_to_EPI.mat \
              -interp nearestneighbour \
              -out ${DIR}/anat_aparc_reg.nii.gz
    fi

    # register aparc2009 atlas to EPI
    if [ ! -f ${DIR}/anat_aparc2009_reg.nii.gz ]; then
        flirt -in ${DIR_T1}/anat_aparc2009_brain.nii.gz \
              -ref ${DIR}/anat_EPI_brain.nii.gz \
              -applyxfm -init ${DIR}/mat_T1_to_EPI.mat \
              -interp nearestneighbour \
              -out ${DIR}/anat_aparc2009_reg.nii.gz
    fi
done


export INPUT=func_scaled
export POLORT=1
export STD=on
export GM=off
export ANATICOR=off
export COMPCOR=on
export COMPNUM=5
export DV=off


echo '************************************************************************'
echo '                    Time series filtering of fMRI data'
echo ''
echo '   - Creates a set of regressors from '${INPUT}' functional data and'
echo '     a freesurfer segmentation. Outputs:'
echo ''
echo '         - MASKS:'
echo '             - white matter + eroded mask,'
echo '             - ventricles + eroded mask,'
echo '             - grey matter mask,'
echo '             - brain stem mask,'
echo '             - dialated brain mask,'
echo '             - draining vessels mask,'
echo ''
echo '         - REGRESSORS:'
echo '             - white matter: local (15mm sphere) and average, + lags'
echo '             - ventricles averaged + lagged,'
echo '             - draining vessel averaged + lagged.'
echo ''
echo '   - Calculates global mean & DVARS (Power et al., 2012).'
echo '   - Detrends input with legrende polynomials up to order '${POLORT}','
echo '   - Computes temporal signal to noise ratio of input,'
echo '   - Computes nusiance time series from physio, motion paramaters, and:'
echo '         - Standard regressors: '${STD}','
echo '         - Global mean regression: '${GM}','
echo '         - ANATICOR local white matter regression: '${ANATICOR}','
echo '         - COMPCOR principal component regression: '${COMPCOR}','
echo '         - Draining vessel regression: '${DV}','
echo '   - Computes fit of run with nusiances via least squares regression,'
echo '   - Subtracts noise model from each voxel, retaining the mean.'
echo ''
echo '************************************************************************'

cd /tmp

DIR_SESS=`ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/`
for SESS in ${DIR_SESS}; do

    ## Make Masks ##
    # eroded white matter mask
    if [ ! -f ${SESS}/anat_wm_ero.nii.gz ]; then
        3dcalc \
            -a ${SESS}/anat_aparc_reg.nii.gz \
            -expr "equals(a,2)  + \
                   equals(a,7)  + \
                   equals(a,41) + \
                   equals(a,46) + \
                   equals(a,251)+ \
                   equals(a,252)+ \
                   equals(a,253)+ \
                   equals(a,254)+ \
                   equals(a,255)" \
            -prefix ${SESS}/anat_wm.nii.gz

        3dcalc \
            -a ${SESS}/anat_wm.nii.gz \
            -b a+i -c a-i -d a+j -e a-j -f a+k -g a-k \
            -expr 'a*(1-amongst(0,b,c,d,e,f,g))' \
            -prefix ${SESS}/anat_wm_ero.nii.gz
    fi

    # eroded ventricle mask
    if [ ! -f ${SESS}/anat_vent_ero.nii.gz ]; then
        3dcalc \
            -a ${SESS}/anat_aparc_reg.nii.gz \
            -expr 'equals(a,4) + equals(a,43)' \
            -prefix ${SESS}/anat_vent.nii.gz

        3dcalc \
            -a ${SESS}/anat_aparc_reg.nii.gz \
            -expr "equals(a,10) + \
                   equals(a,11) + \
                   equals(a,26) + \
                   equals(a,49) + \
                   equals(a,50) + \
                   equals(a,58)" \
            -prefix ${SESS}/anat_tmp_nonvent.nii.gz

        3dcalc \
            -a ${SESS}/anat_tmp_nonvent.nii.gz \
            -b a+i -c a-i -d a+j -e a-j -f a+k -g a-k \
            -expr 'amongst(1,a,b,c,d,e,f,g)' \
            -prefix ${SESS}/anat_tmp_nonvent_dia.nii.gz

        3dcalc \
            -a ${SESS}/anat_vent.nii.gz \
            -b ${SESS}/anat_tmp_nonvent_dia.nii.gz \
            -expr 'a-step(a*b)' \
            -prefix ${SESS}/anat_vent_ero.nii.gz
    fi

    # grey matter mask
    if [ ! -f ${SESS}/anat_gm.nii.gz ]; then
        3dcalc \
            -a ${SESS}/anat_aparc_reg.nii.gz \
            -short \
            -expr 'step(a-1000)*step(1036-a)+step(a-2000)*step(2036-a)' \
            -prefix ${SESS}/anat_gm.nii.gz
    fi

    # dialated brain mask
    if [ ! -f ${SESS}/anat_EPI_mask_dia.nii.gz ]; then
        3dcalc \
            -a ${SESS}/anat_EPI_mask.nii.gz \
            -b a+i -c a-i -d a+j -e a-j -f a+k -g a-k \
            -expr 'amongst(1,a,b,c,d,e,f,g)' \
            -prefix ${SESS}/anat_EPI_mask_dia.nii.gz
    fi

    # brainstem mask
    if [ ! -f ${SESS}/anat_bstem.nii.gz ]; then
        3dcalc \
            -a ${SESS}/anat_aparc_reg.nii.gz \
            -expr "equals(a,8)  + \
                   equals(a,47) + \
                   equals(a,16) + \
                   equals(a,12) + \
                   equals(a,13) + \
                   equals(a,26) + \
                   equals(a,51) + \
                   equals(a,52) + \
                   equals(a,17) + \
                   equals(a,18) + \
                   equals(a,53) + \
                   equals(a,54) + \
                   equals(a,58) + \
                   equals(a,28) + \
                   equals(a,60)" \
            -prefix ${SESS}/anat_bstem.nii.gz
    fi

    # eroded draining vessel mask
    if [ ! -f ${SESS}/anat_dv_ero.nii.gz ]; then
        3dcalc \
            -a ${SESS}/anat_EPI_mask.nii.gz \
            -b ${SESS}/anat_gm.nii.gz \
            -c ${SESS}/anat_wm.nii.gz \
            -d ${SESS}/anat_vent.nii.gz \
            -e ${SESS}/anat_tmp_nonvent.nii.gz \
            -f ${SESS}/anat_bstem.nii.gz \
            -expr '(a-b-c-d-e-f)' \
            -prefix ${SESS}/anat_dv.nii.gz
        
        3dcalc \
            -a ${SESS}/anat_dv.nii.gz \
            -b a+i -c a-i -d a+j -e a-j -f a+k -g a-k \
            -expr 'a*(1-amongst(0,b,c,d,e,f,g))' \
            -prefix ${SESS}/anat_dv_ero.nii.gz
    fi

    DIR_RUNS=`ls -d -- ${SESS}/RUN*`
    for RUN in ${DIR_RUNS}; do
        NUM=`basename ${RUN} | sed 's/[^0-9]//g'`

        # detrend functional data and motion paramaters (and calculate tsnr)
        if [ ! -f ${SESS}/func_detrend.${ID}.${NUM}.nii.gz ]; then
            
            # compute mean, standard deviation
            3dTstat \
                -prefix ${SESS}/func_mean.${ID}.${NUM}.nii.gz \
                -mean ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz

            3dTstat \
                -prefix ${SESS}/func_stdev.${ID}.${NUM}.nii.gz \
                -stdev ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz
            
            # compute temporal SNR (pre anything)
            3dcalc \
                -a ${SESS}/func_mean.${ID}.${NUM}.nii.gz \
                -b ${SESS}/func_stdev.${ID}.${NUM}.nii.gz \
                -expr 'a/b' \
                -prefix ${SESS}/func_tSNR.${ID}.${NUM}.nii.gz

            # detrend input data (before calculating regressors...)
            3dDetrend \
                -prefix ${SESS}/func_detrend.${ID}.${NUM}.nii.gz \
                -polort ${POLORT} \
                ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz

            # detrend motion paramaters
            3dDetrend \
                -prefix - \
                -DAFNI_1D_TRANOUT=YES \
                -polort ${POLORT} \
                ${SESS}/PARAMS/motion.${ID}.${NUM}.1D\' > \
                ${SESS}/PARAMS/det.motion.${ID}.${NUM}.1D

            3dDetrend \
                -prefix - \
                -DAFNI_1D_TRANOUT=YES \
                -polort ${POLORT} \
                ${SESS}/PARAMS/lag.motion.${ID}.${NUM}.1D\' > \
                ${SESS}/PARAMS/det.lag.motion.${ID}.${NUM}.1D
            
            # detrend physiological regressors, if they exist
            if [ -f ${SESS}/PARAMS/phys.${ID}.${NUM}.1D ]; then
                3dDetrend \
                    -prefix - \
                    -DAFNI_1D_TRANOUT=YES \
                    -polort ${POLORT} \
                    ${SESS}/PARAMS/phys.${ID}.${NUM}.1D\' > \
                    ${SESS}/PARAMS/det.phys.${ID}.${NUM}.1D
            fi

            # % signal change DVARS (+ lag) (Power et. al Neuroimage 2012)
            3dcalc \
                -a ${SESS}/func_detrend.${ID}.${NUM}.nii.gz \
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

        # initialize filter command
        if [ ! -f ${SESS}/func_filtered.${ID}.${NUM}.nii.gz ]; then
            
            # start with the standard motion-parameter regressors
            CMD=`echo 3dTfitter \
                          -prefix ${SESS}/func_noise_betas.${ID}.${NUM}.nii.gz \
                          -fitts ${SESS}/func_noise.${ID}.${NUM}.nii.gz \
                          -polort 0 \
                          -RHS ${SESS}/func_detrend.${ID}.${NUM}.nii.gz \
                          -LHS ${SESS}/PARAMS/det.motion.${ID}.${NUM}.1D \
                               ${SESS}/PARAMS/det.lag.motion.${ID}.${NUM}.1D `

            # add the physio regressors if they exist
            if [ -f ${SESS}/PARAMS/det.phys.${ID}.${NUM}.1D ]; then
                CMD=`echo ${CMD} ${SESS}/PARAMS/det.phys.${ID}.${NUM}.1D`
            fi

            if [ `echo ${STD}` = 'on' ]; then

                # white matter mean (+ lag)
                3dmaskave \
                    -q -mask ${SESS}/anat_wm_ero.nii.gz \
                    ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz > \
                    ${SESS}/PARAMS/wm.${ID}.${NUM}.1D
                
                1dcat \
                    ${SESS}/PARAMS/wm.${ID}.${NUM}.1D'{0}' > \
                    ${SESS}/PARAMS/lag.wm.${ID}.${NUM}.1D
                
                1dcat \
                    ${SESS}/PARAMS/wm.${ID}.${NUM}.1D'{0..$}' >> \
                    ${SESS}/PARAMS/lag.wm.${ID}.${NUM}.1D

                # ventricle mean (+ lag)
                3dmaskave \
                    -q -mask ${SESS}/anat_vent_ero.nii.gz \
                    ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz > \
                    ${SESS}/PARAMS/vent.${ID}.${NUM}.1D
                
                1dcat \
                    ${SESS}/PARAMS/vent.${ID}.${NUM}.1D'{0}' > \
                    ${SESS}/PARAMS/lag.vent.${ID}.${NUM}.1D
                
                1dcat \
                    ${SESS}/PARAMS/vent.${ID}.${NUM}.1D'{0..$}' >> \
                    ${SESS}/PARAMS/lag.vent.${ID}.${NUM}.1D

                CMD=`echo ${CMD} ${SESS}/PARAMS/vent.${ID}.${NUM}.1D`
                CMD=`echo ${CMD} ${SESS}/PARAMS/lag.vent.${ID}.${NUM}.1D`
                CMD=`echo ${CMD} ${SESS}/PARAMS/wm.${ID}.${NUM}.1D`
                CMD=`echo ${CMD} ${SESS}/PARAMS/lag.wm.${ID}.${NUM}.1D`
            fi

            if [ `echo ${GM}` = 'on' ]; then

                # global mean (+ lag)
                3dmaskave \
                    -mask ${SESS}/anat_EPI_mask.nii.gz \
                    -quiet ${SESS}/func_detrend.${ID}.${NUM}.nii.gz \
                    > ${SESS}/PARAMS/global_mean.${ID}.${NUM}.1D

                1dcat \
                    ${SESS}/PARAMS/global_mean.${ID}.${NUM}.1D'{0}' > \
                    ${SESS}/PARAMS/lag.global_mean.${ID}.${NUM}.1D
                
                1dcat \
                    ${SESS}/PARAMS/global_mean.${ID}.${NUM}.1D'{0..$}' >> \
                    ${SESS}/PARAMS/lag.global_mean.${ID}.${NUM}.1D
   
                CMD=`echo ${CMD} ${SESS}/PARAMS/global_mean.${ID}.${NUM}.1D`
                CMD=`echo ${CMD} ${SESS}/PARAMS/lag.global_mean.${ID}.${NUM}.1D`
            fi

            if [ `echo ${ANATICOR}` = 'on' ]; then
                
                # local white matter (+ lag)
                if [ ! -f ${SESS}/PARAMS/lag.wm_local15.${ID}.${NUM}.nii.gz ]; then
                    3dLocalstat \
                        -prefix ${SESS}/PARAMS/wm_local15.${ID}.${NUM}.nii.gz \
                        -nbhd 'SPHERE(15)' \
                        -stat mean \
                        -mask ${SESS}/anat_wm_ero.nii.gz \
                        -use_nonmask ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz

                    3dTcat \
                        -prefix ${SESS}/PARAMS/lag.wm_local15.${ID}.${NUM}.nii.gz \
                        ${SESS}/PARAMS/wm_local15.${ID}.${NUM}.nii.gz'[0]' \
                        ${SESS}/PARAMS/wm_local15.${ID}.${NUM}.nii.gz'[0..$]'
                fi

                CMD=`echo ${CMD} ${SESS}/PARAMS/wm_local15.${ID}.${NUM}.nii.gz`
                CMD=`echo ${CMD} ${SESS}/PARAMS/lag.wm_local15.${ID}.${NUM}.nii.gz`
            fi

            if [ `echo ${COMPCOR}` = 'on' ]; then

                # aCompcor regressors for WM and ventricles
                if [ ! -f ${SESS}/PARAMS/vent_pc.${ID}.${NUM}.1D ]; then
                    epi-genregress \
                        ${SESS}/func_detrend.${ID}.${NUM}.nii.gz \
                        ${SESS}/anat_vent_ero.nii.gz \
                        ${SESS}/PARAMS/vent_pc.${ID}.${NUM}.1D \
                        ${COMPNUM}
                fi

                if [ ! -f ${SESS}/PARAMS/wm_pc.${ID}.${NUM}.1D ]; then
                    epi-genregress \
                        ${SESS}/func_detrend.${ID}.${NUM}.nii.gz \
                        ${SESS}/anat_wm_ero.nii.gz \
                        ${SESS}/PARAMS/wm_pc.${ID}.${NUM}.1D \
                        ${COMPNUM}
                fi

                # https://www.youtube.com/watch?v=oavMtUWDBTM
                CMD=`echo ${CMD} ${SESS}/PARAMS/wm_pc.${ID}.${NUM}.1D`
                CMD=`echo ${CMD} ${SESS}/PARAMS/vent_pc.${ID}.${NUM}.1D`
            fi

            if [ `echo ${DV}` = 'on' ]; then

                # create mean draining vessel time series (+ lagged)
                3dmaskave \
                    -q -mask ${SESS}/anat_dv_ero.nii.gz \
                    ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz > \
                    ${SESS}/PARAMS/dv.${ID}.${NUM}.1D
                
                1dcat \
                    ${SESS}/PARAMS/dv.${ID}.${NUM}.1D'{0}' > \
                    ${SESS}/PARAMS/lag.dv.${ID}.${NUM}.1D
                
                1dcat \
                    ${SESS}/PARAMS/dv.${ID}.${NUM}.1D'{0..$}' >> \
                    ${SESS}/PARAMS/lag.dv.${ID}.${NUM}.1D

                CMD=`echo ${CMD} ${SESS}/PARAMS/dv.${ID}.${NUM}.1D`
                CMD=`echo ${CMD} ${SESS}/PARAMS/lag.dv.${ID}.${NUM}.1D`
            fi

            ####################################################################

            # Finally, echo  run the command
            echo '****************************'
            echo 'Filtering time series using:'
            echo ${CMD}
            echo '****************************'
            ${CMD}

            # subtracts nuisances from inputs, retaining the mean
            3dcalc \
                -float \
                -a ${SESS}/func_detrend.${ID}.${NUM}.nii.gz \
                -b ${SESS}/func_noise.${ID}.${NUM}.nii.gz \
                -c ${SESS}/func_mean.${ID}.${NUM}.nii.gz \
                -expr 'a-b+c' \
                -prefix ${SESS}/func_filtered.${ID}.${NUM}.nii.gz
        fi

    done
    rm ${SESS}/func_tmp_*
done

export INPUT=func_filtered
export MASK=anat_EPI_mask
export FWHM=8.0
export MODE=normal

echo '************************************************************************'
echo '                        Spatially smooth data.'
echo ''
echo '    - Smooths data in volumetric space.'
echo '    - Anything labeled zero in the mask will become zeroed in the output.'


if [ ${MODE} == 'multimask' ]; then
echo '    - Obeys mask label boundaries.'
echo '    - Uses simpler blurring (iterative on input dataset).'
fi

if [ ${MODE} == 'normal' ]; then
echo '    - Iteratively blurs data to some FWHM within a mask.'
echo '    - Ideally uses the noise model from the filter module to estimate'
echo '      smoothness, otherwise, detrends input and uses that.'
echo '    - But if you didnt use filter before, this detrends the input'
echo '      and uses that.'
echo '    - NB: Assumes these images are in register!!! Use before going to'
echo '      MNI space!'
fi

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

        # smooth to specified FWHM
        if [ ! -f ${SESS}/func_volsmooth.${ID}.${NUM}.nii.gz ]; then

            # use 3dBlurToFWHM
            if [ ${MODE} == 'normal' ]; then

                # If already run filter, use noise model from it as blurmaster
                if [ -f ${SESS}/func_noise.${ID}.${NUM}.nii.gz ]; then

                    3dBlurToFWHM \
                        -prefix ${SESS}/func_volsmooth.${ID}.${NUM}.nii.gz \
                        -mask ${SESS}/anat_smoothmask.nii.gz \
                        -FWHM ${FWHM} \
                        -blurmaster ${SESS}/func_noise.${ID}.${NUM}.nii.gz \
                        -input ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz

                else

                    3dBlurToFWHM \
                        -prefix ${SESS}/func_volsmooth.${ID}.${NUM}.nii.gz \
                        -mask ${SESS}/anat_smoothmask.nii.gz \
                        -FWHM ${FWHM} \
                        -input ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz
                fi

            # use 3dBlurInMask
            elif [ ${MODE} == 'multimask' ]; then
                
                3dBlurInMask \
                    -prefix ${SESS}/func_volsmooth.${ID}.${NUM}.nii.gz \
                    -Mmask ${SESS}/anat_smoothmask.nii.gz \
                    -FWHM ${FWHM} \
                    -input ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz
            fi
        fi
    done
done


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


