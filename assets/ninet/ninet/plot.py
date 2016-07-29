#!/usr/bin/env python

import numpy as np
from copy import copy
import matplotlib.pyplot as plt
from matplotlib import animation

def reorient_to_radiological(image):
    """
    Reorients input 3D numpy matrix to be the proper orientation for plotting.
    Assumes inputs are in RAI ? 
    """
    
    image = np.transpose(image, (2,0,1))
    image = np.rot90(image, 2)

    return image

def compare_spectra(a, b, fs, title, a_std=None, b_std=None, hi=1):
    """
    Plots the log log spectra of two time series for comparison.
    """
    # remove bandpassed regions
    a = a[0:(len(a)*hi)-1]
    b = b[0:(len(b)*hi)-1]
    fs = fs[0:(len(fs)*hi)-1]

    plt.plot(fs, a, color='red', linewidth=2)
    plt.plot(fs, b, color='black', linewidth=2)

    # if a_std != None:
    #     a_std = a_std[0:(len(a_std)*hi)-1]
    #     plt.fill_between(fs, a, a+a_std, color='red', alpha=0.25)

    # if b_std != None:
    #     b_std = b_std[0:(len(b_std)*hi)-1]
    #     plt.fill_between(fs, b, b+b_std, color='black', alpha=0.25)

    #plt.axis('off')
    plt.xlabel('frequency (Hz)')
    plt.ylabel('normalized power')
    plt.xscale('log')
    plt.yscale('log')
    plt.ylim(ymax=1)
    plt.suptitle(title)
    plt.savefig(title + '.pdf')
    plt.close()

def graph(G, minmax, title):
    plt.imshow(G, vmin=-np.abs(minmax), 
                  vmax=np.abs(minmax), 
                  cmap=plt.cm.RdBu_r, 
                  interpolation='nearest')
    plt.colorbar()
    plt.suptitle(title)
    plt.savefig(title + '.pdf')
    plt.close()

def phase_portrait(x, y, exp_a, exp_b, title): 

    plt.plot(x, y, color='red')
    plt.suptitle(title + ' A: explained = ' + str(exp_a) + 
                        ', B: explained = ' + str(exp_b))
    plt.savefig(title  + '.pdf')
    plt.close()

def delay_embedded_phase_portraits(x, lags, title):

    w, h = plt.figaspect(len(lags))

    plt.figure(figsize=(w,h))

    for i, t in enumerate(lags):

        plt.subplot(len(lags), 1, i+1)

        a = x[:-t]
        b = x[t:]

        plt.plot(a, b, color='red')
        plt.title(t)

    plt.suptitle(title)
    plt.tight_layout()
    plt.savefig(title  + '.pdf')
    plt.close()


def mean_std(mean, std, color):
    """
    Adds mean + standard deviation to a currently-opened plot in the 
    chosen color.
    """
    plt.plot(mean, color=color, linewidth=2)
    plt.fill_between(np.arange(len(mean)), mean-std, mean+std, 
                                                     color=color, alpha=0.25)

def states(data, color='black', approach='median'):
    """
    data -- timeseries
    idx -- color of line plotted
    approach -- 'median' == points => median = 1, else 0.
    """

    # protect ma megabytes
    data = copy(data)

    if approach == 'median':
        cutoff = np.median(data)

    elif approach == 'mean':
        cutoff = np.mean(data)

    data[data < cutoff] = 0
    data[data >= cutoff] = 1
    plt.plot(data, color=color, linewidth=2)
    plt.fill_between(np.arange(len(data)), np.zeros(len(data)), data,
                                                    color=color, alpha=0.25)

# def plot_slidewin_init():
#     """
#     Initialization function: plot the background of each frame.
#     """
#     im.set_data()
    
#     return im

def slidewin_animate(data, win_step, win_len, i, subj):
    """
    Animation function.  This is called sequentially.
    """
    win_start = i*win_step
    win_stop = i*win_step + win_len

    data_slice = data[:, win_start:win_stop]
    corr = np.corrcoef(data_slice)

    im = plt.imshow(corr, interpolation='nearest', cmap=plt.cm.RdBu_r,
                                                      vmin=-1, vmax=1)
    plt.title('Subj ' + str(subj) + ': ' + str(i*win_step+0.5*win_len) + ' s')

    return im

def slidewin_corr(data, n_steps, win_step, win_len, subj):
    """
    data -- voxels x timepoints
    n_steps -- number of windows to take
    win_step -- step length of window (50% of full length?)
    win_len -- length of window
    subj -- name or number.
    
    Returns an animated .gif of the correlation matrix over each window per
    subject. This matrix goes into the intranetwork analysis.

    If you want mp4, you need ffmpeg or mencoder. The x264 codec is used, so
    the video can be embedded in html5. For more information, see:
        
    http://matplotlib.sourceforge.net/api/animation_api.html
    http://jakevdp.github.io/blog/2012/08/18/matplotlib-animation-tutorial/
    """

    # Set up figure, axis, and the plot
    fig = plt.figure()
    im = plt.imshow(np.zeros((data.shape[0], data.shape[0])),  
                    interpolation='nearest', cmap=plt.cm.RdBu_r,
                                                vmin=-1, vmax=1)
    plt.axis('off')

    anim = animation.FuncAnimation(fig, 
           lambda i: slidewin_animate(data, win_step, win_len, i, subj), 
                                                            frames=n_steps-1, 
                                                            interval=20, 
                                                            blit=True)
    
    #anim.save('basic_animation.mp4', fps=30, extra_args=['-vcodec', 'libx264'])
    anim.save('net-dynamics-animation-' + str(subj) + '.gif', 
                                          writer='imagemagick', 
                                          fps=12, 
                                          extra_args=['-vcodec', 'libx264'])