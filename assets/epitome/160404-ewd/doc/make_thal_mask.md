make_thal_mask
--------------
Usage: make_thal_mask

Uses the freesurfer segmentation to produce a thalamus mask that only includes voxels also within the whole-head EPI brain mask. Outputs `anat_THAL_mask.nii.gz`

Prerequisites: init_*, linreg_calc_afni/fsl linreg_fs2epi_afni/fsl.