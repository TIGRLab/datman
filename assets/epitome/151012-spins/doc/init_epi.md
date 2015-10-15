init_epi
--------
Usage: init_epi <data_quality> <del_tr> <t_pattern> <normalization> <masking> <mask_method>

+ data_quality -- 'low' for poor internal contrast, otherwise 'high'.
+ del_tr -- number of TRs to remove from the beginning of the run.
+ despike -- turns despiking on and off.
+ t_pattern -- optional slice-timing at acquisition (from AFNI's 3dTshift).
+ normalization -- voxel wise time series normalization. One of 'zscore', 'pct', 'demean'.
+ masking -- EPI brain masking tolerance. One of 'loosest', 'loose', 'normal', or 'tight'.
+ mask_method -- FSL == 'bet', AFNI == '3dAutomask'.

Works from the raw data in each RUN folder. It performs general pre-processing for all fMRI data:

+ Orients data to RAI
+ Deletes initial time points (optionally)
+ Removes data outliers
+ Slice time correction
+ Deobliques \& motion corrects data
+ Creates session mean deskulled epis and whole-brain masks
+ Scales and optionally normalizes each time series
+ Calculates various statistics + time series

Time series normalization can be accomplished in one of two ways: percent signal change, and scaling. For percent signal change, the data is normalized by the mean of each time series to mean = 100. A deviation of 1 from this mean value indicates 1% signal change in the data. This is helpful for analyzing only relative fluctuations in the signal and is best at removing inter-session/subject/run variability, although it can also introduce rare artifacts in small localized regions of the images and may not play well with multivariate techniques such as partial least squares without accounting for these artifacts. Alternatively, one can scale the data, which applies single scaling factor to all voxels such that the global mean of the entire run = 1000. This will help normalize baseline shifts across sessions, runs, and participants. Your selection here might be motivated by personal preference, or in rarer cases, analytic requirements. When in doubt, it is safe to select 'off', as scaling can be done later by hand, or 'scale' if one is doing a simple GLM-style analysis. 'pct' should be used by those with a good reason.

Masking options are provided to improve masking performance across various acquisition types, but it is very hard to devise a simple one-size fits all solution for this option. Therefore the QC outputs will be very important for ensuring good masking, and these options may need to be tweaked on a site-by-site basis. Luckily, many analysis methods do not rely heavily on mask accuracy. In cases that do, such as partial least squares / ICA / PCA analysis, close attention should be paid to the output of this step. Hopefully the 'loose', 'normal', and 'tight' nomenclature are self-explanatory. Generally, it is best to start with normal, and adjust if required.

Prerequisites: None.

Outputs: tshift (before deobliquing), ob (before motion-correction), scaled (final).
