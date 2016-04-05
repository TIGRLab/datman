reg_calc_hcpfsl
---------------
Usage: reg_calc_hcpfsl <cost> <reg_dof> <data_quality>

+ cost -- cost function minimized during registration (see FSL FLIRT).
+ reg_dof -- 6, 7, 9, or 12 degrees of freedom (see FSL FLIRT).
+ data_quality -- `low' for poor internal contrast, otherwise `high'.

Uses FSL's FLIRT to calculate linear registration between epi <--> T1. It also copies the registration of the T1 to MNI space (that came from the HCP_DATA directory) from the T1 directory down to this session. It generate an epi template registered to T1 \& T1 registered to epi (sessionwise). Specific options can be found in the command-line interface's help function.

Prerequisites: init_epi. hcpexport

Outputs: Registration .mat files, registered anatomicals (including mean EPI).
