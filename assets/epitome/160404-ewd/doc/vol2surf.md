vol2surf
--------
Usage: vol2surf <func_prefix>

+ func_prefix -- functional data prefix (eg.,smooth in func_smooth).

Projects functional data from volume space to a Freesurfer generated cortical mesh. This must be run on epi data in single-subject T1 space, otherwise we won't end up projecting the cortex to the surface model, but rather some random selection of brain and non-brain matter!

Prerequisites: init_*, motion_deskull, linreg_calc_afni, linreg_epi2T1_afni.

Outputs: Surface files (left and right seperately).

