#!/bin/bash

## Pre-processing for fMRI data:
#  1) Linear registration of EPI to Subject T1
#  2) Linear registration of Subject T1 to MNI
#  3) Nonlinear registration of linear-registered T1 to MNI
#  4) Apply warp to EPI mask

for SUB in ${SUBJECTS}; do
    DIR=`echo ${DIR_DATA}/${DIR_EXPT}/${SUB}/`
    cd ${DIR}/t1/
    SESS=`ls`
    cd /tmp
    for S in ${SESS}; do

        # normalize T1 image intensity
        if [ ! -f ${DIR}/t1/${S}/anat_T1_brain.nii.gz ]; then
        3dWarp -prefix ${DIR}/t1/${S}/anat_T1_tmp_deoblique.nii.gz \
               -quintic -deoblique \
                ${DIR}/t1/${S}/*.nii*

        3dUniformize -prefix ${DIR}/t1/${S}/anat_T1_tmp_uniformize.nii.gz \
                     -anat ${DIR}/t1/${S}/anat_T1_tmp_deoblique.nii.gz

        # remore T1 skull
        3dSkullStrip -prefix ${DIR}/t1/${S}/anat_T1_brain.nii.gz \
                     -input ${DIR}/t1/${S}/anat_T1_tmp_uniformize.nii.gz \
                     -niter 400 -ld 40 -push_to_edge

        rm p*.1D    # clean up this garbage (why does this happen?)
        rm vtou*.1D #
        fi

        # linear warp EPI --> T1
        if [ ! -f ${DIR}/t1/${S}/reg_EPI_to_T1.nii.gz ]; then
        3dCopy ${DIR}/task/${S}/anat_EPI_brain.nii.gz anat_EPI_brain
        3dCopy ${DIR}/t1/${S}/anat_T1_brain.nii.gz anat_T1_brain

        align_epi_anat.py -anat anat_T1_brain+orig \
                          -epi anat_EPI_brain+orig \
                          -epi_base 0 -epi2anat -suffix EPI_to_T1 \
                          -anat_has_skull no -epi_strip None -volreg off -tshift off -deoblique off \
                          -giant_move \
                          -cost lpc

        mv anat_EPI_brainEPI_to_T1_mat.aff12.1D ${DIR}/task/${S}/mat_EPI_to_T1.aff12.1D
        mv anat_T1_brainEPI_to_T1_mat.aff12.1D ${DIR}/t1/${S}/mat_T1_to_EPI.aff12.1D
        3dCopy anat_EPI_brainEPI_to_T1+orig ${DIR}/t1/${S}/reg_EPI_to_T1.nii.gz
        rm anat_*
        rm __tt*
        fi

        # linear warp T1 --> ICBM452
        if [ ! -f ${DIR}/t1/${S}/anat_T1_linreg.nii.gz ]; then
        3dAllineate -prefix ${DIR}/t1/${S}/anat_T1_linreg.nii.gz \
                    -base ${AFNI_DIR}/TT_icbm452+tlrc \
                    -source ${DIR}/t1/${S}/anat_T1_brain.nii.gz \
                    -source_automask \
                    -final wsinc5 \
                    -float \
                    -twopass -cost lpa \
                    -1Dmatrix_save ${DIR}/t1/${S}/mat_T1_to_template_lin.aff12.1D \
                    -autoweight -fineblur 3 -cmass
        fi

        # nonlinear warp T1 --> ICBM452
        # -useweight off improves strange edge behavior
        if [ ! -f ${DIR}/t1/${S}/anat_T1_nlinreg_WARP.nii.gz ]; then
        3dQwarp -prefix ${DIR}/t1/${S}/anat_T1_nlinreg.nii.gz \
                -duplo -blur 0 -3 -pear -iwarp \
                -base ${AFNI_DIR}/TT_icbm452+tlrc \
                -source ${DIR}/t1/${S}/anat_T1_linreg.nii.gz
        fi

        RUN=`ls -- ${DIR}/task/${S}/func_brain* | wc -l`
        for ((i=1;i<=RUN;i++)); do
            # Warp EPIs to standard space: concatenates EPI -> T1 -> Template (lin + nonlin) # mat_T1_to_EPI needs to be fixed
            nwarpCMD=`echo ${DIR}/t1/${S}/anat_T1_nlinreg_WARP.nii.gz ${DIR}/t1/${S}/mat_T1_to_template_lin.aff12.1D`
            if [ ! -f ${DIR}/task/${S}/func_norm${i}.nii.gz ]; then
            3dNwarpApply -prefix ${DIR}/task/${S}/func_norm${i}.nii.gz \
                         -source ${DIR}/task/${S}/func_brain${i}.nii.gz \
                         -affter ${DIR}/t1/${S}/mat_T1_to_EPI.aff12.1D \
                         -nwarp ${nwarpCMD}
            fi
        done

        # Warp EPI mask to Template
        nwarpCMD=`echo ${DIR}/t1/${S}/anat_T1_nlinreg_WARP.nii.gz ${DIR}/t1/${S}/mat_T1_to_template_lin.aff12.1D ${DIR}/task/${S}/task/mat_EPI_to_T1.aff12.1D`
        if [ ! -f ${DIR}/task/${S}/anat_EPI_mask_norm.nii.gz ]; then
            3dNwarpApply -prefix ${DIR}/task/${S}/anat_EPI_mask_norm.nii.gz \
                         -source ${DIR}/task/${S}/anat_EPI_mask.nii.gz \
                         -nwarp ${nwarpCMD}
        fi
        #if [ ! -f ${DIR}/task/${S}/anat_EPI_mask_norm_reg.nii.gz ]; then
        TARGET=${SUBJECTS[0]}
        if [ ${TARGET} = ${SUB} ]; then
            echo 'target set'
            TARGET_S=${S}
        fi
        MASTER=`echo ${DIR_DATA}/${DIR_EXPT}/${TARGET}/task/${TARGET_S}/anat_EPI_mask_norm.nii.gz`
        echo ${MASTER}
        3dresample -prefix ${DIR}/task/${S}/anat_EPI_mask_norm_reg.nii.gz \
                   -rmode NN \
                   -inset ${DIR}/task/${S}/anat_EPI_mask_norm.nii.gz \
                   -master ${MASTER}
        #fi
    done
done