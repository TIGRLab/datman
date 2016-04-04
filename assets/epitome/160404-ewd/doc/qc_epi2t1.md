check_epi2t1
------------
Usage: check_epi2t1 <path> <expt> <mode>

+ path -- full path to epitome data folder.
+ expt -- experiment name.
+ mode -- image modality (eg., TASK, REST).

Prints out a PDF showing the quality of the linear registration between the functional and anatomical data for all subjects. On the top row, the epi image is translucent and overlaid on the anatomical in red. On the bottom row, an edge-detected version of the anatomical is overlain on the epi image in blues.

Prerequisites: linreg_calc_afni/fsl.
