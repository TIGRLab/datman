#!/bin/bash
set -e

# Requirements for this script
#  installed versions of: FSL (version 5.0.6), FreeSurfer (version 5.3.0-HCP) , gradunwarp (HCP version 1.0.2)
#  environment: use SetUpHCPPipeline.sh  (or individually set FSLDIR, FREESURFER_HOME, HCPPIPEDIR, PATH - for gradient_unwarp.py)


# --------------------------------------------------------------------------------
#  Load Function Libraries
# --------------------------------------------------------------------------------
#EnvironmentScript="${HOME}/Documents/lerch/spatnav_rest/scripts/SetUpHCPPipeline_mac.sh" #Pipeline environment script

source $HCPPIPEDIR/global/scripts/log.shlib  # Logging related functions
source $HCPPIPEDIR/global/scripts/opts.shlib # Command line option functions

################################################ SUPPORT FUNCTIONS ##################################################

# --------------------------------------------------------------------------------
#  Usage Description Function
# --------------------------------------------------------------------------------

show_usage() {
    echo "Usage information To Be Written"
    exit 1
}

# --------------------------------------------------------------------------------
#   Establish tool name for logging
# --------------------------------------------------------------------------------
log_SetToolName "fMRI2hcp.sh"

################################################## OPTION PARSING #####################################################

opts_ShowVersionIfRequested $@

if opts_CheckForHelpRequest $@; then
    show_usage
fi

log_Msg "Parsing Command Line Options"

# parse arguments
InputfMRI=`opts_GetOpt1 "--InputfMRI" $@`  # "$2"
HCPFolder=`opts_GetOpt1 "--HCPpath" $@`  # "$2"
Subject=`opts_GetOpt1 "--subject" $@`  # "$2"
NameOffMRI=`opts_GetOpt1 "--OutputBasename" $@`  # "$2"
SmoothingFWHM=`opts_GetOpt1 "--smoothingFWHM" $@`  # "${3}"


if [ "${RegName}" = "" ]; then
    RegName="FS"
fi

RUN=`opts_GetOpt1 "--printcom" $@`  # use ="echo" for just printing everything and not running the commands (default is to run)


log_Msg "InputfMRI: ${InputfMRI}"
log_Msg "HCPFolder: ${HCPFolder}"
log_Msg "hcpSubject: ${hcpSubject}"
log_Msg "NameOffMRI: ${NameOffMRI}"
log_Msg "SmoothingFWHM: ${SmoothingFWHM}"


# Setup PATHS
Subject=${Subject}
PipelineScripts=${HCPPIPEDIR_fMRISurf}

#Templates and settings
AtlasSpaceFolder="${HCPFolder}/${Subject}/MNINonLinear"
DownSampleFolder="$AtlasSpaceFolder"/"fsaverage_LR32k"
FinalfMRIResolution="2"
GrayordinatesResolution="2"
LowResMesh="32"
NativeFolder="Native"
RegName="FS"
ResultsFolder="${AtlasSpaceFolder}/Results/${NameOffMRI}/"
ROIFolder="$AtlasSpaceFolder"/ROIs


###### from end of volume mapping pipeline

log_Msg "mkdir -p ${ResultsFolder}"
mkdir -p ${ResultsFolder}
cp ${InputfMRI} ${ResultsFolder}/${NameOffMRI}.nii.gz
fslmaths ${ResultsFolder}/${NameOffMRI}.nii.gz -Tmean ${ResultsFolder}/${NameOffMRI}_SBRef.nii.gz


#Make fMRI Ribbon
#Noisy Voxel Outlier Exclusion
#Ribbon-based Volume to Surface mapping and resampling to standard surface
if [ ! -f ${ResultsFolder}/${NameOffMRI}.R.atlasroi.32k_fs_LR.func.gii ]; then
  log_Msg "Make fMRI Ribbon"
  log_Msg "mkdir -p ${ResultsFolder}/RibbonVolumeToSurfaceMapping"
  mkdir -p "$ResultsFolder"/RibbonVolumeToSurfaceMapping
  "$PipelineScripts"/RibbonVolumeToSurfaceMapping.sh \
  	"$ResultsFolder"/RibbonVolumeToSurfaceMapping \
  	"$ResultsFolder"/"$NameOffMRI" \
  	"$Subject" \
  	"$DownSampleFolder" \
  	"$LowResMesh" \
  	"$AtlasSpaceFolder"/"$NativeFolder" \
  	"${RegName}"
fi

#Surface Smoothing
if [ ! -f ${ResultsFolder}/${NameOffMRI}_s${SmoothingFWHM}.atlasroi.R.32k_fs_LR.func.gii ]; then
  log_Msg "Surface Smoothing"
  "$HCPPIPEDIR_fMRISurf"/SurfaceSmoothing.sh \
  	"$ResultsFolder"/"$NameOffMRI" \
  	"$Subject" \
  	"$DownSampleFolder" \
  	"$LowResMesh" \
  	"$SmoothingFWHM"
fi

#Subcortical Processing
if [ ! -f ${ResultsFolder}/${NameOffMRI}_AtlasSubcortical_s${SmoothingFWHM}.nii.gz ]; then
log_Msg "Subcortical Processing"
"$HCPPIPEDIR_fMRISurf"/SubcorticalProcessing.sh \
	"$AtlasSpaceFolder" \
	"$ROIFolder" \
	"$FinalfMRIResolution" \
	"$ResultsFolder" \
	"$NameOffMRI" \
	"$SmoothingFWHM" \
	"$GrayordinatesResolution"
fi

#Generation of Dense Timeseries
if [ ! -f ${ResultsFolder}/${NameOffMRI}_Atlas_s${SmoothingFWHM}.dtseries.nii ]; then
  log_Msg "Generation of Dense Timeseries"
  "$PipelineScripts"/CreateDenseTimeseries.sh \
  	"$DownSampleFolder" \
  	"$Subject" \
  	"$LowResMesh" \
  	"$ResultsFolder"/"$NameOffMRI" \
  	"$SmoothingFWHM" \
  	"$ROIFolder" \
  	"$ResultsFolder"/"${NameOffMRI}_Atlas_s${SmoothingFWHM}" \
  	"$GrayordinatesResolution"
fi


# if [ ! -f ${ResultsFolder}/${NameOffMRI}_Atlas_s${SmoothingFWHM}_grad.dscalar.nii ]; then
#   log_Msg "Calculating Correlation Gradient Map"
#   wb_command -cifti-correlation-gradient \
#     ${ResultsFolder}/${NameOffMRI}_Atlas_s${SmoothingFWHM}.dtseries.nii \
#     ${ResultsFolder}/${NameOffMRI}_Atlas_s${SmoothingFWHM}_grad.dscalar.nii \
#     -left-surface "$DownSampleFolder"/"$Subject".L.midthickness."$LowResMesh"k_fs_LR.surf.gii \
#     -right-surface "$DownSampleFolder"/"$Subject".R.midthickness."$LowResMesh"k_fs_LR.surf.gii \
#     -mem-limit 2
# fi
#
# if [ ! -f ${ResultsFolder}/${NameOffMRI}_Atlas_s${SmoothingFWHM}_Z.dconn.nii ]; then
#   log_Msg "Calculating Dense Connectivity Map"
#   wb_command -cifti-correlation \
#     ${ResultsFolder}/${NameOffMRI}_Atlas_s${SmoothingFWHM}.dtseries.nii \
#     ${ResultsFolder}/${NameOffMRI}_Atlas_s${SmoothingFWHM}_Z.dconn.nii \
#     -fisher-z -mem-limit 2
# fi

# # Dilation step for cortical surface glm - dunno if this is really needed..but it's in the hcp pipeline
# log_Msg "Cortical Surface Dilation"
# for Hemisphere in L R ; do
#   #Prepare for film_gls
#   ${CARET7DIR}/wb_command -metric-dilate "$ResultsFolder"/"$NameOffMRI"_s"$SmoothingFWHM".atlasroi."$Hemisphere"."$LowResMesh"k_fs_LR.func.gii "$DownSampleFolder"/"$Subject"."$Hemisphere".midthickness."$LowResMesh"k_fs_LR.surf.gii 50 "$ResultsFolder"/"$NameOffMRI"_s"$SmoothingFWHM".atlasroi_dil."$Hemisphere"."$LowResMesh"k_fs_LR.func.gii -nearest
# done

log_Msg "Completed"
