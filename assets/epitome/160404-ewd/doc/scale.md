scale
-----
Usage: scale <func_prefix> <normalize>

+ func_prefix -- functional data prefix (eg., smooth in func_smooth).
+ normalization -- voxel wise time series normalization. One of 'zscore', 'pct', 'demean'.

Time series normalization can be accomplished in one of two ways: percent signal change, and scaling. For percent signal change, the data is normalized by the mean of each time series to mean = 100. A deviation of 1 from this mean value indicates 1% signal change in the data. This is helpful for analyzing only relative fluctuations in the signal and is best at removing inter-session/subject/run variability, although it can also introduce rare artifacts in small localized regions of the images and may not play well with multivariate techniques such as partial least squares without accounting for these artifacts. Alternatively, one can scale the data, which applies single scaling factor to all voxels such that the global mean of the entire run = 1000. This will help normalize baseline shifts across sessions, runs, and participants. Your selection here might be motivated by personal preference, or in rarer cases, analytic requirements. When in doubt, it is safe to select 'off', as scaling can be done later by hand, or 'scale' if one is doing a simple GLM-style analysis. 'pct' should be used by those with a good reason.

Prerequisites: init_*, motion_deskull.

Outputs: scaled.