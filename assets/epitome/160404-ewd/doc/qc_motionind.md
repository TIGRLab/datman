check_motionind
---------------
Usage: check_motionind <path> <expt> <mode> <uid>

+ path -- full path to epitome data folder.
+ expt -- experiment name.
+ mode -- image modality (eg., TASK, REST).
+ uid -- unique identifier for run of epitome.

This prints the estimated framewise displacement and DVARS measurement for all subjects and runs in an experiment to one grid, ranking subjects by the sum of their framewise displacement (top left shows least motion, bottom right shows most motion). Vertical lines denote runs, and the horizontal line denotes a respectable threshold of 0.5 mm/TR for the framewise displacement plot, and 10\% signal change for the DVARS plot. This can be used to hopefully facilitate subject-wise or run-wise rejection due to excessive head motion.

Prerequisites: init_epi.
