#!/usr/bin/env python
import numpy as np
import epitome as epi

def slidewin_intranet_corr(data, idx, net, n_steps, win_step, win_len):
    """
    data -- voxels x timepoints
    idx -- voxel network labels (integers)
    net -- interger value representing network of interest
    n_steps -- number of windows to take
    win_step -- step length of window (50% of full length?)
    win_len -- length of window

    Returns the mean + std across all windowed samples of the timeseries 
    supplied in data.

    Gives a measure of intranetwork correlation variability over time. This
    can be used to see if / when networks become coherent, and allows us to
    compare this across networks.
    """

    idx = np.where(np.array(idx) == net)[0] 
    net_data = data[idx, :]

    mean = np.zeros(n_steps)
    std = np.zeros(n_steps)

    for step in np.arange(n_steps-1):

        win_start = step*win_step
        win_stop = step*win_step + win_len

        data_slice = net_data[:, win_start:win_stop]
        corr = np.corrcoef(data_slice)

        for x in np.arange(corr.shape[0]):
            corr[x,x] = np.nan

        mean[step] = np.nanmean(corr)
        std[step] = np.nanstd(corr)

    return mean, std

def main():
    data = np.load('/projects/jdv/data/dynamics/da-dmn.npy')
    #data = np.load('/srv/data/hcp-attractors/da-dmn.npy')
    N = 3
    lo = 0.009 # bandpass in Hz
    hi = 0.2  # bandpass in Hz
    samp = 1.4285 # sampling rate in Hz
    lags = [1,2,3,4,5,6,7,8] # 
    net_idx = [1,1,1,1,1,1,2,2,2,2,0,2] # idx of unique networks, 0 = remove
    win_len = 60 # length of window in TRs
    n_steps = 40 # number of windows
    # scaled to 0, 1 (1 == nyquist frequency)

    n_rois = len(np.array(net_idx))
    lo, hi = epi.signal.scale_frequencies(lo, hi, samp/2)
    n_subj = np.shape(data)[0] / n_rois
    n_net = len(np.unique(net_idx))
    win_step = data.shape[1] / float(n_steps)
    corrs = np.zeros((n_steps-1, 2))
    #corrs = np.zeros(n_subj)

    # normalize time series
    data = epi.stats.pct_signal_change(data)

    # initialize frequency arrays
    ts = data[0,:]
    fs, pxx = epi.signal.calculate_spectra(ts, samp, olap=0, nseg=3, wtype='tukey', norm=True)
    pxx_mat_a_mean = np.zeros((n_subj, len(pxx)))
    pxx_mat_b_mean = np.zeros((n_subj, len(pxx)))
    pxx_mat_a_std = np.zeros((n_subj, len(pxx)))
    pxx_mat_b_std = np.zeros((n_subj, len(pxx)))

    for i, n in enumerate(np.arange(n_subj)):
        print i
        print str(n_rois*i) + ' ' + str(n_rois*(i+1)-1)

        # extract data
        tmp_data = data[n_rois*i:n_rois*(i+1)]
        tmp_idx = np.where(np.array(net_idx) > 0)[0]

        # calculate spectra of each time series
        pxx_roi = np.zeros((tmp_data.shape[0], len(pxx)))

        for j, roi in enumerate(np.arange(len(tmp_idx))):
            if net_idx[j] != 0:
                ts = tmp_data[roi, :]
                fs, pxx = epi.signal.calculate_spectra(ts, samp, olap=0, nseg=3,  wtype='tukey', norm=True)
                pxx_roi[roi, :] = pxx

        tmp_idx = np.where(np.array(net_idx) == 1)[0]
        spectra_a_mean = np.mean(pxx_roi[tmp_idx, :], axis=0)
        spectra_a_std = np.std(pxx_roi[tmp_idx, :], axis=0)
        pxx_mat_a_mean[i, :] = spectra_a_mean
        pxx_mat_a_std[i, :] = spectra_a_std

        tmp_idx = np.where(np.array(net_idx) == 2)[0]
        spectra_b_mean = np.mean(pxx_roi[tmp_idx, :], axis=0)
        spectra_b_std = np.std(pxx_roi[tmp_idx, :], axis=0)
        pxx_mat_b_mean[i, :] = spectra_b_mean
        pxx_mat_b_std[i, :] = spectra_b_std
        
        plt.figure()
        epi.plot.compare_spectra(spectra_a_mean, spectra_b_mean, fs, 'roi-mean-spectra-subject-' + str(i), spectra_a_std, spectra_b_std, hi)

        # bandpass data
        tmp_data = epi.signal.butter_bandpass(tmp_data, lo, hi)

        # plot full correlation matrix animation
        epi.plot.slidewin_corr(tmp_data, n_steps, win_step, win_len, i)

        # do the intranetwork cohesion sliding window analysis
        w, h = plt.figaspect(3)
        plt.figure(figsize=(h, h))

        plt.subplot(2,2,1)
        for net in filter(lambda x: x > 0, np.unique(net_idx)):

            mean, std = slidewin_intranet_corr(tmp_data, net_idx, net, n_steps, win_step, win_len)

            if net == 1:
                tmp_mean_1 = mean
                epi.plot.mean_std(mean, std, 'red')
            else:
                tmp_mean_2 = mean
                epi.plot.mean_std(mean, std, 'black')

        plt.hlines(0, 0, n_steps-1, linestyles='dotted') # no correlation
        plt.xlim(0, n_steps-1) # time 
        plt.ylim(-1, 1) # correlations
        plt.ylabel('correlation (r)')
        plt.title(r'intra-network correlation $\mu$ and $\sigma$.')
        
        plt.subplot(2,2,2)
        plt.plot(tmp_mean_1 - tmp_mean_2, color='black', linewidth=2)

        plt.hlines(0, 0, n_steps-1, linestyles='dotted') # no correlation
        plt.xlim(0, n_steps-1) # time 
        plt.ylim(-1, 1) # correlations
        plt.ylabel('correlation (r)')
        plt.xlabel('time step (' + str(win_len) + ' s windows)')
        plt.title(r'DA $\mu$ - DMN $\mu$')

        plt.subplot(2,2,3)
        epi.plot.states(tmp_mean_1, color='red', approach='mean')
        epi.plot.states(tmp_mean_2, color='black', approach='mean')

        plt.xlim(0, n_steps-1) # time 
        plt.ylim(-0.5, 1.5) # states
        plt.ylabel('state')
        plt.xlabel('time step (' + str(win_len) + ' s windows)')
        plt.title(r'State switching of DA $\mu$ and DMN $\mu$')

        plt.subplot(2,2,4)
        plt.hist(tmp_mean_1, bins=20, range=(-1,1), histtype='stepfilled', color='red', alpha=0.5)
        plt.hist(tmp_mean_2, bins=20, range=(-1,1), histtype='stepfilled', color='black', alpha=0.5)
        plt.vlines(0, 0, 10, linestyles='dotted')
        plt.ylabel('correlation (r)')
        plt.xlabel('count')
        plt.title(r'Distributions of DA $\mu$ and DMN $\mu$')

        #plt.tight_layout()
        plt.suptitle('intra-network r dynamics for the DMN and DA')
        plt.savefig('corr-dynamics-' + str(i) + '.pdf')
        plt.close()
        
        # create z-scored correlation matrix (for group mean)
        tmp_idx = np.where(np.array(net_idx) > 0)[0]
        tmp_data = np.corrcoef(tmp_data[tmp_idx, :])
        tmp_data = epi.stats.fischers_r2z(tmp_data)

        # stack data
        if i == 0:
            out_data = tmp_data
        else:
            out_data = np.dstack((out_data, tmp_data))

    # take mean, convert back to r
    out_data = np.mean(out_data, axis=2)
    out_data = epi.stats.fischers_z2r(out_data)

    epi.plot.graph(out_data, 0.5, 'group-correlation-network')

    # plot group spectra means
    pxx_mat_a_mean = np.mean(pxx_mat_a_mean, axis=0)
    pxx_mat_a_std = np.mean(pxx_mat_a_std, axis=0)
    pxx_mat_b_mean = np.mean(pxx_mat_b_mean, axis=0)
    pxx_mat_b_std = np.mean(pxx_mat_b_std, axis=0)

    plt.figure()
    epi.plot.compare_spectra(pxx_mat_a_mean, pxx_mat_b_mean, fs,
                           'group-spectra',
                            pxx_mat_a_std, pxx_mat_b_std, hi)

def phase_plot():

    data = np.load('da-dmn.npy')
    data = epi.stats.pct_signal_change(data)

    net_idx = [1,1,1,1,1,1,2,2,2,2,0,2] # idx of unique networks, 0 = remove
    n_rois = len(np.array(net_idx))
    n_subj = np.shape(data)[0] / n_rois

    for n in np.arange(n_subj):
        # top 3 PCs (plot bottom 2)
        tmp_data = data[n_rois*n:n_rois*(n+1)]
        tmp_idx = np.where(np.array(net_idx) > 0)[0]
        tmp_data = tmp_data[tmp_idx, :]
        components, exp = epi.stats.pca_reduce(tmp_data.T, n=2)
        epi.plot.phase_portrait(components.T[0], components.T[1], 
                                         exp[0], exp[1],  'da-dmn-phaseportrait-' + str(n))
        # top PC per network
        # tmp_data = data[n_rois*n:n_rois*(n+1)]
        # tmp_idx = np.where(np.array(net_idx) == 1)[0]
        # d = tmp_data[tmp_idx, :]
        # pc_a, exp_a = epi.stats.pca_reduce(d.T, n=1)
        # tmp_idx = np.where(np.array(net_idx) == 2)[0]
        # d = tmp_data[tmp_idx, :]
        # pc_b, exp_b = epi.stats.pca_reduce(d.T, n=1)
        # epi.plot.phase_portrait(pc_a.T[0], pc_b.T[0], exp_a, exp_b,
        #                         'da-dmn-phaseportrait-' + str(n))
        print(n)






# def unused():
#     """
#     Noone loves these.
#     """

    #calculate pc spectra
    # pc_a_spec = calculate_spectra(pc_a, samp)
    # pc_b_spec = calculate_spectra(pc_b, samp)

    # # calculate pc derivatives
    # pc_a_diff = np.diff(pc_a, n=1)
    # pc_b_diff = np.diff(pc_b, n=1)

    # #calculate pc envalope
    # pc_a_env = np.abs(signal.hilbert(pc_a_diff))
    # pc_b_env = np.abs(signal.hilbert(pc_b_diff))

    # pc1_a, pc2_a, exp_a = return_top_2_pcs(tmp_data[0:6, :])
    # pc1_b, pc2_b, exp_b = return_top_2_pcs(tmp_data[0:6, :])

    # plot PCs
    # plot_timeseries(np.vstack((pc_a, pc_b)), 2, 2,
    #                'roi-pc-timeseries-subject-' + str(i))

    # compare_spectra(pc_a_spec, pc_b_spec,
    #                'roi-pc-spectra-subject-' + str(i))

    # plot_timeseries(np.vstack((pc_a_diff, pc_b_diff)), 2, 2,
    #                'roi-pc-diff-timeseries-subject-' + str(i))

    # plot_timeseries(np.vstack((pc_a_diff, pc_b_diff)), 2, 2,
    #                'roi-pc-env-timeseries-subject-' + str(i),
    #                 np.vstack((pc_a_env, pc_b_env)))

    # # plot phase portrait of both pcs
    # plot_phase_portrait(pc_a.T, pc_b.T, exp_a, exp_b,
    #                    'roi-pc_phase-portrait-subject-' + str(i))

    # # plot phase portrait of the derivative of both pcs
    # plot_phase_portrait(pc_a_diff.T, pc_b_diff.T, exp_a, exp_b,
    #                    'roi-pc-diff_phase-portrait-subject-' + str(i))

    # # plot phase portrait of the envalope of both pcs
    # plot_phase_portrait(pc_a_env.T, pc_b_env.T, exp_a, exp_b,
    #                      'roi-pc-env_phase-portrait-subject-' + str(i))

    # # plot phase portrait of pc_A + lag
    # plot_delay_embedded_phase_portraits(pc_a.T, lags, 
    #                 'roi-pc-a_delay-embedded-portrait-subject-' + str(i))

    # # plot phase portrait of pc_B + lag
    # plot_delay_embedded_phase_portraits(pc_b.T, lags, 
    #                 'roi-pc-b_delay-embedded-portrait-subject-' + str(i))

    # # plot phase portrait top 2 pcs from network a
    # plot_phase_portrait(pc1_a.T, pc2_a.T, exp_a, exp_a, 
    #                     'roi-2pcs-a-subject-' + str(i))

    # # plot phase portrait top 2 pcs from network a
    # plot_phase_portrait(pc1_b.T, pc2_b.T, exp_b, exp_b, 
    #                     'roi-2pcs-b-subject-' + str(i))

    #corrs[i] = np.corrcoef(pc_a, pc_b)[0][1]

    # return 'sadness'

# def plot_timeseries(data, n_rois, n_net, title, envs=None):
#     """
#     This function needs to be fixed to work with the network indicies.
#     """
#     # plot timeseries
#     for i in np.arange(n_rois):
        
#         plt.subplot(n_rois, 1, i+1)
        
#         plot_data = data[i, :]
        
#         if envs != None:
#             plot_envs = envs[i, :]


#         if i < n_rois/n_net:
#             plt.plot(plot_data, linewidth=1, color='red')

#             if envs != None:
#                 plt.plot(plot_envs, linewidth=1, color='black')

#             plt.axis('off')

#         else:
#             plt.plot(plot_data, linewidth=1, color='blue')
            
#             if envs != None:
#                 plt.plot(plot_envs, linewidth=1, color='black')

#             plt.axis('off')

#     plt.suptitle(title)
#     plt.savefig(title + '.pdf')
#     plt.close()
