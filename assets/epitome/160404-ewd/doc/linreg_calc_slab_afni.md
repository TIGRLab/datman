linreg_calc_afni
----------------
Usage: linreg_calc_afni <cost> <reg_dof> <data_quality>

+ cost -- cost function minimized during registration.
+ reg_dof -- `big_move' or `giant_move' (from align_epi_anat.py).
+ data_quality -- `low' for poor internal contrast, otherwise `high'.

Uses AFNI's align_epi_anat.py to calculate linear registration between epi <--> WHEPI <-->T1 <--> MNI152, and generate an epi template registered to T1 \& T1 registered to epi (sessionwise). This is a specialty module for experiments where you have acquired a very thin slab of fMRI data and have a companion whole-head EPI acquisition with similar image characteristics. This program will first solve the easy problem of registering the slab with the whole head EPI before attempting to compute the EPI to T1 registration. Fir best results, the whole head EPI should have the exact same origin as the slab, voxel dimensions, and TE, with simply more slices acquired (and therefore a correspondingly longer TR). Specific options can be found in the command-line interface's help function.

Each session should have its own whole head EPI, and should be placed into its own MODE folder named `WHEPI` (and corresponding `SESSXX/RUN01` folder). This script will match the selected EPI mode data to the `WHEPI` mode by session automatically.

This outputs of this will be identical in utility to `linreg_calc_afni`.

Prerequisites: init_epi, motion_deskull.

Outputs: Registration .1D files, resampled anatomicals (including mean EPI).

