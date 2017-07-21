#!/bin/bash

if [ ! $# -eq 4 ]
then
  echo
  echo "Runs the full HCP freesurfer pipeline (Pre, Freesurfer, and Post). To"
  echo "run this script, you must first run HCP-Pipeline's SetUpHCPPipeline.sh"
  echo "script, as customized for your site."
  echo
  echo "Usage:"
  echo "    `basename $0` <base_dir> <subject_id> <T1> <T2>"
  echo
  echo "Arguments:"
  echo "    <base_dir>      The absolute path to the directory where all outputs"
  echo "                    will be made."
  echo "    <subject_id>    The subject id. This will be the name of the output"
  echo "                    folder within base_dir"
  echo "    <T1>            The full path to this subject's T1 nifti file"
  echo "    <T2>            The full path to this subject's T2 nifti file"
  echo
  exit 0
fi

base_dir=$1
subject_id=$2
t1=$3
t2=$4

subject_data=${base_dir}/${subject_id}

################################################################################
# Pre FreeSurfer pipeline
pre_fs=${HCPPIPEDIR}/PreFreeSurfer

${pre_fs}/PreFreeSurferPipeline.sh --path=${base_dir} \
    --subject=${subject_id} \
    --t1=${t1} \
    --t2=${t2} \
    --t1template=${HCPPIPEDIR_Templates}/MNI152_T1_0.8mm.nii.gz \
    --t1templatebrain=${HCPPIPEDIR_Templates}/MNI152_T1_0.8mm_brain.nii.gz \
    --t1template2mm=${HCPPIPEDIR_Templates}/MNI152_T1_2mm.nii.gz \
    --t2template=${HCPPIPEDIR_Templates}/MNI152_T2_0.8mm.nii.gz \
    --t2templatebrain=${HCPPIPEDIR_Templates}/MNI152_T2_0.8mm_brain.nii.gz \
    --templatemask=${HCPPIPEDIR_Templates}/MNI152_T1_0.8mm_brain_mask.nii.gz \
    --template2mmmask=${HCPPIPEDIR_Templates}/MNI152_T1_2mm_brain_mask_dil.nii.gz

################################################################################
# FreeSurfer pipeline
fs_pipeline=${HCPPIPEDIR}/FreeSurfer

t1w=${subject_data}/T1w/T1w_acpc_dc_restore.nii.gz
t2w=${subject_data}/T1w/T2w_acpc_dc_restore.nii.gz
t1w_brain=${subject_data}/T1w/T1w_acpc_dc_restore_brain.nii.gz

# Post freesurfer expects that fs outputs are nested inside the subject's T1w folder :(
${fs_pipeline}/FreeSurferPipeline.sh --subject=${subject_id} \
    --subjectDIR=${subject_data}/T1w \
    --t1=${t1w} \
    --t2=${t2w} \
    --t1brain=${t1w_brain}

################################################################################
# Post FreeSurfer pipeline
post_fs=${HCPPIPEDIR}/PostFreeSurfer

${post_fs}/PostFreeSurferPipeline.sh \
    --path=${base_dir} \
    --subject=${subject_id} \
    --surfatlasdir=${HCPPIPEDIR_Templates}/standard_mesh_atlases \
    --grayordinatesdir=${HCPPIPEDIR_Templates}/91282_Greyordinates \
    --grayordinatesres="2" \
    --hiresmesh="164" \
    --lowresmesh="32" \
    --subcortgraylabels=${HCPPIPEDIR_Config}/FreeSurferSubcorticalLabelTableLut.txt \
    --freesurferlabels=${HCPPIPEDIR_Config}/FreeSurferAllLut.txt \
    --refmyelinmaps=${HCPPIPEDIR_Templates}/standard_mesh_atlases/Conte69.MyelinMap_BC.164k_fs_LR.dscalar.nii \
    --regname="FS"
