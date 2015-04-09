volsmooth
---------
Usage: volsmooth <func_prefix> <mask_prefix> <FWHM> <mode>

+ func_prefix -- functional data prefix (eg., smooth in func_smooth).
+ mask_prefix -- mask data prefix (eg., epi_mask in anat_epi_mask).
+ FWHM -- FWHM in mm of gaussian to blur towards (all methods use iterative blurring).
+ mode -- 'normal' or 'multimask'.

Re-samples a mask containing one or more labels to the functional data. In 'normal' mode, blurs towards target FWHM iteratively using a 'noise' dataset with no spatial struture as the guide. The objective here is to standardize the spatial smoothness of the noise across all datasets. This is particularly useful in multi-scanner experiments. In 'multimask' mode, blurs iteratively within unique mask values. This is not as clever a mode, in that it does not explicitly work on a noise model of the data, but can be useful in the subcortical regions when you do not want to blur into non-brain regions or between adjacent nuclei. All zero values in the mask are zeroed out in the output. The output of this can be combined with the outputs of surfsmooth & surf2vol using combine_volumes.

Prerequisites: init_epi, (filtered preferred, not required, for normal mode).

Outputs: volsmooth

