#!/usr/bin/env python

import sys
import numpy as np
import scipy as sp
import scipy.signal as signal

def scale_frequencies(lo, hi, nyq):
    """
    Scales frequencies in Hz to be between [0,1], 1 = nyquist frequency.
    """
    lo = lo / nyq
    hi = hi / nyq

    return lo, hi

def butter_bandpass(data, lo, hi, wtype='butter', ptype='band'):
    """
    Bandpasses the data using a bi-directional low-order filter.
    """
    if wtype == 'butter':
        b, a = signal.butter(4, [lo, hi], btype=ptype)
    
    data = signal.filtfilt(b, a, data)

    return data

def moving_average(data, N=5):
    """
    Calculates a moving average of length N. Pads the output to prevent
    transients at the beginning and end of the run.
    """
    # pad the to-be-smoothed vector by the window length on each side
    padded = np.zeros(data.shape[0]+(N*2),)
    padded[N:-N] = data

    # insert the 1st and last value, respectively
    padded[0:N] = data[0]
    padded[-1-N:] = data[-1]

    # convolve the time series with a vector of 1/N
    data = np.convolve(padded, np.ones((N,), ) / N, mode='full')[(N-1):]
    data = data[N:-N]

    return data

def tukeywin(window_length, alpha=0.5):
    """
    The Tukey window, also known as the tapered cosine window, can be regarded 
    as a cosine lobe of width \alpha * N / 2 that is convolved with a
    rectangular window of width (1 - \alpha / 2). At \alpha = 1 it becomes 
    rectangular, and at \alpha = 0 it becomes a Hann window.
 
    We use the same reference as MATLAB to provide the same results in case
    users compare a MATLAB output to this function output.
 
    References
    ----------
    Code:
    http://leohart.wordpress.com/2006/01/29/hello-world/

    MATLAB:
    http://www.mathworks.com/access/helpdesk/help/toolbox/signal/tukeywin.html
    """
    ## special cases
    if alpha <= 0:
        return np.ones(window_length)
    elif alpha >= 1:
        return np.hanning(window_length)

    ## normal case
    x = np.linspace(0, 1, window_length)
    window = np.ones(x.shape)

    # first condition: 0 <= x < alpha/2
    c1 = x < alpha/2
    window[c1] = 0.5 * (1 + np.cos(2*np.pi/alpha * (x[c1] - alpha/2)))

    # second condition already taken care of
    # third condition 1 - alpha / 2 <= x <= 1
    c3 = x >= (1 - alpha/2)
    window[c3] = 0.5 * (1 + np.cos(2*np.pi/alpha * (x[c3] - 1 + alpha/2)))

    return window

def calculate_spectra(ts, samp, olap=0, nseg=3, wtype='tukey', norm=True):
    """
    ts = input time series
    samp = sampling rate in Hz
    olap = window overlap in %. 0 == Bartlett's method.
    nseg = number of segments to take for PSD estimation.
    wtype = window to use during calculation. see scipy.signal.get_window.
    norm = If true, normalizes spectra such that it's sum = 1.

    Calculates the spectra of an input time series using the specified window.
    Inspired by He, Biyu J in Neuron 2010 & J Neurosci 2011.
    """

    if olap < 0 or olap >= 100:
        print('INVALID: olap = ' + str(olap) + ', should be a % (1-99)')

    # calculate the length of each window, accounting for nseg and olap
    ntrs = ts.shape[-1]
    nperseg = ntrs / nseg * (1 + olap/100.0)

    while np.remainder(nperseg, 1) != 0:
        nseg = nseg - 1
        nperseg = ntrs / float(nseg) * (1 + olap/100.0)

    olap = olap * nperseg

    print('MSG: Calculating spectra using {} pts/window.'.format(nperseg))

    if wtype == 'tukey':
        window = tukeywin(nperseg, alpha=0.5)
        spectra = signal.welch(ts, fs=samp, window=window,
                                            noverlap=olap,
                                            nperseg=nperseg,
                                            return_onesided=True,
                                            scaling='spectrum')

    else:
        try:
            spectra = signal.welch(ts, fs=samp, window=wtype, 
                                                noverlap=olap,
                                                nperseg=nperseg,
                                                return_onesided=True,
                                                scaling='spectrum')

        except:
            print('Input window ' + str(wtype) + 'is invalid!')
            print('Using scipy default: hanning...')
            spectra = signal.welch(ts, fs=samp, noverlap=olap,
                                                nperseg=nperseg,
                                                return_onesided=True,
                                                scaling='spectrum')

    fs = spectra[0]
    pxx = spectra[1]

    # convert to %s (i.e., sum of pxx = 1)
    if norm == True:
        pxx = pxx / np.sum(pxx)

    return fs, pxx
