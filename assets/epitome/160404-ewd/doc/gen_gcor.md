gen_gcor
--------
Usage: gen_gcor <func_prefix>

+ func_prefix -- functional data prefix (eg.,smooth in func_smooth).

Calls an AFNI script to calculate the global correlation for each concatenated set of runs (across all sessions). Useful for resting state functional connectivity experiments.

Prerequisites: init_*, motion_deskull.

Outputs: .gcor files in /PARAMS
