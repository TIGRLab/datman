nonlinreg_epi2mni_afni
----------------------
Usage: nonlinreg_epi2mni_afni <func_prefix> <voxel_dims>

+ func_prefix -- functional data prefix (eg., smooth in func_smooth). 
+ voxel_dims -- target voxel dimensions (isotropic).

Prepares data for analysis in MNI standard-space, including a nonlinear warp. This also performs a linear registration, so the input data should be in native space.

Prerequisites: init_*, motion_deskull, linreg_calc_afni, nonlinreg_calc_afni

Outputs: MNI-nonlin
