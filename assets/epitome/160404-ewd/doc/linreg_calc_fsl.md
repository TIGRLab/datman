linreg_calc_fsl
---------------
Usage: linreg_calc_fsl <data_quality> <cost> <reg_dof>

+ cost -- cost function minimized during registration (see FSL FLIRT).
+ reg_dof -- 6, 7, 9, or 12 degrees of freedom (see FSL FLIRT).
+ data_quality -- `low' for poor internal contrast, otherwise `high'.

Uses FSL's FLIRT to calculate linear registration between epi <--> T1 <--> MNI152, and generate an epi template registered to T1 \& T1 registered to epi (sessionwise). Specific options can be found in the command-line interface's help function.

Prerequisites: init_*, motion_deskull.

Outputs: Registration .mat files, registered anatomicals (including mean EPI).

