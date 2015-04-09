check_spectra
-------------
Usage: check_spectra <path> <expt> <mode> <uid>

+ path -- full path to epitome data folder.
+ expt -- experiment name.
+ mode -- image modality (eg., TASK, REST).
+ uid -- unique identifier for run of epitome.

This gives an overview of the frequency content of the MRI data in multiple ways for each subject. First, it plots the log-log spectra of the regressors used for time-series filtering, as typically done in resting-state experiments. It also compares the mean raw data with the mean filtered output, and mean noise model, to show whether the modeled noise is qualitatively different from the input raw data. Finally, it compares the spectra of the mean time series with the mean of all computed spectra, which should be equivalent.

Prerequisites: linreg_FS2epi_afni/fsl, gen_regressors.