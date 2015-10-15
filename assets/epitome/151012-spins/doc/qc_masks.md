check_masks
-----------
Usage: check_masks <path> <expt> <mode>

+ path -- full path to epitome data folder.
+ expt -- experiment name.
+ mode -- image modality (eg., TASK, REST).

Prints out a PDF showing the Freesurfer-derived masks overlain on each subject's T1 brain -- these masks are those used for regressor estimation. White matter is labeled in dark blue, gray matter is labeled in light blue, draining vessels are labeled in light blue?, and ventricles are labeled in ???.  
Prerequisites: linreg_FS2epi_afni/fsl.
