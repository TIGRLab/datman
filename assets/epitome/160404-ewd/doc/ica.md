ica
---
Usage: ica <func_prefix> <mask_prefix>

+ func_prefix -- functional data prefix (eg., smooth in func_smooth).
+ anat_prefix -- mask data prefix (eg., epi_brain in anat_epi_brain).

Runs ICA on each input functional file of the type defined using the default MELODIC settings. This module could be easily tweaked to grant the user access to the dimensionality estimation settings, if need be. The output is the full MELODIC report in a `.ica` folder.

Prerequisites: init_*, motion_deskull.

Outputs: MELODIC.ica folders (does not directly affect pipeline, no func_whatever.nii.gzs are produced).

