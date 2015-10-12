import scipy as sp
import numpy as np
import matplotlib.pyplot as plt
import epitome as epi

#
inputs = 'lists/cleaned-hc.csv'
################################
subjects = np.genfromtxt(inputs, dtype=str)
title = os.path.basename(inputs).split('.')[0]
rois = epi.utilities.loadnii('anat_MNI_rois-detailed.nii.gz')[0]

n_subj = len(subjects)
n_rois = len(np.unique(rois))-1

full_rest_G = np.zeros((n_rois, n_rois, n_subj))
full_im_G = np.zeros((n_rois, n_rois, n_subj))
full_ob_G = np.zeros((n_rois, n_rois, n_subj))

for i, subj in enumerate(subjects):
    mask = epi.utilities.loadnii(subj + '_rest-mask.nii.gz')[0]
    rest = epi.utilities.loadnii(subj + '_rest.nii.gz')[0]
    im = epi.utilities.loadnii(subj + '_im.nii.gz')[0]
    ob = epi.utilities.loadnii(subj + '_ob.nii.gz')[0]
    
    G = epi.utilities.roi_graph(rest, rois)
    epi.plot.graph(G, 0.5, 'plots/' + subj + '_rest-graph')
    full_rest_G[:,:, i] = G

    G = epi.utilities.roi_graph(im, rois)
    epi.plot.graph(G, 0.5, 'plots/' + subj + '_im-graph')
    full_im_G[:,:, i] = G

    G = epi.utilities.roi_graph(ob, rois)
    epi.plot.graph(G, 0.5, 'plots/' + subj + '_ob-graph')
    full_ob_G[:,:, i] = G

mean_G = np.mean(full_rest_G, axis=2)
epi.plot.graph(mean_G, 0.5, 'plots/' ' _rest-graph')

mean_G = np.mean(full_im_G, axis=2)
epi.plot.graph(mean_G, 0.5, 'plots/' '_im-graph')

mean_G = np.mean(full_ob_G, axis=2)
epi.plot.graph(mean_G, 0.5, 'plots/' '_ob-graph')

# get the mean time series from each roi
