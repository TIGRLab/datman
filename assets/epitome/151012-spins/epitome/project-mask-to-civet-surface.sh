#!/bin/bash

## THIS WORKS IN MNI SPACE!! ##

FIN_DIR=`pwd`

DIR_CIV='/projects/jdv/data/ica-surface/civet/D24S005_raw_struct'
MASK='/projects/jdv/data/ica-surface/tmp/DMN_POS_IC0000.nii.gz'
DIR='/projects/jdv/data/ica-surface/tmp/'


echo 'NB: This script works on the MNI space data only!'
echo ''

# copy Civet TAL T1 to DIR, convert to NIFTI
cp ${DIR_CIV}/final/*_raw_struct_t1_tal.mnc ${DIR}/anat_T1_brain_MNI.mnc
mnc2nii ${DIR}/anat_T1_MNI.mnc ${DIR}/anat_T1_brain_MNI.nii

# copy input mask into DIR as mask.nii.gz
3dcopy ${MASK} ${DIR}/mask.nii.gz

# convert RSL CIVET .obj files to freesurfer binaries
if [ ! -f ${DIR}/surf_wm_L.asc ]; then
    ConvertSurface \
        -i_mni ${DIR_CIV}/surfaces/*white_surface_rsl_left*81920.obj \
        -o_fs ${DIR}/surf_wm_L.asc \
        -sv ${DIR}/anat_T1_brain_MNI.nii
fi

if [ ! -f ${DIR}/surf_wm_R.asc ]; then
    ConvertSurface \
        -i_mni ${DIR_CIV}/surfaces/*white_surface_rsl_right*81920.obj \
        -o_fs ${DIR}/surf_wm_R.asc \
        -sv ${DIR}/anat_T1_brain_MNI.nii
fi

if [ ! -f ${DIR}/proc/surf_mid_L.asc ]; then
    ConvertSurface \
        -i_mni ${DIR_CIV}/surfaces/*mid_surface_rsl_left*81920.obj \
        -o_fs ${DIR}/surf_mid_L.asc \
        -sv ${DIR}/anat_T1_brain_MNI.nii
fi

if [ ! -f ${DIR}/proc/surf_mid_R.asc ]; then
    ConvertSurface \
        -i_mni ${DIR_CIV}/surfaces/*mid_surface_rsl_right*81920.obj \
        -o_fs ${DIR}/surf_mid_R.asc \
        -sv ${DIR}/anat_T1_brain_MNI.nii
fi

if [ ! -f ${DIR}/proc/surf_gm_L.asc ]; then
    ConvertSurface \
        -i_mni ${DIR_CIV}/surfaces/*gray_surface_rsl_left*81920.obj \
        -o_fs ${DIR}/surf_gm_L.asc \
        -sv ${DIR}/anat_T1_brain_MNI.nii
fi

if [ ! -f ${DIR}/proc/surf_gm_R.asc ]; then
    ConvertSurface \
        -i_mni ${DIR_CIV}/surfaces/*gray_surface_rsl_right*81920.obj \
        -o_fs ${DIR}/surf_gm_R.asc \
        -sv ${DIR}/anat_T1_brain_MNI.nii
fi

# this is required for quickspec to work properly, because it likes
# relative ('reli') paths. don't hate.
cd ${DIR}

# make a 'spec' file for AFNI
quickspec \
  -tn FS surf_wm_L.asc \
  -tn FS surf_wm_R.asc \
  -tn FS surf_gm_L.asc \
  -tn FS surf_gm_R.asc \
  -tn FS surf_mid_L.asc \
  -tn FS surf_mid_R.asc

# project mask onto 'dset' surface
if [ ! -f ${DIR}/atlas_civ.L.1D ]; then
    3dVol2Surf \
      -spec quick.spec \
      -surf_A surf_mid_L.asc \
      -sv anat_T1_brain_MNI.nii \
      -grid_parent mask.nii.gz \
      -map_func mask \
      -f_steps 2 \
      -f_index nodes \
      -out_1D atlas_civ.L.1D
fi

if [ ! -f ${DIR}/atlas_civ.R.1D ]; then
    3dVol2Surf \
      -spec quick.spec \
      -surf_A surf_mid_R.asc \
      -sv anat_T1_brain_MNI.nii \
      -grid_parent mask.nii.gz \
      -map_func mask \
      -f_steps 2 \
      -f_index nodes \
      -out_1D atlas_civ.R.1D 
fi
