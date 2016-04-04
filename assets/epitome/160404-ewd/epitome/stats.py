#!/usr/bin/env python

"""
A collection of statistical routines for MRI analysis.
"""

import os, sys
import numpy as np
import sklearn as sk

def partial_corr(C):
    """
    Partial Correlation in Python (clone of Matlab's partialcorr)
    from https://gist.github.com/fabianp/9396204419c7b638d38f

    This uses the linear regression approach to compute the partial
    correlation (might be slow for a huge number of variables). The
    algorithm is detailed here:

        http://en.wikipedia.org/wiki/Partial_correlation#Using_linear_regression

    Taking X and Y two variables of interest and Z the matrix with all the variable minus {X, Y},
    the algorithm can be summarized as

        1) perform a normal linear least-squares regression with X as the target and Z as the predictor
        2) calculate the residuals in Step #1
        3) perform a normal linear least-squares regression with Y as the target and Z as the predictor
        4) calculate the residuals in Step #3
        5) calculate the correlation coefficient between the residuals from Steps #2 and #4;

    The result is the partial correlation between X and Y while controlling for the effect of Z

    Returns the sample linear partial correlation coefficients between pairs of variables in C, controlling
    for the remaining variables in C.


    Parameters
    ----------
    C : array-like, shape (n, p)
        Array with the different variables. Each column of C is taken as a variable


    Returns
    -------
    P : array-like, shape (p, p)
        P[i, j] contains the partial correlation of C[:, i] and C[:, j] controlling
        for the remaining variables in C.
    """

    C = np.asarray(C)
    p = C.shape[1]
    P_corr = np.zeros((p, p), dtype=np.float)
    for i in range(p):
        P_corr[i, i] = 1
        for j in range(i + 1, p):
            idx = np.ones(p, dtype=np.bool)
            idx[i] = False
            idx[j] = False
            beta_i = linalg.lstsq(C[:, idx], C[:, j])[0]
            beta_j = linalg.lstsq(C[:, idx], C[:, i])[0]

            res_j = C[:, j] - C[:, idx].dot(beta_i)
            res_i = C[:, i] - C[:, idx].dot(beta_j)

            corr = stats.pearsonr(res_i, res_j)[0]
            P_corr[i, j] = corr
            P_corr[j, i] = corr

    return P_corr

def FD(motion, head_radius):
    """
    Loads motion parameters and uses head radius to calculate
    framewise displacement.
    """
    # load motion parameters
    FD = np.genfromtxt(motion)

    # check input head_radius (convert to float)
    try:
        head_radius = float(head_radius)
    except:
        print('Invalid head radius, defaulting to 50 mm')
        head_radius = 50

    FD[:,0] = np.radians(FD[:,0])*head_radius # roll
    FD[:,1] = np.radians(FD[:,1])*head_radius # pitch
    FD[:,2] = np.radians(FD[:,2])*head_radius # yaw

    # sum over absolute derivative for the 6 motion parameters
    FD = np.sum(np.abs(np.diff(FD, n=1, axis=0)), axis=1)
    FD = np.insert(FD, 0, 0) # align FD with original run & DVARS

    print(FD)

    return FD

def FDR_mask(p=[], q=1.05, iid='yes', crit='no'):

    """
    Calculates the Benjamini & Hochberg (1995) correction for multiple
    hypothesis testing from a list of p-values, and creates a binary mask
    where p-values are significant. Also optionally reports the critical
    p-value. Requires numpy.

    See http://www.jstor.org/stable/2346101 for details.

    - `p`   : a nD list or numpy array of p values.
    - `q`   : maximum acceptibe proportion of false positives. Default = 0.05.
    - `iid' : if iid='yes', uses liberal test assuming positive dependence
              or independence between tests. if iid='no', uses conservative
              test with no assumptions. Default = 'yes'.
    - `crit`: if crit='yes', also returns the critical p-value . Default = 'no'.
    """
    # initialize numpy array with > 2 p values
    if isinstance(p, np.ndarray) == False:
        p = np.array(p)

    if p.size < 2:
        print('p-value vector must have multiple values!')
        raise SystemExit

    q = float(q)

    # if p is > 1D, reshape to 1D
    if len(p.shape) > 1:
        dim = np.shape(p)
        shape = 1
        for d in dim:
            shape = shape * d
        p = p.reshape(shape)

    size = float(len(p)) # number of comparisons
    idx = np.argsort(p) # sort p values for test
    dat = p[idx]
    del(idx)

    # find threshold
    vec = np.arange(size) + 1.0
    if iid == 'yes':
        threshold = vec / size * q
    if iid == 'no':
        threshold = vec / size * q / np.sum([1 / vec])
    del(vec)

    # find largest p value below threshold
    H0_rej = dat <= threshold
    try:
        crit_p = np.max(dat[H0_rej])
    except:
        crit_p = 0.0
    del(dat, threshold)

    # create & reshape binary output mask
    mask = np.zeros(size)
    if crit_p > 0:
        mask[p <= crit_p] = 1

    if 'dim' in locals():
        shape = []
        for d in dim:
            shape.append(d)
        mask.reshape(shape)

    if crit == 'yes':
        return (mask, crit_p)
    else:
        return mask

def FDR_threshold(p=[], q=0.05, iid='yes'):

    """
    Calculates the Benjamini & Hochberg (1995) correction for multiple
    hypothesis testing from a list of p-values, and returns the threshold only.
    NaNs are ignored for the calculation.

    See http://www.jstor.org/stable/2346101 for details.

    - `p`   : a nD list or numpy array of p values.
    - `q`   : maximum acceptibe proportion of false positives. Default = 0.05.
    - `iid' : if iid='yes', uses liberal test assuming positive dependence
              or independence between tests. if iid='no', uses conservative
              test with no assumptions. Default = 'yes'.
    """
    # initialize numpy array with > 2 p values
    if isinstance(p, np.ndarray) == False:
        p = np.array(p)

    if p.size < 2:
        print('p-value vector must have multiple values!')
        raise SystemExit

    q = float(q)

    # if p is > 1D, reshape to 1D
    if len(p.shape) > 1:
        dim = p.shape
        shape = 1
        for d in dim:
            shape = shape * d
        p = p.reshape(shape)

    # remove NaNs
    p = p[np.where(np.isnan(p) == False)[0]]

    # sort the p-vector
    size = float(len(p)) # number of comparisons
    idx = np.argsort(p) # sort p values for test
    dat = p[idx]
    del(idx)

    # find threshold
    vec = np.arange(size) + float(1)
    if iid == 'yes':
        threshold = vec / size * q
    if iid == 'no':
        threshold = vec / size * q / np.sum([1 / vec])
    del(vec)

    # find largest p value below threshold
    H0_rej = dat <= threshold
    try:
        crit_p = np.max(dat[H0_rej])
    except:
        crit_p = 0
    del(dat, threshold)

    return crit_p

def fischers_r2z(data):
    """
    Fischer's r-to-z transform on a matrix (elementwise).
    """
    data = 0.5 * np.log( (1+data) / (1-data) )

    return data

def fischers_z2r(data):
    """
    Inverse of Fischer's r-to-z transform on a matrix (elementwise).
    """
    data = (np.exp(2*data) -1) / (np.exp(2 * data) + 1)

    return data

def pct_signal_change(data):
    """
    Converts input time series to percent signal change. This works on
    matricies of data, dealing with each time series separately.
    """
    dims = data.shape
    mean = np.tile(np.mean(data, axis=1), [dims[1], 1]).T
    data = (data - mean) / mean * 100

    return data

def pca_reduce(data, n=None, copy=True, whiten=False, cutoff=1000):
    """
    Principal component analysis dimensionality reduction using Scikit Learn.

    Inputs:
        data = timepoints x voxels matrix.
        n = None -- return all components
          = int -- return int components
        copy = if False, do pca in place.
        whiten = pre-whiten (decorrelate) data.
        cutoff = maximum number of input features before we move to an
                 efficient method.

    This mean-centers and auto-scales the data (in-place).

    Returns:
        pcs from the input data
        % variance explained by each of them

    methods
    -------
    normal -- standard PCA
    random -- randomized PCA (for large matricies [1])

    [1] Halko, N., Martinsson, P. G., Shkolnisky, Y., & Tygert, M. (2010).
        An algorithm for the principal component analysis of large data sets.
    """

    import sklearn.decomposition as dec

    data = data.astype(np.float)
    data -= np.mean(data) # mean-center entire dataset

    if data.shape[0] > cutoff:
        method = 'random'
    else:
        method = 'normal'

    # set n to be the cutoff if the dimensionality of the data is large
    if n == None and method == 'random':
        n = cutoff

    if method == 'random':
        pcmodel = dec.RandomizedPCA(n_components=n, copy=copy, whiten=whiten)
    elif method == 'normal':
        pcmodel = dec.pca.PCA(n_components=n, copy=copy, whiten=whiten)

    pcmodel.fit(data)
    data = pcmodel.transform(data)
    #components = pcmodel.components_
    exp_var = pcmodel.explained_variance_ratio_

    return data, exp_var
