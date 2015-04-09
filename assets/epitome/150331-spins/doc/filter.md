filter
------
Usage: filter <func_prefix> <det> <std> <gm> <anaticor> <compcor> <compnum> <dv>

+ func_prefix -- functional data prefix (eg.,smooth in func_smooth). 
+ det -- polynomial order to detrend each voxel against. 
+ std -- if == on, does standard basic time-series filtering (mean white matter and csf regression).
+ gm -- if == on, regress mean global signal from each voxel (careful...). 
+ anaticor -- if == on, regress 15mm local white matter signal from data. 
+ compcor -- if == on, regress top 3 principal components from both the white matter and csf from the data.
+ compnum -- if using compcor, the number of components per ROI to regress.
+ dv -- if == on, regress mean draining vessel signal from each voxel. 

Creates a series of regressors from fMRI data and a freesurfer segmentation: 

+ white matter + eroded mask
+ ventricles + eroded mask
+ grey matter mask
+ brain stem mask
+ dialated whole-brain mask
+ draining vessels mask
+ DVARS (for 'scrubbing' -- calculated here because we need detrended data) [1].

The regressors calculated depend on the method(s) used to filter the data:

std
---
'Standard' resting state tissue regressors for resting-state fMRI . See [2] for an overview.

+ local white matter regressors + 1 temporal lag
+ ventricle regressors + 1 temporal lag

gm
--
Global mean regression. Often, but controvertially, combined with 'std' above. Watch your anticorrelations!

anaticor
--------
An AFNI method for dealing with artifacts in your data using 15mm local white matter regressors + 1 temporal lag. Tends to be conservative. Good at dealing with distance-dependnet motion artifacts, but less so at dealing with physiological noise [3].

compcor
-------
Takes the first N principal components from the white matter and ventricle tissue masks and applies them as regressors. Believed by some to deal well with physiological noise (like global mean regression) without the spurious anticorrelations [4]. 

draining vessel
---------------
An experimental regressor c.o. Dr. W. Dale Stevens. 

+ draining vessel regressors + 1 temporal lag


This computes detrended nuisance time series, fits each run with a computed noise model, and subtracts the fit. Computes temporal SNR. This program always regresses the motion parameters \& their first lags, as well as physiological noise regressors generated my McRetroTS if they are available. The rest are optional.

[1] Power JD, et al. 2012. Spurious but systematic correlations in functional connectivity MRI networks arise from subject motion. Neuroimage. 59(3).
[2] Van Dijk K, et al. 2010. Intrinsic Functional Connectivity As a Tool For Human Connectomics: Theory, Properties, and Optimization. Journal of Neurophysiology. 103(1).
[3] Jo HJ, et al. 2010. Mapping sources of correlation in resting state FMRI, with artifact detection and removal. Neuroimage. 52(2).
[4] Behzadi Y, et al. 2007. A component based noise correction method (CompCor) for BOLD and perfusion based fMRI. Neuroimage. 37(1).

Prerequisites: init_epi, linreg_calc_afni/fsl, linreg_FS2epi_afni/fsl.

Outputs: set of masks, regressors in PARAMS/, detrend (detrended, before regression model, mean per voxel removed), mean, std (standard deviation), noise (fit of regression model), filtered (residuals of regression model, mean added back in).
