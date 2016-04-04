slice_time_correct
------------------

Usage: scale <func_prefix> <t_pattern>

+ func_prefix -- functional data prefix (eg., smooth in func_smooth).
+ t_pattern -- optional slice-timing at acquisition (from AFNI's 3dTshift).

This performs slice time correction using the supplied slice timing pattern.

Prerequisites: init_*.

Output: tshift.