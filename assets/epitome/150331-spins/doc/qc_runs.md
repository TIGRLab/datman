check_runs
----------
Usage: check_runs <path> <expt>

+ path -- full path to epitome data folder.
+ expt -- experiment name.

This prints out a CSV containing the NIFTI dimensions of each file contained in a RUN folder. This works across all modalities simultaneously, and records subject, image modality, session, and run number. This should give the user a broad overview of the input data, hopefully assisting in identifying corrupted files or aborted runs in the MRI.

Prerequisites: None.
