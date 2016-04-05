linreg_calc_afni
----------------
Usage: linreg_calc_afni <data_quality> <cost> <reg_dof>

+ data_quality -- `low' for poor internal contrast, otherwise `high'.
+ cost -- cost function minimized during registration.
+ reg_dof -- `big_move' or `giant_move' (from align_epi_anat.py).

Uses AFNI's align_epi_anat.py to calculate linear registration between epi <--> T1 <--> MNI152, and generate an epi template registered to T1 \& T1 registered to epi (sessionwise). Specific options can be found in the command-line interface's help function.

Prerequisites: init_*, motion_deskull.

Outputs: Registration .1D files, resampled anatomicals (including mean EPI).

