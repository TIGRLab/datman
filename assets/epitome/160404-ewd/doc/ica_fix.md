ica
---
Usage: ica_fix <func_prefix> <train_data> <threshold>

+ func_prefix -- functional data prefix (eg., smooth in func_smooth).
+ train_data -- name of the .RData file in your fix/training_data/ folder.
+ threshold -- a number. Who knows what it means? It should be between 1-100, and the FSL people recommend 20, or a number between 1-5 for 'more conservative' cleanup. I always use 20 because the FSL people never explained what this number does.
+ motionregress -- use fix's ('-m -h 0') option with also regresses out motion confounds after they have been detrended (linear)
+ cleanup -- delete all the intermediate files from this step (you might want to look at them first, to get an idea of what this step is doing...)

Runs FSL ICA-based de-noising based on expert rating of ICA components into signal and noise. FSL FIX is not easy to run outside of the FSL ecosystem, so you must follow a pretty tight perscription to run this module (see prereqs below). The key is all registrations need to be done with FSL, and you really should use 'filter' to remove (at least) the linear trend from all voxels.

There are currently 4 trained-weights files supplied:

+ Standard.RData - for use on more "standard" FMRI datasets / analyses; e.g., TR=3s, Resolution=3.5x3.5x3.5mm, Session=6mins, default FEAT preprocessing (including default spatial smoothing).
+ HCP_hp2000.RData for use on "minimally-preprocessed" HCP-like datasets, e.g., TR=0.7s, Resolution=2x2x2mm, Session=15mins, no spatial smoothing, minimal (2000s FWHM) highpass temporal filtering.
+ WhII_MB6.RData derived from the Whitehall imaging study, using multiband x6 EPI acceleration: TR=1.3s, Resolution=2x2x2mm, Session=10mins, no spatial smoothing, 100s FWHM highpass temporal filtering.
+ WhII_Standard.RData derived from more traditional early parallel scanning in the Whitehall imaging study, using no EPI acceleration: TR=3s, Resolution=3x3x3mm, Session=10mins, no spatial smoothing, 100s FWHM highpass temporal filtering.
+ 'autohawko.RData' : (in epitome assets) trained using Colin Hawko (of TIGRLab)'s labels of very noisy real data (35 runs Imitate or Observe Task runs) / TR=3s, Resolution=3x3x3mm, Session~5mins, no spatial smoothing, 100s FWHM highpass temporal filtering.'

Recommended epitome steps pre ica_fix (or rather, tested):

    . ${DIR_PIPE}/epitome/modules/pre/init_epi high 0 alt+z scale normal
    . ${DIR_PIPE}/epitome/modules/pre/linreg_calc_fsl high corratio 12
    . ${DIR_PIPE}/epitome/modules/pre/linreg_fs2epi_fsl
    . ${DIR_PIPE}/epitome/modules/pre/gen_regressors scaled
    . ${DIR_PIPE}/epitome/modules/pre/filter scaled 1 off off off off off
    . ${DIR_PIPE}/epitome/modules/pre/volsmooth filtered EPI_mask 5.0
    . ${DIR_PIPE}/epitome/modules/pre/ica volsmooth EPI_mask

This takes the above MELODIC output, generates a phony '.feat' folder, and runs FIX within that. The output it moved to the epitome SESS folder as `func_fix`.

Prerequisites: init_*, motion_deskull, linreg_calc_fsl, filter, ica.

Outputs: fix
