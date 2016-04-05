surfsmooth
----------
Usage: surfsmooth <func_prefix> <FWHM>

+ func_prefix -- functional data prefix (eg.,smooth in func_smooth). 
+ FWHM -- full-width half-maximum of the gaussian kernel convolved with the surface data.

This spatially-smooths cortical data along the surface mesh, estimated by Freesurfer.

Prerequisites: init_*, motion_deskull, linreg_calc_afni, linreg_epi2T1_afni, vol2surf.

Outputs: Surface files (left and right seperately).
