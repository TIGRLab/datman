
check_mc_trs
------------
Usage: check_mc_trs <path> <expt> <mode>

+ path -- full path to epitome data folder.
+ expt -- experiment name.
+ mode -- image modality (eg., TASK, REST).

Prints TRs 6-10 from the first run of each session. The default motion-correction TR 8 is marked in red. This will allow the user to identify whether the motion-correction TR is somehow corrupted for any given subject, which can be manually changed and re-run.

Prerequisites: init_epi.