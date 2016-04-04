surf2vol
--------
Usage: surf2vol <func_prefix> <target_prefix>

+ func_prefix -- functional data prefix (eg.,smooth in func_smooth). 
+ target_prefix -- target data prefix (eg.,smooth in func_smooth). \

This projects surface data back into a functional volume with the same properties as <target_prefix>.

Prerequisites: init_*, motion_deskull, linreg_calc_afni, linreg_epi2T1_afni, vol2surf.

Outputs: ctx
