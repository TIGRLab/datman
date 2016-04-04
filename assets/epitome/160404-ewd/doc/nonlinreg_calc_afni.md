nonlinreg_calc_afni
-------------------
Usage: nonlinreg_calc_afni

Computes a nonlinear warp from linear-registered individual T1 to MNI space. This can be concatenated onto the end of a set of linear warps to push epi data into a more homogeneous space than by simply nonlinearly-warping the data, but beware the findings one can obtain by forcing a square peg into a round hole! Requires these linear registrations to be completed first.

Prerequisites: init_*, motion_deskull, linreg_calc_afni.