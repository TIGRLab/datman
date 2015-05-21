#!/usr/bin/env python
"""
Produces QC documents for each exam.

Usage: 
    qc.py [options]

Arguments: 
    <scanid>        Scan ID to QC for. E.g. DTI_CMH_H001_01_01

Options: 
    --datadir DIR      Parent folder holding exported data [default: data]
    --qcdir DIR        Folder for QC reports [default: qc]
    --verbose          Be chatty
    --debug            Be extra chatty
    --dry-run          Don't actually do any work

DETAILS

    This program requires the AFNI toolkit to be available, as well as NIFTI
    scans for each acquisition to be QC'd. That is, it searches for exported
    nifti acquistions in:

        <datadir>/nifti/<timepoint>

"""
import os
import sys
import datetime
import glob
import numpy as np
import scipy as sp
import scipy.signal as sig
import dicom as dcm
import nibabel as nib
import datman as dm
import datman.utils
import datman.scanid
import subprocess as proc
from copy import copy
from docopt import docopt

import matplotlib
matplotlib.use('Agg')   # Force matplotlib to not use any Xwindows backend
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

DEBUG  = False
VERBOSE= False
DRYRUN = False

def log(message): 
    print message
    sys.stdout.flush()

def error(message): 
    log("ERROR: " + message)

def verbose(message): 
    if not(VERBOSE or DEBUG): return
    log(message)

def debug(message): 
    if not DEBUG: return
    log("DEBUG: " + message)

def makedirs(path):
    debug("makedirs: {}".format(path))
    if not DRYRUN: os.makedirs(path)

def run(cmd):
    debug("exec: {}".format(cmd))
    if not DRYRUN: 
        p = proc.Popen(cmd, shell=True, stdout=proc.PIPE, stderr=proc.PIPE)
        out, err = p.communicate() 
        if p.returncode != 0: 
            log("Error {} while executing: {}".format(p.returncode, cmd))
            out and log("stdout: \n>\t{}".format(out.replace('\n','\n>\t')))
            err and log("stderr: \n>\t{}".format(err.replace('\n','\n>\t')))
        else:
            debug("rtnval: {}".format(p.returncode))
            out and debug("stdout: \n>\t{}".format(out.replace('\n','\n>\t')))
            err and debug("stderr: \n>\t{}".format(err.replace('\n','\n>\t')))

def qc_folder(scanpath, prefix, outputdir, handlers):
    """
    QC all the images in a folder (scanpath).

    Outputs PDF and other files to outputdir. All files named startng with
    prefix.
    """

    outputdir = dm.utils.define_folder(outputdir)
    pdffile = os.path.join(outputdir, 'qc_' + prefix + '.pdf')
    if os.path.exists(pdffile):
        debug("{} pdf exists, skipping.".format(pdffile))
        return 

    pdf = PdfPages(pdffile)
   
    filetypes = ('*.nii.gz', '*.nii')
    found_files = []
    for filetype in filetypes:
        found_files.extend(glob.glob(scanpath + '/' + filetype))

    for fname in found_files:
        verbose("QC scan {}".format(fname))
        ident, tag, series, description = dm.scanid.parse_filename(fname)
        if tag not in qc_handlers:
            log("QC hanlder for scan {} (tag {}) not found. Skipping.".format(
                fname, tag))
            continue
        qc_handlers[tag](fname, outputdir, pdf)

    # finally, close the pdf
    d = pdf.infodict()
    d['CreationDate'] = datetime.datetime.today()
    d['ModDate'] = datetime.datetime.today()
    pdf.close()

def ignore(fpath, outputdir, pdf):
    pass

def fmri_qc(fpath, outputdir, pdf):
    """
    This takes an input image, motion corrects, and generates a brain mask. 
    It then calculates a signal to noise ratio map and framewise displacement
    plot for the file.
    """
    # if the number of TRs is too little, we skip the pipeline
    ntrs = check_n_trs(fpath)

    if ntrs < 3:
        return pdf

    opath = outputdir
    filename = os.path.basename(fpath)

    # FIXME: use a proper tempdir 

    # motion correct + calculate motion paramaters
    cmd = '3dvolreg -prefix ' + opath + '/tmp_mcorr.nii.gz -twopass -twoblur 3 -Fourier -1Dfile ' + opath + '/tmp_motion.1D ' + fpath
    run(cmd)

    # calculate mean
    cmd = '3dTstat -prefix ' + opath + '/tmp_mean.nii.gz ' + opath + '/tmp_mcorr.nii.gz'
    run(cmd)

    # calculate brain mask from mean
    cmd = ' 3dAutomask -prefix ' + opath +  '/tmp_mask.nii.gz -clfrac 0.5 -peels 3 ' + opath + '/tmp_mean.nii.gz'
    run(cmd)

    # calculate standard deviation
    cmd = '3dTstat -prefix ' + opath + '/tmp_std.nii.gz  -stdev ' + opath + '/tmp_mcorr.nii.gz'
    run(cmd)

    # calculate SFNR
    cmd = '3dcalc -prefix ' + opath + '/tmp_sfnr.nii.gz -a ' + opath + '/tmp_mean.nii.gz -b ' + opath + """/tmp_std.nii.gz -expr 'a/b'"""
    run(cmd)

    # print raw data
    pdf = montage(fpath, 'BOLD contrast', 
                         'gray', None, 0.75, filename, pdf)

    # calculate FD using default head radius of 50 mm
    pdf = compute_FD(opath + '/tmp_motion.1D', filename, pdf, 50)

    # plot SFNR
    pdf = montage(opath + '/tmp_sfnr.nii.gz', 'SFNR',
                                              'hot', None, 0.75, filename, pdf)

    # plot spectra
    # pdf = mean_PSD(opath + '/tmp_mcorr.nii.gz', 
    #                opath + '/tmp_mask.nii.gz', filename, pdf)

    # plot correlation statistics
    # pdf = mean_correlation(opath + '/tmp_mcorr.nii.gz', 
    #                        opath + '/tmp_mask.nii.gz', filename, pdf)

    # plot abnormalities
    pdf = find_fmri_spikes(fpath, filename, pdf)

    # clean up all temporary files
    run('rm ' + opath + '/tmp*')

    return pdf

def intensity_volume_qc(fpath, outputdir, pdf, name):
    """
    This prints a montage of the intensity volume
    """
    filename = os.path.basename(fpath)
    pdf = montage(fpath, name, 'gray', None, 0.5, filename, pdf)
    return pdf

def t1_qc(fpath, outputdir, pdf):
    intensity_volume_qc(fpath, outputdir, pdf, 'T1-contrast')

def pd_qc(fpath, outputdir, pdf):
    intensity_volume_qc(fpath, outputdir, pdf, 'PD-contrast')

def t2_qc(fpath, outputdir, pdf):
    intensity_volume_qc(fpath, outputdir, pdf, 'T2-contrast')

def dti_qc(fpath, outputdir, pdf, subject_type='human'):
    """
    This prints a montage of the raw T1 image, for great justice.
    """
    filename = os.path.basename(fpath)
 
    # print coverage
    pdf = montage(fpath, 'B0 Contrast', 
                         'gray', None, 0.5, filename, pdf)

    # print all directions
    pdf = montage_dti(fpath, filename, pdf, subject_type)

    # print all slice-wise spike artifacts
    pdf = find_dti_spikes(fpath, filename, pdf, subject_type, 5)

    return pdf

def bounding_box(filename):
    """
    Finds a box that only includes all nonzero voxels in a 3D image. Output box
    is represented as 3 x 2 numpy array with rows denoting x, y, z, and columns
    denoting stand and end slices.

    Usage:
        box = bounding_box(filename)
    """

    # find 3D bounding box
    box = np.zeros((3,2))  # init bounding box
    flag = 0  # switch to ascending

    for i, dim in enumerate(filename.shape): # loop through (x, y, z)

        # ascending search
        while flag == 0:
            for dim_test in np.arange(dim):

                # get sum of all values in each slice
                if i == 0:
                    test = np.sum(filename[dim_test, :, :])
                elif i == 1:
                    test = np.sum(filename[:, dim_test, :])
                elif i == 2:
                    test = np.sum(filename[:, :, dim_test])

                if test >= 1:  # if slice is nonzero, set starting bound
                    box[i, 0] = dim_test
                    flag = 1  # switch to descending
                    break  # get us out of this nested nonsense

        # descending search
        while flag == 1:
            for dim_test in np.arange(dim):
                
                dim_test = dim-dim_test - 1  # we have to reverse things

                # get sum of all values in each slice
                if i == 0:
                    test = np.sum(filename[dim_test, :, :])
                elif i == 1:
                    test = np.sum(filename[:, dim_test, :])
                elif i == 2:
                    test = np.sum(filename[:, :, dim_test])

                if test >= 1:  # if slice is nonzero, set ending bound
                    box[i, 1] = dim_test
                    flag = 0  # switch to ascending 
                    break  # get us out of this nested nonsense

    return box

def montage(image, name, cmaptype, minval, maxval, filename, pdf):
    """
    Creates a montage of images displaying a image set on top of a grayscale 
    image.

    Generally, this will be used to plot an image (of type 'name') that was
    generated from the original file 'filename'. So if we had an SNR map
    'SNR.nii.gz' from 'fMRI.nii.gz', we would submit everything to montage
    as so:

        montage('SNR.nii.gz', 'SNR', 'EPI.nii.gz', pdf)

    Usage:
        montage(image, name, filename, pdf)

        image    -- submitted image file name
        name     -- name of the printout (e.g, SNR map, t-stats, etc.)
        cmaptype -- 'redblue', 'hot', or 'gray'.
        minval   -- colormap minimum value as a % (None == 'auto')
        maxval   -- colormap maximum value as a % (None == 'auto')
        filename -- qc image file name  
        pdf      -- PDF object to save the figure to
    """

    # hard coded
    steps = 25
    box = None

    # input checks
    image = str(image)

    # grab the image folder
    opath = os.path.dirname(image)

    # load in the daterbytes
    output = str(image)
    image = nib.load(image).get_data()

    # if image is 4D, only keep the first time-point
    if len(image.shape) > 3:
        image = image[:, :, :, 0]

    # reorient the data to radiological (does this generalize?)
    image = np.transpose(image, (2,0,1))
    image = np.rot90(image, 2)

    if box == None: # if we didn't get a submitted bounding box
        box = bounding_box(image) # get the image bounds
    elif box.shape != (3,2): # if we did, ensure it is the right shape
        error('*** Submitted bounding box is not the correct shape! ***')
        error('***     It should be (3,2).                          ***')
        raise ValueError

    # crop data to bounded size
    image = image[box[0,0]:box[0,1], box[1,0]:box[1,1], box[2,0]:box[2,1]]

    # colormapping -- set value
    if cmaptype == 'redblue':
        cmap = plt.cm.RdBu_r 
    elif cmaptype == 'hot':
        cmap = plt.cm.OrRd
    elif cmaptype == 'gray':
        cmap = plt.cm.gray
    else:
        debug('No colormap supplied, default = greyscale.')
        cmap = plt.cm.gray

    # colormapping -- set range
    if minval == None:
        minval = np.min(image)
    else:
        minval = np.min(image) + ((np.max(image) - np.min(image)) * minval)

    if maxval == None:
        maxval = np.max(image)
    else:
        maxval = np.max(image) * maxval

    cmap.set_bad('g', 0)  # value for transparent pixels in the overlay 

    # I changed this to always work in the coronal plane...
    steps = np.round(np.linspace(0,np.shape(image)[0]-1,25))

    # init the figure, looping through each step
    fig, axes = plt.subplots(nrows=5, ncols=5, facecolor='white')
    for i, ax in enumerate(axes.flat):
        im = ax.imshow(image[steps[i], :, :], cmap=cmap, 
                                interpolation='nearest', 
                                vmin=minval, vmax=maxval)
        ax.set_frame_on(False)  # clean up unnecessary detail
        ax.axes.get_xaxis().set_visible(False)
        ax.axes.get_yaxis().set_visible(False)
        #ax.set_title(str(int(steps[i])))
        # step = step + stepsize  # iterate through the steps

    fig.subplots_adjust(right=0.8)
    cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
    cb = fig.colorbar(im, cax=cbar_ax)
    cb.set_label(name, labelpad=0, y=0.5)
    fig.suptitle(filename + '\n' + name, size=10)

    fig.savefig(pdf, format='pdf')
    plt.close()

    return pdf

def montage_dti(image, filename, pdf, subject_type):

    """
    Creates a montage of images displaying each DTI acquisition direction from
    a single central slice.

    For simplicity, most options from 'montage' are hard-coded here.

    Usage:
        montage(image, name, filename, pdf)

        image    -- submitted image file name
        name     -- name of the printout (e.g, SNR map, t-stats, etc.)
        filename -- qc image file name  
        pdf      -- PDF object to save the figure to
        subject_type -- 'human' or 'phantom'

    """

    image = str(image)             # input checks
    opath = os.path.dirname(image) # grab the image folder

    # load in the daterbytes
    output = str(image)
    image = nib.load(image).get_data()

    # reorient the data to radiological, one TR at a time
    for i in np.arange(image.shape[3]):

        if i == 0:
            newimage = np.transpose(image[:, :, :, i], (2,0,1))
            newimage = np.rot90(newimage, 2)

        elif i == 1:
            tmpimage = np.transpose(image[:, :, :, i], (2,0,1))
            tmpimage = np.rot90(tmpimage, 2)
            newimage = np.concatenate((newimage[...,np.newaxis], 
                                       tmpimage[...,np.newaxis]), axis=3)
        
        else:
            tmpimage = np.transpose(image[:, :, :, i], (2,0,1))
            tmpimage = np.rot90(tmpimage, 2)
            newimage = np.concatenate((newimage, 
                                       tmpimage[...,np.newaxis]), axis=3)

    image = copy(newimage)

    cmap = plt.cm.gray
    cmap.set_bad('g', 0)  # value for transparent pixels in the overlay 

    # find the middle slice
    if subject_type == 'human':
        midslice = np.floor((image.shape[2]-1)/2)
    elif subject_type == 'phantom':
        midslice = np.floor((image.shape[0]-1)/2)

    # init the figure, looping through each step
    fig, axes = plt.subplots(nrows=8, ncols=9, facecolor='white')
    for i, ax in enumerate(axes.flat):

        if i < image.shape[3]:

            if subject_type == 'human':
                im = ax.imshow(image[:, :, midslice, i], cmap=cmap, 
                                           interpolation='nearest')
            elif subject_type == 'phantom':
                im = ax.imshow(image[midslice, :, :, i], cmap=cmap, 
                                           interpolation='nearest')

            ax.set_frame_on(False)  # clean up unnecessary detail
            ax.axes.get_xaxis().set_visible(False)
            ax.axes.get_yaxis().set_visible(False)
            #ax.set_title(str(int(i+1)))

        # removes extra axes from plot
        else:
            ax.set_axis_off()

    fig.subplots_adjust(right=0.8)
    cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
    cb = fig.colorbar(im, cax=cbar_ax)
    cb.set_label('Anisotropy', labelpad=0, y=0.5)
    fig.suptitle(filename + '\n' + 'DTI', size=10)

    fig.savefig(pdf, format='pdf')
    plt.close()

    return pdf

def find_dti_spikes(image, filename, pdf, subject_type, n_b0):

    """
    Plots, for each axial slice, the mean instensity over all encoding
    directions. Strong deviations are an indication of the presence of spike
    noise.

    Usage:
        find_dti_spikes(image, filename, pdf)

        image    -- submitted image file name
        filename -- qc image file name  
        pdf      -- PDF object to save the figure to
        subject_type -- 'human' or 'phantom'
        n_b0     -- number of b0 images at beginning.

    """

    image = str(image)             # input checks
    opath = os.path.dirname(image) # grab the image folder

    # load in the daterbytes
    output = str(image)
    image = nib.load(image).get_data()

    # reorient the data to radiological, one TR at a time
    for i in np.arange(image.shape[3]):

        if i == 0:
            newimage = np.transpose(image[:, :, :, i], (2,0,1))
            newimage = np.rot90(newimage, 2)

        elif i == 1:
            tmpimage = np.transpose(image[:, :, :, i], (2,0,1))
            tmpimage = np.rot90(tmpimage, 2)
            newimage = np.concatenate((newimage[...,np.newaxis], 
                                       tmpimage[...,np.newaxis]), axis=3)
        
        else:
            tmpimage = np.transpose(image[:, :, :, i], (2,0,1))
            tmpimage = np.rot90(tmpimage, 2)
            newimage = np.concatenate((newimage, 
                                       tmpimage[...,np.newaxis]), axis=3)

    image = copy(newimage)

    x = image.shape[1]
    y = image.shape[2]

    # cmap = plt.cm.gray
    # cmap.set_bad('g', 0)  # value for transparent pixels in the overlay 

    # init the figure, looping through each step
    if subject_type == 'human':
        fig, axes = plt.subplots(nrows=8, ncols=9, facecolor='white')
    elif subject_type == 'phantom':
        fig, axes = plt.subplots(nrows=3, ncols=3, facecolor='white')

    for i, ax in enumerate(axes.flat):
    # for each axial slice
    #for i in np.arange(image.shape[0]):
        if i < image.shape[0]:

            vector_mean = np.array([])
            vector_std = np.array([])

            # find the mean, STD, of each dir and concatenate w. vector
            for j in np.arange(image.shape[3]):

                # this is if we want a subset of the image
                sample = image[i, np.round(x*0.25):np.round(x*0.75), 
                                  np.round(y*0.25):np.round(y*0.75), j]

                # this is if we want to use the whole image
                # sample = image[i, :, :, j] 

                mean = np.mean(sample)
                std = np.std(sample)

                if j == 0:
                    vector_mean = copy(mean)
                    vector_std = copy(std)
                else:
                    vector_mean = np.hstack((vector_mean, mean))
                    vector_std = np.hstack((vector_std, std))

                # #ax.set_title(str(int(i+1)))

            # crop out b0 images
            vector_mean = vector_mean[n_b0:]
            vector_std = vector_std[n_b0:]

            #fig.subplots_adjust(right=0.8)
            #cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
            #cb = fig.colorbar(im, cax=cbar_ax)
            #cb.set_label('Anisotropy', labelpad=0, y=0.5)
            ax.plot(vector_mean, color='black')
            ax.fill_between(np.arange(len(vector_std)), 
                             vector_mean-vector_std, 
                             vector_mean+vector_std, alpha=0.5, 
                                                     color='black')

            ax.set_frame_on(False)  # clean up unnecessary detail
            ax.axes.get_xaxis().set_visible(False)
            ax.axes.get_yaxis().set_visible(False)
            ax.set_title('slice: ' + str(i+1), size=8)
        else:
            ax.set_axis_off()

    plt.suptitle(filename + '\n' + 'DTI Slice/TR Wise Abnormalities', size=10)
    plt.savefig(pdf, format='pdf')
    plt.close()

    return pdf

def find_fmri_spikes(image, filename, pdf):

    """
    Plots, for each axial slice, the mean instensity over all encoding
    directions. Strong deviations are an indication of the presence of spike
    noise.

    Usage:
        find_fmri_spikes(image, filename, pdf)

        image    -- submitted image file name
        filename -- qc image file name  
        pdf      -- PDF object to save the figure to

    """

    image = str(image)             # input checks
    opath = os.path.dirname(image) # grab the image folder

    # load in the daterbytes
    output = str(image)
    image = nib.load(image).get_data()

    # reorient the data to radiological, one TR at a time
    for i in np.arange(image.shape[3]):

        if i == 0:
            newimage = np.transpose(image[:, :, :, i], (2,0,1))
            newimage = np.rot90(newimage, 2)

        elif i == 1:
            tmpimage = np.transpose(image[:, :, :, i], (2,0,1))
            tmpimage = np.rot90(tmpimage, 2)
            newimage = np.concatenate((newimage[...,np.newaxis], 
                                       tmpimage[...,np.newaxis]), axis=3)
        
        else:
            tmpimage = np.transpose(image[:, :, :, i], (2,0,1))
            tmpimage = np.rot90(tmpimage, 2)
            newimage = np.concatenate((newimage, 
                                       tmpimage[...,np.newaxis]), axis=3)

    image = copy(newimage)

    x = image.shape[1]
    y = image.shape[2]

    # cmap = plt.cm.gray
    # cmap.set_bad('g', 0)  # value for transparent pixels in the overlay 

    # init the figure, looping through each step
    fig, axes = plt.subplots(nrows=6, ncols=6, facecolor='white')
    for i, ax in enumerate(axes.flat):

    # for each axial slice
    #for i in np.arange(image.shape[0]):
        if i < image.shape[0]:

            vector_mean = np.array([])
            vector_std = np.array([])

            # find the mean, STD, of each dir and concatenate w. vector
            for j in np.arange(image.shape[3]):

                # this is if we want a subset of the image
                sample = image[i, np.round(x*0.25):np.round(x*0.75), 
                                 np.round(y*0.25):np.round(y*0.75), j]

                # this is if we want to use the whole image
                # sample = image[i, :, :, j] 

                mean = np.mean(sample)
                std = np.std(sample)

                if j == 0:
                    vector_mean = copy(mean)
                    vector_std = copy(std)
                else:
                    vector_mean = np.hstack((vector_mean, mean))
                    vector_std = np.hstack((vector_std, std))

                # #ax.set_title(str(int(i+1)))

            #fig.subplots_adjust(right=0.8)
            #cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
            #cb = fig.colorbar(im, cax=cbar_ax)
            #cb.set_label('Anisotropy', labelpad=0, y=0.5)
            ax.plot(vector_mean, color='black')
            ax.fill_between(np.arange(len(vector_std)), 
                             vector_mean-vector_std, 
                             vector_mean+vector_std, alpha=0.5, 
                                                     color='black')

            ax.set_frame_on(False)  # clean up unnecessary detail
            ax.axes.get_xaxis().set_visible(False)
            ax.axes.get_yaxis().set_visible(False)
            ax.set_title('slice: ' + str(i+1), size=8)
        else:
            ax.set_axis_off()

    plt.suptitle(filename + '\n' + 'fMRI Slice/TR Abnormalities', size=10)
    plt.savefig(pdf, format='pdf')
    plt.close()

    return pdf

def load_masked_data(func, mask):
    """
    Accepts 'functional.nii.gz' and 'mask.nii.gz', and returns a voxels x
    timepoints matrix of the functional data in non-zero mask locations. 
    """
    func = nib.load(func).get_data()
    mask = nib.load(mask).get_data()

    mask = mask.reshape(mask.shape[0]*mask.shape[1]*mask.shape[2])
    func = func.reshape(func.shape[0]*func.shape[1]*func.shape[2],
                                                    func.shape[3])

    # find within-brain timeseries
    idx = np.where(mask > 0)[0]
    func = func[idx, :]

    return func

def mean_correlation(func, mask, filename, pdf):
    """
    Calculates a correlation matrix of all timeseries within the submitted 
    mask, along with the mean correlation value, and plots this information in
    the submitted pdf.
    """
    # load data
    func = load_masked_data(func, mask)

    # take a random 10% of the data
    idx = np.random.choice(func.shape[0], func.shape[0]/10, replace=False)
    func = func[idx, :]

    # find correlation matrix
    func = sp.corrcoef(func, rowvar=1)

    # mean, standard deviation of flattened array
    mean = np.mean(func, axis=None)
    std = np.std(func, axis=None)

    # plot correlation matrix
    im = plt.imshow(func, cmap=plt.cm.RdBu_r, interpolation='nearest', 
                                                      vmin=-1, vmax=1)
    # clean up unnecessary detail
    #plt.set_frame_on(False)
    #plt.axes.get_xaxis().set_visible(False)
    #plt.axes.get_yaxis().set_visible(False)

    plt.xlabel('Voxel')
    plt.ylabel('Voxel')

    # add stats
    cb = plt.colorbar(im)
    cb.set_label('Correlation (r)', labelpad=0, y=0.5)
    plt.title(filename + '\nWhole-Brain Correlaion (r)\n' +
                         ' Mean = ' + str(mean) + ' SD = ' + str(std), size=10)

    # print to pdf
    plt.savefig(pdf, format='pdf')
    plt.close()

    return pdf

def mean_PSD(func, mask, filename, pdf):
    """
    Calculates the mean normalized spectra across the entire brain 
    and plots them in the submitted pdf.
    """
    func = load_masked_data(func, mask)

    # find peridogram
    func = sig.detrend(func, type='linear')
    func = sig.periodogram(func, fs=0.5, return_onesided=True, 
                                            scaling='density')

    freq = func[0]
    func = func[1]

    # compute std, sem, mean.
    std = np.nanstd(func, axis=0)
    #sem = std / np.repeat(np.sqrt(func.shape[0]), func.shape[1])
    mean = np.nanmean(func, axis=0)

    # plot
    plt.plot(freq, mean, color='black', linewidth=2)
    #plt.loglog(freq, -mean, color='black', linewidth=2)
    plt.fill_between(freq, mean + std, mean, color='black', alpha=0.5)
    plt.fill_between(freq, mean - std, mean, color='black', alpha=0.5)
    # plt.plot(freq, mean + sem, color='black', linestyle='-.', 
    #                                             linewidth=0.5)
    #plt.plot(freq, mean - sem, color='black', linestyle='-.',                                        linewidth=0.5)
    plt.title(filename + '\nWhole-Brain Spectra Mean, SD (shaded)', size=10)
    plt.xlabel('Frequency (Hz)')
    plt.ylabel('Power')

    plt.ylim(0, max(std))   
    plt.savefig(pdf, format='pdf')
    plt.close()

    return pdf

def compute_FD(f, filename, pdf, head_radius=50):
    """
    Computes FD vector from AFNI 3dVolreg 6-param .1D file read using
    numpy's genfromtxt.

        f is a string pointing to the .1D file.
        head_radius is an integer in mm.

    1) Convert degrees (roll, pitch, yaw) to mm using head radius
    2) Takes the same of the absoloute first difference
    Returns a vector of mm/TR.
    """
    
    # framewise displacement
    f = np.genfromtxt(f)
    f[:,0] = np.radians(f[:,0]) * head_radius
    f[:,1] = np.radians(f[:,1]) * head_radius
    f[:,2] = np.radians(f[:,2]) * head_radius
    f = np.abs(np.diff(f, n=1, axis=0))
    f = np.sum(f, axis=1)
    
    # time axis
    t = np.arange(len(f))

    # plot
    plt.plot(t, f.T, lw=1, color='black')
    plt.axhline(y=0.5, xmin=0, xmax=len(t), color='r')
    plt.xlim((-3, len(t) + 3)) # this is in TRs
    plt.ylim(0, 2) # this is in mm/TRs
    plt.xlabel('TR')
    plt.ylabel('Framewise Displacement (mm/TR)')
    plt.title(filename + '\nHead Motion', size=10)
    plt.savefig(pdf, format='pdf')
    plt.close()

    return pdf

def check_n_trs(fpath):
    """
    Returns the number of TRs for an input file. If the file is 3D, we also
    return 1.
    """
    data = nib.load(fpath)

    try:
        ntrs = data.shape[3]
    except:
        ntrs = 1

    return ntrs

qc_handlers = {   # map from tag to QC function 
        "T1"          : t1_qc,
        "T2"          : t2_qc,
        "PD"          : pd_qc,
        "PDT2"        : ignore,
        "RST"         : fmri_qc, 
        "OBS"         : fmri_qc, 
        "IMI"         : fmri_qc, 
        "NBK"         : fmri_qc, 
        "EMP"         : fmri_qc, 
        "DTI"         : dti_qc, 
        "DTI60-1000"  : dti_qc, 
        "DTI60-b1000" : dti_qc, 
	"DTI33-1000"  : dti_qc, 
	"DTI33-b1000" : dti_qc, 
        "DTI33-3000"  : dti_qc, 
        "DTI33-b3000" : dti_qc, 
        "DTI33-4500"  : dti_qc, 
        "DTI33-b4500" : dti_qc, 
}

def main():
    """
    This spits out our QCed data
    """
    global VERBOSE
    global DEBUG
    global DRYRUN

    arguments = docopt(__doc__)
    datadir   = arguments['--datadir']
    qcdir     = arguments['--qcdir']
    VERBOSE   = arguments['--verbose']
    DEBUG     = arguments['--debug']
    DRYRUN    = arguments['--dry-run']

    timepoint_glob = '{datadir}/nii/*'.format(datadir=datadir)

    for path in glob.glob(timepoint_glob): 
        timepoint = os.path.basename(path)

        # skip phantoms
        if 'PHA' in timepoint:
            pass
        else:
            verbose("QCing folder {}".format(path))
            qc_folder(path, timepoint, qcdir, qc_handlers) 

if __name__ == "__main__":
    main()
