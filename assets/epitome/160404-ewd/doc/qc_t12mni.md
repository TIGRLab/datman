check_t12mni
------------
Usage: check_t12mni <path> <expt> <mode>

+ path -- full path to epitome data folder.
+ expt -- experiment name.
+ mode -- image modality (eg., TASK, REST).

Prints out a PDF showing the quality of the linear registration between the subject-specific anatomical data and the group-level MNI brain. On the top row, the T1 image is translucent and overlaid on the MNI brain in red. On the bottom row, the MNI brain is translucent and is overlaid on the T1 brain in red.

Prerequisites: linreg_calc_afni/fsl.
