filter
------
Usage: filter <func_prefix> <det> <diff> <lag> <sq> <std> <gm> <dv> <anaticor> <compcor> <mask>

+ func_prefix -- functional data prefix (eg.,smooth in func_smooth). 
+ det -- polynomial order to detrend each voxel against. 
+ diff -- if == on, regresses first differences of regressors from data as well. If `sq` is also on, this takes the derivative of the squares.
+ lag -- if == on, regress the first lags of regressors from data as well.
+ sq -- if == on, regresses squares of regressors from data as well. Does NOT take the squares of the derivatives.
+ std -- if == on, does standard basic time-series filtering (6 paramater head motion, mean white matter, csf regression).
+ gm -- if == on, regress mean global signal from each voxel (careful...). 
+ dv -- if == on, regress mean draining vessel signal from each voxel.
+ anaticor -- if == on, regress 15mm local white matter signal from data.
+ compcor -- if > 0, regress top n PCA regressors from the white matter and csf. 0 == off.
+ mask -- prefix for the EPI brain mask used [default: EPI_mask]

Creates a series of regressors from fMRI data and a freesurfer segmentation: 

+ white matter + eroded mask
+ ventricles + eroded mask
+ grey matter mask
+ brain stem mask
+ dialated whole-brain mask
+ draining vessels mask
+ DVARS (for 'scrubbing' -- calculated here because we need detrended data) [1].

All regressors are constrained within the supplied EPI mask (for partial acquisitions in particular).

The regressors calculated depend on the method(s) used to filter the data:

std
---
'Standard' resting state tissue regressors for resting-state fMRI . See [2] for an overview.

+ 6 head motion paramaters
+ local white matter regressors
+ ventricle regressors

gm
--
Global mean regression. Often, but controvertially, combined with 'std' above. Watch your anticorrelations!

+ global mean signal

dv
--
An experimental draining vessel regressor c.o. Dr. W. Dale Stevens. 

+ mean draining vessel signal

diff
----
Combined with std, gm, and/or dv above to additionally regress the first derivative(s) of the selected regressors from the data.

sq
--
Combined with std, gm, dv, and/or diff above to additionall regress the squares of the computed regressors from the data. See [5] for more details.

anaticor
--------
An AFNI method for dealing with artifacts in your data using 15mm local white matter regressors + 1 temporal lag. Tends to be conservative. Good at dealing with distance-dependnet motion artifacts, but less so at dealing with physiological noise [3]. NB: Currently does not interact with the DET, LAG, or SQ options. This will only produce the local WM regressor and the first lag.

compcor
-------
Takes the first N principal components from the white matter and ventricle tissue masks and applies them as regressors. Believed by some to deal well with physiological noise (like global mean regression) without the spurious anticorrelations [4]. 

This computes detrended nuisance time series, fits each run with a computed noise model, and subtracts the fit. Computes temporal SNR. This program always regresses the motion parameters \& their first lags, as well as physiological noise regressors generated my McRetroTS if they are available. The rest are optional.

[1] Power JD, et al. 2012. Spurious but systematic correlations in functional connectivity MRI networks arise from subject motion. Neuroimage. 59(3).
[2] Van Dijk K, et al. 2010. Intrinsic Functional Connectivity As a Tool For Human Connectomics: Theory, Properties, and Optimization. Journal of Neurophysiology. 103(1).
[3] Jo HJ, et al. 2010. Mapping sources of correlation in resting state FMRI, with artifact detection and removal. Neuroimage. 52(2).
[4] Behzadi Y, et al. 2007. A component based noise correction method (CompCor) for BOLD and perfusion based fMRI. Neuroimage. 37(1).
[5] Satterthwaite TF, et al. 2013. An improved framework fro confound regression and filtering for control of motion artifact in the preprocessing of resting-state functional connectivity data. Neuroimage. 64(1).

Prerequisites: init_*, motion_deskull, linreg_calc_afni/fsl, linreg_FS2epi_afni/fsl.

Outputs: set of masks, regressors in PARAMS/, detrend (detrended, before regression model, mean per voxel removed), mean, std (standard deviation), noise (fit of regression model), filtered (residuals of regression model, mean added back in).
