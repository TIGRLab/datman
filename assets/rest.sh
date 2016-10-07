#!/bin/bash

# rendered script-it from master_161006_datman.sh
# generated: 2016/10/06 -- 14:23:51 by jviviano.

set -e

export DIR_MODULES=/archive/code/epitome/modules
export DIR_DATA=/archive/code/script-it/data
export DIR_EXPT=dummy_project
export DATA_TYPE=rest
export ID=datman

# command line arguments
export SUB=DATMAN
export del=${1}
export tr=${2}
export dims=${3}

if [ "$#" -ne 3 ]; then
    echo "Usage:"
    echo "    $(basename ${0}) deltr tr dims"
    echo "        deltr:   number of TRs to remove from the beginning of each run"
    echo "        tr:      length of TR in seconds (decimals allowed)"
    echo "        dims:    isotropic voxel dimensions of MNI space data"
    exit 1
fi

# sets some handy AFNI defaults
export AFNI_NIFTI_TYPE_WARN='NO'
export AFNI_DECONFLICT=OVERWRITE

echo '*** MODULE: init_basic. Reorients, phys regression, removes init TRs. ***'
export data_quality=high

# loop through sessions
for SESS in $(ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/); do

    # make the output folder for the paramaters
    if [ ! -d ${SESS}/PARAMS ]; then
        mkdir ${SESS}/PARAMS
    fi

    # loop through runs
    RUNS=$(find ${SESS} -type d -name 'RUN*' | sort)
    for RUN in ${RUNS}; do
        NUM=$(basename ${RUN} | sed 's/[^0-9]//g')
        input=$(echo ${SESS}/RUN${NUM}/*.nii*)
        runfolder=$(echo ${SESS}/RUN${NUM}/)

        if [ ! -f ${SESS}/func_del.${ID}.${NUM}.nii.gz ]; then
           # ensure all data is in RAI
           fslreorient2std \
               ${input} \
               ${SESS}/func_tmp_RAI.${ID}.${NUM}.nii.gz

            # retain 1st TR from 1st run (prestabilization)
            if [ ${data_quality} = 'low' ] && [ ${NUM} = 01 ]; then
                3dcalc \
                    -prefix ${SESS}/anat_EPI_initTR.nii.gz \
                    -a ${SESS}/func_tmp_RAI.${ID}.${NUM}.nii.gz[0] \
                    -expr 'a'
            fi

            # Generate physiological noise regressors if they exist
            if [ -f ${runfolder}/resp.*.phys ] && [ -f ${runfolder}/card.*.phys ]; then

                # get dimension info from input file
                x=$(fslhd ${input}     | sed -n 6p  | cut -c 5-)
                y=$(fslhd ${input}     | sed -n 7p  | cut -c 5-)
                z=$(fslhd ${input}     | sed -n 8p  | cut -c 5-)
                ntrs=$(fslhd ${input}  | sed -n 9p  | cut -c 5-)
                tr=$(fslhd ${input}    | sed -n 22p | cut -c 9-)
                units=$(fslhd ${input} | sed -n 14p | cut -c 11- | xargs)

                # find the smallest dimension in x, y, z
                xyz=($x $y $z)
                slice=$(echo ${xyz[*]} | python -c "print sorted(map(int, raw_input().split(' ')))[0]")

                # get the number of samples in physio logs
                samp=$(cat ${runfolder}/resp.*.phys | wc -w)

                # convert ms to s to hz
                if [ ${units} = 's' ]; then
                    time=$(perl -e "print ${ntrs} * ${tr}")
                elif [ ${units} = 'ms' ]; then
                    time=$(perl -e "print ${ntrs} * ${tr} / 1000")
                fi
                fs=$(perl -e "print ${samp} / ${time}")

                # Run McRetroTS -- Respfile Cardfile VolTR Nslices PhysFS Graph
                # NB! Right now we are NOT using the slice-wise information,
                # as the slice-wise information assumes alternating+Z! Jeesh!
                ${McRetroTS} \
                    ${runfolder}/resp.*.phys ${runfolder}/card.*.phys ${tr} ${slice} ${fs} 0

                # Output both the single-slice and multi-slice data
                1dcat \
                    oba.slibase.1D[0..12]{${del}..$} > ${SESS}/PARAMS/phys.${ID}.${NUM}.1D

                1dcat \
                    oba.slibase.1D[0..$]{${del}..$} > ${SESS}/PARAMS/phys_slicewise.${ID}.${NUM}.1D
                rm oba.slibase*
            fi

            # delete initial time points
            3dcalc \
                -prefix ${SESS}/func_del.${ID}.${NUM}.nii.gz \
                -a "${SESS}/func_tmp_RAI.${ID}.${NUM}.nii.gz[${del}..$]" \
                -expr 'a'
            rm ${SESS}/func_tmp_*
        fi
    done
done

echo '*** MODULE: despike. Removes time series outliers via L1 regression. ***'
export input=func_del

# loop through sessions
DIR_SESS=`ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/`
for SESS in ${DIR_SESS}; do

    # loop through runs
    DIR_RUNS=`ls -d -- ${SESS}/RUN*`
    for RUN in ${DIR_RUNS}; do
        NUM=`basename ${RUN} | sed 's/[^0-9]//g'`

        if [ ! -f ${SESS}/func_despike.${ID}.${NUM}.nii.gz ]; then
	        3dDespike \
	            -prefix ${SESS}/func_despike.${ID}.${NUM}.nii.gz \
	            -ssave ${SESS}/PARAMS/spikes.${ID}.${NUM}.nii.gz \
	            -quiet \
	             ${SESS}/${input}.${ID}.${NUM}.nii.gz
        fi
    done
done

echo '*** MODULE: slice_time_correct. Corrects slice timing. *****************'
export input=func_despike
export direction=z
export ascending=yes
export interleave=yes

if [ ${ascending} = 'no' ]; then
    ascending='--down'
else
    ascending=''
fi

if [ ${interleave} = 'yes' ]; then
    interleave='--odd'
else
    interleave=''
fi

if [ ${direction} = 'x' ]; then
    direction=1
elif [ ${direction} = 'y' ]; then
    direction=2
else
    direction=3
fi

# loop through sessions
DIR_SESS=`ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/`
for SESS in ${DIR_SESS}; do

    # loop through runs
    DIR_RUNS=`ls -d -- ${SESS}/RUN*`
    for RUN in ${DIR_RUNS}; do
        NUM=`basename ${RUN} | sed 's/[^0-9]//g'`

        # slice time correction (can include specified timings)
        # NB: Physio regression must happen BEFORE NOW
        if [ ! -f ${SESS}/func_tshift.${ID}.${NUM}.nii.gz ]; then
            if [ -f ${RUN}/slice_timing.1D ]; then
                slicetimer \
                    -i ${SESS}/${input}.${ID}.${NUM}.nii.gz \
                    -o ${SESS}/func_tshift.${ID}.${NUM}.nii.gz \
                    --ocustom @ ${RUN}/slice_timing.1D
            else
                slicetimer \
                    -i ${SESS}/${input}.${ID}.${NUM}.nii.gz \
                    -o ${SESS}/func_tshift.${ID}.${NUM}.nii.gz \
                    -r ${tr} -d ${direction} ${ascending} ${interleave}
            fi
        fi
    done
done


echo '*** MODULE: motion_deskull. Motion correction and brain masking. ***'
export input=func_tshift
export masking=normal
export method=FSL

# loop through sessions
DIR_SESS=`ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/`
for SESS in ${DIR_SESS}; do

    # loop through runs
    DIR_RUNS=`ls -d -- ${SESS}/RUN*`
    for RUN in ${DIR_RUNS}; do
        NUM=`basename ${RUN} | sed 's/[^0-9]//g'`

        # deoblique and motion correct data
        if [ ! -f ${SESS}/func_motion.${ID}.${NUM}.nii.gz ]; then

            # motion correct to 9th sub-brick of 1st run
            3dvolreg \
                -prefix ${SESS}/func_motion.${ID}.${NUM}.nii.gz \
                -base ${SESS}/${input}.${ID}'.01.nii.gz[8]' \
                -twopass \
                -twoblur 3 \
                -twodup \
                -coarse 10 3 \
                -Fourier \
                -zpad 10 \
                -float \
                -1Dfile ${SESS}/PARAMS/motion.${ID}.${NUM}.1D \
                -1Dmatrix_save ${SESS}/PARAMS/3dvolreg.${ID}.${NUM}.aff12.1D \
                ${SESS}/${input}.${ID}.${NUM}.nii.gz

            # create lagged motion regressors
            if [ ! -f ${SESS}/PARAMS/lag.motion.${ID}.${NUM}.1D ]; then
                1dcat \
                    ${SESS}/PARAMS/motion.${ID}.${NUM}.1D'{0}' > \
                    ${SESS}/PARAMS/lag.motion.${ID}.${NUM}.1D

                1dcat \
                    ${SESS}/PARAMS/motion.${ID}.${NUM}.1D'{0..$}' >> \
                    ${SESS}/PARAMS/lag.motion.${ID}.${NUM}.1D
            fi

            # create derivative of motion regressors
            if [ ! -f ${SESS}/PARAMS/dif.motion.${ID}.${NUM}.1D ]; then
                1d_tool.py \
                    -infile ${SESS}/PARAMS/motion.${ID}.${NUM}.1D \
                    -backward_diff \
                    -write ${SESS}/PARAMS/dif.motion.${ID}.${NUM}.1D
            fi

            # make a registration volume for low-quality data if required
            if [ -f ${SESS}/anat_EPI_initTR.nii.gz ] && [ ${NUM} = 01 ] && [ ! -f ${SESS}/anat_EPI_initTR_reg.nii.gz ]; then

                # deoblique registration volume
                3dWarp \
                    -prefix ${SESS}/anat_EPI_initTR_ob.nii.gz \
                    -deoblique \
                    -quintic \
                    -verb \
                    -gridset ${SESS}/${input}.01.nii.gz \
                    ${SESS}/anat_EPI_initTR.nii.gz

                # align registration volume with the motion correction TR
                3dvolreg \
                    -prefix ${SESS}/anat_EPI_initTR_reg.nii.gz \
                    -base ${SESS}/${input}.${ID}.'01.nii.gz[8]' \
                    -twopass \
                    -twoblur 3 \
                    -twodup \
                    -Fourier \
                    -zpad 2 \
                    -float \
                    ${SESS}/anat_EPI_initTR_ob.nii.gz
            fi
        fi

        # create TS mean for each run
        if [ ! -f ${SESS}/anat_EPI_brain.nii.gz ]; then
            3dTstat \
                -prefix ${SESS}/anat_EPI_ts_mean.${ID}.${NUM}.nii.gz \
                ${SESS}/func_motion.${ID}.${NUM}.nii.gz
        fi

    done

    # create session 3D EPI brain + mask (loosened peels)
    if [ ! -f ${SESS}/anat_EPI_brain.nii.gz ]; then
        # create mean over all runs
        3dMean \
            -prefix ${SESS}/anat_EPI_tmp_mean.nii.gz \
            ${SESS}/anat_EPI_ts_mean.${ID}.*.nii.gz

        3dTstat \
            -prefix ${SESS}/anat_EPI_tmp_vol.nii.gz \
            ${SESS}/anat_EPI_tmp_mean.nii.gz

        # AFNI
        if [ ${method} == 'AFNI' ]; then

            # set masking variables given each preset
            if [ ${masking} == 'loosest' ]; then CLFRAC=0.15; PEELS=1; fi
            if [ ${masking} == 'loose' ]; then CLFRAC=0.2; PEELS=1; fi
            if [ ${masking} == 'normal' ]; then CLFRAC=0.3; PEELS=3; fi
            if [ ${masking} == 'tight' ]; then CLFRAC=0.5; PEELS=3; fi

            # compute the mask using 3dAutomask, dilate
            3dAutomask \
                -prefix ${SESS}/anat_EPI_tmp_mask.nii.gz \
                -clfrac ${CLFRAC} \
                -peels ${PEELS} \
                ${SESS}/anat_EPI_tmp_vol.nii.gz
            3dcalc \
                -prefix ${SESS}/anat_EPI_mask.nii.gz \
                -a ${SESS}/anat_EPI_tmp_mask.nii.gz \
                -b a+i -c a-i -d a+j -e a-j -f a+k -g a-k \
                -expr 'amongst(1,a,b,c,d,e,f,g)'
        fi

        # FSL
        if [ ${method} == 'FSL' ]; then

            # set masking variables given each preset
            if [ ${masking} == 'loosest' ]; then FI=0.15; VG=0.4; fi
            if [ ${masking} == 'loose' ]; then FI=0.2; VG=0; fi
            if [ ${masking} == 'normal' ]; then FI=0.3; VG=0; fi
            if [ ${masking} == 'tight' ]; then FI=0.5; VG=0; fi

            # compute the mask using robust BET, dilate
            bet \
                ${SESS}/anat_EPI_tmp_vol.nii.gz \
                ${SESS}/anat_EPI_mask.nii.gz \
                -R -n -m \
                -f ${FI} \
                -g ${VG}
            fslmaths \
                ${SESS}/anat_EPI_mask_mask.nii.gz \
                -dilD \
                ${SESS}/anat_EPI_mask_mask_dil.nii.gz
            rm ${SESS}/anat_EPI_mask.nii.gz
            rm ${SESS}/anat_EPI_mask_mask.nii.gz
            mv ${SESS}/anat_EPI_mask_mask_dil.nii.gz ${SESS}/anat_EPI_mask.nii.gz
        fi

        # deskull anat_EPI
        3dcalc \
            -prefix ${SESS}/anat_EPI_brain.nii.gz \
            -a ${SESS}/anat_EPI_tmp_vol.nii.gz \
            -b ${SESS}/anat_EPI_mask.nii.gz \
            -expr 'a*b'
        rm ${SESS}/anat_EPI_tmp*
    fi

    # deskull anat_EPI_initTR if required
    if [ ! -f ${SESS}/anat_EPI_initTR_brain.nii.gz ]; then
        if [ ${DATA_QUALITY} = 'low' ]; then
            3dcalc \
                -prefix ${SESS}/anat_EPI_initTR_brain.nii.gz \
                -a ${SESS}/anat_EPI_initTR_reg.nii.gz \
                -b ${SESS}/anat_EPI_mask.nii.gz \
                -expr 'a*b'
        fi
    fi

    # loop through runs
    DIR_RUNS=`ls -d -- ${SESS}/RUN*`
    for RUN in ${DIR_RUNS}; do
        NUM=`basename ${RUN} | sed 's/[^0-9]//g'`

        # deskull functional data
        if [ ! -f ${SESS}/func_deskull.${ID}.${NUM}.nii.gz ]; then
            3dcalc \
                -prefix ${SESS}/func_deskull.${ID}.${NUM}.nii.gz \
                -datum float \
                -a ${SESS}/${input}.${ID}.${NUM}.nii.gz \
                -b ${SESS}/anat_EPI_mask.nii.gz \
                -expr "a*b"
        fi
    done
done

echo '*** MODULE: scale. Normalizes time series. *****************************'
export input=func_deskull
export normalize=scale

# loop through sessions
DIR_SESS=`ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/`
for SESS in ${DIR_SESS}; do

    # loop through runs
    DIR_RUNS=`ls -d -- ${SESS}/RUN*`
    for RUN in ${DIR_RUNS}; do
        NUM=`basename ${RUN} | sed 's/[^0-9]//g'`

        if [ ! -f ${SESS}/func_scaled.${ID}.${NUM}.nii.gz ]; then

            # calculate time series mean
            3dTstat \
                -prefix ${SESS}/func_tmp_mean.${ID}.${NUM}.nii.gz \
                -mean \
                ${SESS}/${input}.${ID}.${NUM}.nii.gz

            # % SIGNAL CHANGE: mean = 0, 1% == 1 (normalized by mean)... careful using this with event-related designs
            if [ ${normalize} == 'pct' ]; then
                3dcalc \
                   -prefix ${SESS}/func_scaled.${ID}.${NUM}.nii.gz \
                   -datum float \
                   -a ${SESS}/${input}.${ID}.${NUM}.nii.gz \
                   -b ${SESS}/func_tmp_mean.${ID}.${NUM}.nii.gz \
                   -c ${SESS}/anat_EPI_mask.nii.gz \
                   -expr "(a-b)/b*c*100"
            fi

            # SCALE: set global mean = 1000, arbitrary units, no normalization
            if [ ${normalize} == 'scale' ]; then
                MEAN=$(3dmaskave -quiet -mask ${SESS}/anat_EPI_brain.nii.gz ${SESS}/func_tmp_mean.${ID}.${NUM}.nii.gz)
                3dcalc \
                    -prefix ${SESS}/func_scaled.${ID}.${NUM}.nii.gz \
                    -datum float \
                    -a ${SESS}/${input}.${ID}.${NUM}.nii.gz \
                    -b ${SESS}/anat_EPI_mask.nii.gz \
                    -expr "a*(1000/${MEAN})*b"
            fi
            rm ${SESS}/func_tmp_mean.${ID}.${NUM}.nii.gz
        fi
    done
done

echo '*** MODULE: linreg_calc_fsl. Calculates EPI <--> T1 <--> MNI152. *******'
export data_quality=high
export cost=corratio
export reg_dof=6

dir_pipe=$(dirname $(dirname $(which epi-lowpass)))

# Copy MNI brain to experiment directory
if [ ! -f ${DIR_DATA}/${DIR_EXPT}/anat_MNI.nii.gz ]; then
    cp ${dir_pipe}/assets/MNI152_T1_1mm_brain.nii.gz ${DIR_DATA}/${DIR_EXPT}/anat_MNI.nii.gz
    cp ${dir_pipe}/assets/MNI152_T1_1mm_brain_mask_dil.nii.gz ${DIR_DATA}/${DIR_EXPT}/anat_MNI_mask.nii.gz
fi

DIR_SESS=`ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/`
for SESS in ${DIR_SESS}; do
    SESS=$(basename ${SESS})
    DIR=`echo ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}`
    DIR_T1=`echo ${DIR_DATA}/${DIR_EXPT}/${SUB}/T1`

    # figure out if we should use each session's T1, or just the first session
    if [ $(ls -l ${DIR} | grep ^d | wc -l) -eq $(ls -l ${DIR_T1} | grep ^d | wc -l) ]; then
        multisession=1
    else
        multisession=0
    fi

    if [ ${multisession} -eq 1 ]; then
        ANAT_T1=`echo ${DIR_T1}/${SESS}/anat_T1_brain.nii.gz`
    else
        ANAT_T1=`echo ${DIR_T1}/SESS01/anat_T1_brain.nii.gz`
    fi

    # Set EPI data file (for low vs high quality data).
    if [ ${data_quality} = 'low' ]; then
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
            -dof ${reg_dof} \
            -cost ${cost} \
            -searchcost ${cost} \
            -searchrx -180 180 -searchry -180 180 -searchrz -180 180

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
            -init ${DIR}/${SESS}/mat_T1_to_EPI.mat
    fi

    # calculate registration of T1 to reg_T1_to_TAL
    if [ ! -f ${DIR}/${SESS}/mat_TAL_to_T1.mat ]; then
        flirt \
            -in ${ANAT_T1} \
            -ref ${FSLDIR}/data/standard/MNI152_T1_2mm_brain.nii.gz \
            -out ${DIR}/${SESS}/reg_T1_to_TAL.nii.gz \
            -omat ${DIR}/${SESS}/mat_T1_to_TAL.mat \
            -dof 12 \
            -searchcost corratio \
            -cost corratio

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
done

echo '*** MODULE: nonlinreg_calc_fsl. Calcs MNI warp from linreg outputs. ****'

DIR_SESS=$(ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/)
for SESS in ${DIR_SESS}; do
    SESS=$(basename ${SESS})
    DIR="${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}"

    # calculate nonlinear warp of T1 to MNI space
    if [ ! -f ${DIR}/${SESS}/reg_nlin_TAL_WARP.nii.gz ]; then
        fnirt \
            --ref=${DIR_DATA}/${DIR_EXPT}/anat_MNI.nii.gz \
            --refmask=${DIR_DATA}/${DIR_EXPT}/anat_MNI_mask.nii.gz \
            --in=${DIR}/${SESS}/reg_T1_to_TAL.nii.gz \
            --config=T1_2_MNI152_2mm.cnf \
            --iout=${DIR}/${SESS}/reg_nlin_TAL.nii.gz \
            --fout=${DIR}/${SESS}/reg_nlin_TAL_FIELD.nii.gz \
            --cout=${DIR}/${SESS}/reg_nlin_TAL_WARP.nii.gz \
            --intout=${DIR}/${SESS}/reg_nlin_TAL_INTOUT.nii.gz \
            --interp=spline
    fi
done

echo '*** MODULE: linreg_fs2epi_fsl. Puts freesurfer atlases in EPI space. ***'

DIR_SESS=$(ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/)
for SESS in ${DIR_SESS}; do
    SESS=$(basename ${SESS})
    DIR=$(echo ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/${SESS})
    DIR_T1=$(echo ${DIR_DATA}/${DIR_EXPT}/${SUB}/T1)

    if [ ${multisession} -eq 1 ]; then
        DIR_T1="${DIR_DATA}/${DIR_EXPT}/${SUB}/T1/${SESS}"
    else
        DIR_T1="${DIR_DATA}/${DIR_EXPT}/${SUB}/T1/SESS01)"
    fi

    # register aparc atlas to EPI
    if [ ! -f ${DIR}/anat_aparc_reg.nii.gz ]; then
        flirt \
            -in ${DIR_T1}/anat_aparc_brain.nii.gz \
            -ref ${DIR}/anat_EPI_brain.nii.gz \
            -applyxfm -init ${DIR}/mat_T1_to_EPI.mat \
            -interp nearestneighbour \
            -out ${DIR}/anat_aparc_reg.nii.gz
    fi

    # register aparc2009 atlas to EPI
    if [ ! -f ${DIR}/anat_aparc2009_reg.nii.gz ]; then
        flirt \
            -in ${DIR_T1}/anat_aparc2009_brain.nii.gz \
            -ref ${DIR}/anat_EPI_brain.nii.gz \
            -applyxfm -init ${DIR}/mat_T1_to_EPI.mat \
            -interp nearestneighbour \
            -out ${DIR}/anat_aparc2009_reg.nii.gz
    fi
done

echo '*** MODULE: filter. Applies regression models of noise sources. ********'
export INPUT=func_scaled
export POLORT=2
export DIFF=on
export LAG=off
export SQ=on
export STD=on
export GM=on
export DV=off
export ANATICOR=off
export COMPCOR=3
export MASK=anat_EPI_mask

DIR_SESS=`ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/`
for SESS in ${DIR_SESS}; do

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
            -h ${SESS}/${MASK}.nii.gz \
            -expr 'a*(1-amongst(0,b,c,d,e,f,g))*h' \
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
            -c ${SESS}/${MASK}.nii.gz \
            -expr 'a-step(a*b)*c' \
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
            -a ${SESS}/${MASK}.nii.gz \
            -b a+i -c a-i -d a+j -e a-j -f a+k -g a-k \
            -expr 'amongst(1,a,b,c,d,e,f,g)' \
            -prefix ${SESS}/anat_EPI_mask_dia.nii.gz
    fi

    # brainstem mask
    if [ ! -f ${SESS}/anat_bstem.nii.gz ]; then
        3dcalc \
            -a ${SESS}/anat_aparc_reg.nii.gz \
            -b ${SESS}/${MASK}.nii.gz \
            -expr "equals(a,8)*b  + \
                   equals(a,47)*b + \
                   equals(a,16)*b + \
                   equals(a,12)*b + \
                   equals(a,13)*b + \
                   equals(a,26)*b + \
                   equals(a,51)*b + \
                   equals(a,52)*b + \
                   equals(a,17)*b + \
                   equals(a,18)*b + \
                   equals(a,53)*b + \
                   equals(a,54)*b + \
                   equals(a,58)*b + \
                   equals(a,28)*b + \
                   equals(a,60)*b" \
            -prefix ${SESS}/anat_bstem.nii.gz
    fi

    # eroded draining vessel mask
    if [ ! -f ${SESS}/anat_dv_ero.nii.gz ]; then
        3dcalc \
            -a ${SESS}/${MASK}.nii.gz \
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

        if [ ! -f ${SESS}/func_filtered.${ID}.${NUM}.nii.gz ]; then

            # compute mean, standard deviation
            3dTstat \
                -prefix ${SESS}/func_tmp_mean.${ID}.${NUM}.nii.gz \
                -mean ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz

            3dTstat \
                -prefix ${SESS}/func_tmp_stdev.${ID}.${NUM}.nii.gz \
                -stdev ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz

            # compute temporal SNR (pre anything)
            3dcalc \
                -a ${SESS}/func_tmp_mean.${ID}.${NUM}.nii.gz \
                -b ${SESS}/func_tmp_stdev.${ID}.${NUM}.nii.gz \
                -expr 'a/b' \
                -prefix ${SESS}/func_tSNR.${ID}.${NUM}.nii.gz

            # input data detrend (before calculating regressors...)
            3dDetrend \
                -prefix ${SESS}/func_tmp_det.${ID}.${NUM}.nii.gz \
                -polort ${POLORT} \
                ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz

            # motion paramaters, detrend, lag, dif, sq
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

            3dDetrend \
                -prefix - \
                -DAFNI_1D_TRANOUT=YES \
                -polort ${POLORT} \
                ${SESS}/PARAMS/dif.motion.${ID}.${NUM}.1D\' > \
                ${SESS}/PARAMS/det.dif.motion.${ID}.${NUM}.1D

            # squares of detrended head motion
            1deval \
                -a ${SESS}/PARAMS/det.motion.${ID}.${NUM}.1D[0] \
                -expr 'a^2' > ${SESS}/PARAMS/sq.1.det.motion.${ID}.${NUM}.1D
            1deval \
                -a ${SESS}/PARAMS/det.motion.${ID}.${NUM}.1D[1] \
                -expr 'a^2' > ${SESS}/PARAMS/sq.2.det.motion.${ID}.${NUM}.1D
            1deval \
                -a ${SESS}/PARAMS/det.motion.${ID}.${NUM}.1D[2] \
                -expr 'a^2' > ${SESS}/PARAMS/sq.3.det.motion.${ID}.${NUM}.1D
            1deval \
                -a ${SESS}/PARAMS/det.motion.${ID}.${NUM}.1D[3] \
                -expr 'a^2' > ${SESS}/PARAMS/sq.4.det.motion.${ID}.${NUM}.1D
            1deval \
                -a ${SESS}/PARAMS/det.motion.${ID}.${NUM}.1D[4] \
                -expr 'a^2' > ${SESS}/PARAMS/sq.5.det.motion.${ID}.${NUM}.1D
            1deval \
                -a ${SESS}/PARAMS/det.motion.${ID}.${NUM}.1D[5] \
                -expr 'a^2' > ${SESS}/PARAMS/sq.6.det.motion.${ID}.${NUM}.1D

            # squares of detrended + lagged head motion
            1deval \
                -a ${SESS}/PARAMS/det.lag.motion.${ID}.${NUM}.1D[0] \
                -expr 'a^2' > ${SESS}/PARAMS/sq.1.det.lag.motion.${ID}.${NUM}.1D
            1deval \
                -a ${SESS}/PARAMS/det.lag.motion.${ID}.${NUM}.1D[1] \
                -expr 'a^2' > ${SESS}/PARAMS/sq.2.det.lag.motion.${ID}.${NUM}.1D
            1deval \
                -a ${SESS}/PARAMS/det.lag.motion.${ID}.${NUM}.1D[2] \
                -expr 'a^2' > ${SESS}/PARAMS/sq.3.det.lag.motion.${ID}.${NUM}.1D
            1deval \
                -a ${SESS}/PARAMS/det.lag.motion.${ID}.${NUM}.1D[3] \
                -expr 'a^2' > ${SESS}/PARAMS/sq.4.det.lag.motion.${ID}.${NUM}.1D
            1deval \
                -a ${SESS}/PARAMS/det.lag.motion.${ID}.${NUM}.1D[4] \
                -expr 'a^2' > ${SESS}/PARAMS/sq.5.det.lag.motion.${ID}.${NUM}.1D
            1deval \
                -a ${SESS}/PARAMS/det.lag.motion.${ID}.${NUM}.1D[5] \
                -expr 'a^2' > ${SESS}/PARAMS/sq.6.det.lag.motion.${ID}.${NUM}.1D

            # diff of detrended + squared head motion
            1d_tool.py \
                -infile ${SESS}/PARAMS/sq.1.det.motion.${ID}.${NUM}.1D \
                -backward_diff \
                -overwrite \
                -write ${SESS}/PARAMS/dif.sq.1.det.motion.${ID}.${NUM}.1D
            1d_tool.py \
                -infile ${SESS}/PARAMS/sq.2.det.motion.${ID}.${NUM}.1D \
                -backward_diff \
                -overwrite \
                -write ${SESS}/PARAMS/dif.sq.2.det.motion.${ID}.${NUM}.1D
            1d_tool.py \
                -infile ${SESS}/PARAMS/sq.3.det.motion.${ID}.${NUM}.1D \
                -backward_diff \
                -overwrite \
                -write ${SESS}/PARAMS/dif.sq.3.det.motion.${ID}.${NUM}.1D
            1d_tool.py \
                -infile ${SESS}/PARAMS/sq.4.det.motion.${ID}.${NUM}.1D \
                -backward_diff \
                -overwrite \
                -write ${SESS}/PARAMS/dif.sq.4.det.motion.${ID}.${NUM}.1D
            1d_tool.py \
                -infile ${SESS}/PARAMS/sq.5.det.motion.${ID}.${NUM}.1D \
                -backward_diff \
                -overwrite \
                -write ${SESS}/PARAMS/dif.sq.5.det.motion.${ID}.${NUM}.1D
            1d_tool.py \
                -infile ${SESS}/PARAMS/sq.6.det.motion.${ID}.${NUM}.1D \
                -backward_diff \
                -overwrite \
                -write ${SESS}/PARAMS/dif.sq.6.det.motion.${ID}.${NUM}.1D

            # detrend physiological regressors, if they exist
            if [ -f ${SESS}/PARAMS/phys.${ID}.${NUM}.1D ]; then
                3dDetrend \
                    -prefix - \
                    -DAFNI_1D_TRANOUT=YES \
                    -polort ${POLORT} \
                    ${SESS}/PARAMS/phys.${ID}.${NUM}.1D\' > \
                    ${SESS}/PARAMS/det.phys.${ID}.${NUM}.1D
            fi

            # initialize filter command
            CMD=`echo 3dTfitter \
                          -prefix ${SESS}/func_noise_betas.${ID}.${NUM}.nii.gz \
                          -fitts ${SESS}/func_noise.${ID}.${NUM}.nii.gz \
                          -polort 0 \
                          -quiet \
                          -RHS ${SESS}/func_tmp_det.${ID}.${NUM}.nii.gz \
                          -LHS `

            # add the physio regressors if they exist
            if [ -f ${SESS}/PARAMS/det.phys.${ID}.${NUM}.1D ]; then
                CMD=`echo ${CMD} ${SESS}/PARAMS/det.phys.${ID}.${NUM}.1D`
            fi

            if [ `echo ${STD}` = 'on' ]; then

                # white matter mean, lag, dif, sq
                3dmaskave \
                    -q -mask ${SESS}/anat_wm.nii.gz \
                    ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz > \
                    ${SESS}/PARAMS/wm.${ID}.${NUM}.1D
                1dcat \
                    ${SESS}/PARAMS/wm.${ID}.${NUM}.1D'{0}' > \
                    ${SESS}/PARAMS/lag.wm.${ID}.${NUM}.1D
                1dcat \
                    ${SESS}/PARAMS/wm.${ID}.${NUM}.1D'{0..$}' >> \
                    ${SESS}/PARAMS/lag.wm.${ID}.${NUM}.1D
                1d_tool.py \
                    -infile ${SESS}/PARAMS/wm.${ID}.${NUM}.1D \
                    -backward_diff \
                    -overwrite \
                    -write ${SESS}/PARAMS/dif.wm.${ID}.${NUM}.1D
                1deval \
                    -a ${SESS}/PARAMS/wm.${ID}.${NUM}.1D \
                    -expr 'a^2' > ${SESS}/PARAMS/sq.wm.${ID}.${NUM}.1D
                1deval \
                    -a ${SESS}/PARAMS/lag.wm.${ID}.${NUM}.1D \
                    -expr 'a^2' > ${SESS}/PARAMS/sq.lag.wm.${ID}.${NUM}.1D
                1d_tool.py \
                    -infile ${SESS}/PARAMS/sq.wm.${ID}.${NUM}.1D \
                    -backward_diff \
                    -overwrite \
                    -write ${SESS}/PARAMS/dif.sq.wm.${ID}.${NUM}.1D

                # ventricle mean, lag, dif, sq
                3dmaskave \
                    -q -mask ${SESS}/anat_vent.nii.gz \
                    ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz > \
                    ${SESS}/PARAMS/vent.${ID}.${NUM}.1D
                1dcat \
                    ${SESS}/PARAMS/vent.${ID}.${NUM}.1D'{0}' > \
                    ${SESS}/PARAMS/lag.vent.${ID}.${NUM}.1D
                1dcat \
                    ${SESS}/PARAMS/vent.${ID}.${NUM}.1D'{0..$}' >> \
                    ${SESS}/PARAMS/lag.vent.${ID}.${NUM}.1D
                1d_tool.py \
                    -infile ${SESS}/PARAMS/vent.${ID}.${NUM}.1D \
                    -backward_diff \
                    -overwrite \
                    -write ${SESS}/PARAMS/dif.vent.${ID}.${NUM}.1D
                1deval \
                    -a ${SESS}/PARAMS/vent.${ID}.${NUM}.1D \
                    -expr 'a^2' > ${SESS}/PARAMS/sq.vent.${ID}.${NUM}.1D
                1deval \
                    -a ${SESS}/PARAMS/lag.vent.${ID}.${NUM}.1D \
                    -expr 'a^2' > ${SESS}/PARAMS/sq.lag.vent.${ID}.${NUM}.1D
                1d_tool.py \
                    -infile ${SESS}/PARAMS/sq.vent.${ID}.${NUM}.1D \
                    -backward_diff \
                    -overwrite \
                    -write ${SESS}/PARAMS/dif.sq.vent.${ID}.${NUM}.1D

                CMD=`echo ${CMD} ${SESS}/PARAMS/det.motion.${ID}.${NUM}.1D`
                CMD=`echo ${CMD} ${SESS}/PARAMS/vent.${ID}.${NUM}.1D`
                CMD=`echo ${CMD} ${SESS}/PARAMS/wm.${ID}.${NUM}.1D`

                if [ `echo ${SQ}` = 'on' ]; then
                    CMD=`echo ${CMD} ${SESS}/PARAMS/sq.1.det.motion.${ID}.${NUM}.1D`
                    CMD=`echo ${CMD} ${SESS}/PARAMS/sq.2.det.motion.${ID}.${NUM}.1D`
                    CMD=`echo ${CMD} ${SESS}/PARAMS/sq.3.det.motion.${ID}.${NUM}.1D`
                    CMD=`echo ${CMD} ${SESS}/PARAMS/sq.4.det.motion.${ID}.${NUM}.1D`
                    CMD=`echo ${CMD} ${SESS}/PARAMS/sq.5.det.motion.${ID}.${NUM}.1D`
                    CMD=`echo ${CMD} ${SESS}/PARAMS/sq.6.det.motion.${ID}.${NUM}.1D`
                    CMD=`echo ${CMD} ${SESS}/PARAMS/sq.vent.${ID}.${NUM}.1D`
                    CMD=`echo ${CMD} ${SESS}/PARAMS/sq.wm.${ID}.${NUM}.1D`

                    if [ `echo ${DIFF}` = 'on' ]; then
                        CMD=`echo ${CMD} ${SESS}/PARAMS/dif.sq.1.det.motion.${ID}.${NUM}.1D`
                        CMD=`echo ${CMD} ${SESS}/PARAMS/dif.sq.2.det.motion.${ID}.${NUM}.1D`
                        CMD=`echo ${CMD} ${SESS}/PARAMS/dif.sq.3.det.motion.${ID}.${NUM}.1D`
                        CMD=`echo ${CMD} ${SESS}/PARAMS/dif.sq.4.det.motion.${ID}.${NUM}.1D`
                        CMD=`echo ${CMD} ${SESS}/PARAMS/dif.sq.5.det.motion.${ID}.${NUM}.1D`
                        CMD=`echo ${CMD} ${SESS}/PARAMS/dif.sq.6.det.motion.${ID}.${NUM}.1D`
                        CMD=`echo ${CMD} ${SESS}/PARAMS/dif.sq.vent.${ID}.${NUM}.1D`
                        CMD=`echo ${CMD} ${SESS}/PARAMS/dif.sq.wm.${ID}.${NUM}.1D`
                    fi

                fi

                if [ `echo ${DIFF}` = 'on' ]; then
                    CMD=`echo ${CMD} ${SESS}/PARAMS/det.dif.motion.${ID}.${NUM}.1D`
                    CMD=`echo ${CMD} ${SESS}/PARAMS/dif.vent.${ID}.${NUM}.1D`
                    CMD=`echo ${CMD} ${SESS}/PARAMS/dif.wm.${ID}.${NUM}.1D`
                fi

                # note the difference in the order of operations from the diff method,
                # above. It isn't clear to me if there is a meaningful difference in the
                # lag case. -- jdv may 2015
                if [ `echo ${LAG}` == 'on' ]; then
                    CMD=`echo ${CMD} ${SESS}/PARAMS/det.lag.motion.${ID}.${NUM}.1D`
                    CMD=`echo ${CMD} ${SESS}/PARAMS/lag.vent.${ID}.${NUM}.1D`
                    CMD=`echo ${CMD} ${SESS}/PARAMS/lag.wm.${ID}.${NUM}.1D`

                    if [ `echo ${SQ}` = 'on' ]; then
                        CMD=`echo ${CMD} ${SESS}/PARAMS/sq.1.det.lag.motion.${ID}.${NUM}.1D`
                        CMD=`echo ${CMD} ${SESS}/PARAMS/sq.2.det.lag.motion.${ID}.${NUM}.1D`
                        CMD=`echo ${CMD} ${SESS}/PARAMS/sq.3.det.lag.motion.${ID}.${NUM}.1D`
                        CMD=`echo ${CMD} ${SESS}/PARAMS/sq.4.det.lag.motion.${ID}.${NUM}.1D`
                        CMD=`echo ${CMD} ${SESS}/PARAMS/sq.5.det.lag.motion.${ID}.${NUM}.1D`
                        CMD=`echo ${CMD} ${SESS}/PARAMS/sq.6.det.lag.motion.${ID}.${NUM}.1D`
                        CMD=`echo ${CMD} ${SESS}/PARAMS/sq.lag.vent.${ID}.${NUM}.1D`
                        CMD=`echo ${CMD} ${SESS}/PARAMS/sq.lag.wm.${ID}.${NUM}.1D`
                    fi
                fi
            fi

            if [ ${GM} = 'on' ]; then

                # global mean, lag, dif, sq
                3dmaskave \
                    -mask ${SESS}/anat_EPI_mask.nii.gz \
                    -quiet ${SESS}/func_tmp_det.${ID}.${NUM}.nii.gz \
                    > ${SESS}/PARAMS/global_mean.${ID}.${NUM}.1D
                1dcat \
                    ${SESS}/PARAMS/global_mean.${ID}.${NUM}.1D'{0}' > \
                    ${SESS}/PARAMS/lag.global_mean.${ID}.${NUM}.1D
                1dcat \
                    ${SESS}/PARAMS/global_mean.${ID}.${NUM}.1D'{0..$}' >> \
                    ${SESS}/PARAMS/lag.global_mean.${ID}.${NUM}.1D
                1d_tool.py \
                    -infile ${SESS}/PARAMS/global_mean.${ID}.${NUM}.1D \
                    -backward_diff \
                    -overwrite \
                    -write ${SESS}/PARAMS/dif.global_mean.${ID}.${NUM}.1D
                1deval \
                    -a ${SESS}/PARAMS/global_mean.${ID}.${NUM}.1D \
                    -expr 'a^2' > ${SESS}/PARAMS/sq.global_mean.${ID}.${NUM}.1D
                1deval \
                    -a ${SESS}/PARAMS/lag.global_mean.${ID}.${NUM}.1D \
                    -expr 'a^2' > ${SESS}/PARAMS/sq.lag.global_mean.${ID}.${NUM}.1D
                1d_tool.py \
                    -infile ${SESS}/PARAMS/sq.global_mean.${ID}.${NUM}.1D \
                    -backward_diff \
                    -overwrite \
                    -write ${SESS}/PARAMS/dif.sq.global_mean.${ID}.${NUM}.1D

                CMD=`echo ${CMD} ${SESS}/PARAMS/global_mean.${ID}.${NUM}.1D`
                if [ `echo ${SQ}` = 'on' ]; then
                    CMD=`echo ${CMD} ${SESS}/PARAMS/sq.global_mean.${ID}.${NUM}.1D`

                    if [ `echo ${DIFF}` = 'on' ]; then
                        CMD=`echo ${CMD} ${SESS}/PARAMS/dif.sq.global_mean.${ID}.${NUM}.1D`
                    fi
                fi

                if [ `echo ${DIFF}` = 'on' ]; then
                    CMD=`echo ${CMD} ${SESS}/PARAMS/dif.global_mean.${ID}.${NUM}.1D`
                fi

                # note the difference in the order of operations from the diff method,
                # above. It isn't clear to me if there is a meaningful difference in the
                # lag case. -- jdv may 2015
                if [ `echo ${LAG}` = 'on' ]; then
                    CMD=`echo ${CMD} ${SESS}/PARAMS/lag.global_mean.${ID}.${NUM}.1D`

                    if [ `echo ${SQ}` = 'on' ]; then
                        CMD=`echo ${CMD} ${SESS}/PARAMS/sq.lag.global_mean.${ID}.${NUM}.1D`
                    fi
                fi
            fi

            if [ `echo ${DV}` = 'on' ]; then

                # draining vessel mean, lag, dif, sq
                3dmaskave \
                    -q -mask ${SESS}/anat_dv.nii.gz \
                    ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz > \
                    ${SESS}/PARAMS/dv.${ID}.${NUM}.1D
                1dcat \
                    ${SESS}/PARAMS/dv.${ID}.${NUM}.1D'{0}' > \
                    ${SESS}/PARAMS/lag.dv.${ID}.${NUM}.1D
                1dcat \
                    ${SESS}/PARAMS/dv.${ID}.${NUM}.1D'{0..$}' >> \
                    ${SESS}/PARAMS/lag.dv.${ID}.${NUM}.1D
                1d_tool.py \
                    -infile ${SESS}/PARAMS/dv.${ID}.${NUM}.1D \
                    -backward_diff \
                    -overwrite \
                    -write ${SESS}/PARAMS/dif.dv.${ID}.${NUM}.1D
                1deval \
                    -a ${SESS}/PARAMS/dv.${ID}.${NUM}.1D \
                    -expr 'a^2' > ${SESS}/PARAMS/sq.dv.${ID}.${NUM}.1D
                1deval \
                    -a ${SESS}/PARAMS/lag.dv.${ID}.${NUM}.1D \
                    -expr 'a^2' > ${SESS}/PARAMS/sq.lag.dv.${ID}.${NUM}.1D
                1d_tool.py \
                    -infile ${SESS}/PARAMS/sq.dv.${ID}.${NUM}.1D \
                    -backward_diff \
                    -overwrite \
                    -write ${SESS}/PARAMS/dif.sq.dv.${ID}.${NUM}.1D

                CMD=`echo ${CMD} ${SESS}/PARAMS/dv.${ID}.${NUM}.1D`
                if [ `echo ${SQ}` = 'on' ]; then
                    CMD=`echo ${CMD} ${SESS}/PARAMS/sq.dv.${ID}.${NUM}.1D`

                    if [ `echo ${DIFF}` = 'on' ]; then
                        CMD=`echo ${CMD} ${SESS}/PARAMS/dif.sq.dv.${ID}.${NUM}.1D`
                    fi
                fi

                if [ `echo ${DIFF}` = 'on' ]; then
                    CMD=`echo ${CMD} ${SESS}/PARAMS/dif.dv.${ID}.${NUM}.1D`
                fi

                # note the difference in the order of operations from the diff method,
                # above. It isn't clear to me if there is a meaningful difference in the
                # lag case. -- jdv may 2015
                if [ `echo ${LAG}` = 'on' ]; then
                    CMD=`echo ${CMD} ${SESS}/PARAMS/lag.dv.${ID}.${NUM}.1D`

                    if [ `echo ${SQ}` = 'on' ]; then
                        CMD=`echo ${CMD} ${SESS}/PARAMS/sq.lag.dv.${ID}.${NUM}.1D`
                    fi
                fi
            fi

            if [ `echo ${ANATICOR}` = 'on' ]; then

                # local white matter (+ lag)
                if [ ! -f ${SESS}/PARAMS/lag.wm_local15.${ID}.${NUM}.nii.gz ]; then
                    3dLocalstat \
                        -prefix ${SESS}/PARAMS/wm_local15.${ID}.${NUM}.nii.gz \
                        -nbhd 'SPHERE(15)' \
                        -stat mean \
                        -mask ${SESS}/anat_wm.nii.gz \
                        -use_nonmask ${SESS}/${INPUT}.${ID}.${NUM}.nii.gz

                    3dTcat \
                        -prefix ${SESS}/PARAMS/lag.wm_local15.${ID}.${NUM}.nii.gz \
                        ${SESS}/PARAMS/wm_local15.${ID}.${NUM}.nii.gz'[0]' \
                        ${SESS}/PARAMS/wm_local15.${ID}.${NUM}.nii.gz'[0..$]'
                fi

                CMD=`echo ${CMD} ${SESS}/PARAMS/wm_local15.${ID}.${NUM}.nii.gz`
                CMD=`echo ${CMD} ${SESS}/PARAMS/lag.wm_local15.${ID}.${NUM}.nii.gz`
            fi

            if [ ${COMPCOR} -gt 0 ]; then

                # aCompcor regressors for WM and ventricles
                if [ ! -f ${SESS}/PARAMS/vent_pc.${ID}.${NUM}.1D ]; then
                    epi-genregress \
                        ${SESS}/func_tmp_det.${ID}.${NUM}.nii.gz \
                        ${SESS}/anat_vent.nii.gz \
                        ${SESS}/PARAMS/vent_pc.${ID}.${NUM}.1D \
                        ${COMPCOR}
                fi

                if [ ! -f ${SESS}/PARAMS/wm_pc.${ID}.${NUM}.1D ]; then
                    epi-genregress \
                        ${SESS}/func_tmp_det.${ID}.${NUM}.nii.gz \
                        ${SESS}/anat_wm.nii.gz \
                        ${SESS}/PARAMS/wm_pc.${ID}.${NUM}.1D \
                        ${COMPCOR}
                fi

                # https://www.youtube.com/watch?v=oavMtUWDBTM
                CMD=`echo ${CMD} ${SESS}/PARAMS/wm_pc.${ID}.${NUM}.1D`
                CMD=`echo ${CMD} ${SESS}/PARAMS/vent_pc.${ID}.${NUM}.1D`
            fi

            ####################################################################
            # Finally, run the command
            ${CMD}

            # subtracts nuisances from inputs, retaining the mean
            3dcalc \
                -float \
                -a ${SESS}/func_tmp_det.${ID}.${NUM}.nii.gz \
                -b ${SESS}/func_noise.${ID}.${NUM}.nii.gz \
                -c ${SESS}/func_tmp_mean.${ID}.${NUM}.nii.gz \
                -expr 'a-b+c' \
                -prefix ${SESS}/func_filtered.${ID}.${NUM}.nii.gz

        fi
    done
done

echo '*** MODULE: volsmooth. Spatially smooths volume data. ******************'
export input=func_filtered
export mask=anat_EPI_mask
export fwhm=12.0
export mode=normal

DIR_SESS=`ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/`
for SESS in ${DIR_SESS}; do
    DIR_RUNS=`ls -d -- ${SESS}/RUN*`
    for RUN in ${DIR_RUNS}; do
        NUM=`basename ${RUN} | sed 's/[^0-9]//g'`

        # if an old smoothmask is left behind, obliterate
        if [ -f ${SESS}/anat_tmp_smoothmask.nii.gz ]; then
            rm ${SESS}/anat_tmp_smoothmask.nii.gz
        fi

        # resample input mask to match dimensions of first run
        3dresample \
            -prefix ${SESS}/anat_tmp_smoothmask.nii.gz \
            -master ${SESS}/${input}.${ID}.01.nii.gz \
            -rmode NN \
            -inset ${SESS}/${mask}.nii.gz

        # smooth to specified fwhm
        if [ ! -f ${SESS}/func_volsmooth.${ID}.${NUM}.nii.gz ]; then

            # use 3dBlurTofwhm
            if [ ${mode} == 'normal' ]; then
                # If already run filter, use noise model from it as blurmaster
                if [ -f ${SESS}/func_noise.${ID}.${NUM}.nii.gz ]; then
                    echo 'MSG: func_noise found. ensure that the filter module was run in the same space as volsmooth, or this command will fail and complain about grid spacing of the BLURMASTER!'
                    3dBlurToFWHM \
                        -quiet \
                        -prefix ${SESS}/func_volsmooth.${ID}.${NUM}.nii.gz \
                        -mask ${SESS}/anat_tmp_smoothmask.nii.gz \
                        -fwhm ${fwhm} \
                        -blurmaster ${SESS}/func_noise.${ID}.${NUM}.nii.gz \
                        -input ${SESS}/${input}.${ID}.${NUM}.nii.gz
                else
                    3dBlurToFWHM \
                        -quiet \
                        -prefix ${SESS}/func_volsmooth.${ID}.${NUM}.nii.gz \
                        -mask ${SESS}/anat_tmp_smoothmask.nii.gz \
                        -fwhm ${fwhm} \
                        -input ${SESS}/${input}.${ID}.${NUM}.nii.gz
                fi

            # use 3dBlurInMask
            elif [ ${mode} == 'multimask' ]; then
                3dBlurInMask \
                    -prefix ${SESS}/func_volsmooth.${ID}.${NUM}.nii.gz \
                    -Mmask ${SESS}/anat_tmp_smoothmask.nii.gz \
                    -fwhm ${fwhm} \
                    -quiet -float \
                    -input ${SESS}/${input}.${ID}.${NUM}.nii.gz
            fi
        rm ${SESS}/anat_tmp_smoothmask.nii.gz
        fi
    done
done

echo '*** MODULE: nonlinreg_epi2mni_fsl. Warps EPI data to MNI space. ********'
export input=func_volsmooth

DIR_SESS=$(ls -d -- ${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/*/)
for SESS in ${DIR_SESS}; do
    SESS=$(basename ${SESS})
    DIR="${DIR_DATA}/${DIR_EXPT}/${SUB}/${DATA_TYPE}/${SESS}"

    # create registration dummy for FSL
    if [ ! -f ${DIR}/anat_EPI_reg_target.nii.gz ]; then
        3dresample \
            -dxyz ${dims} ${dims} ${dims} \
            -prefix ${DIR}/anat_EPI_reg_target.nii.gz \
            -inset ${FSLDIR}/data/standard/MNI152_T1_2mm_brain.nii.gz
    fi

    DIR_RUNS=$(ls -d -- ${DIR}/RUN*)
    for RUN in ${DIR_RUNS}; do
        NUM=$(basename ${RUN} | sed 's/[^0-9]//g')

        # register runs with MNI
        if [ ! -f ${DIR}/func_MNI-nonlin.${ID}.${NUM}.nii.gz ]; then
            applywarp \
                --ref=${DIR}/anat_EPI_reg_target.nii.gz \
                --in=${DIR}/${input}.${ID}.${NUM}.nii.gz \
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

