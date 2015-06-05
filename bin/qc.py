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
import tempfile

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

def ignore(fpath, pdf):
    pass

def factors(n):    
    """
    Returns all factors of n.
    """    
    return set(reduce(list.__add__, 
                ([i, n//i] for i in range(1, int(n**0.5) + 1) if n % i == 0)))

def square_factors(fac, num):
    """
    Finds the two most square factors of a number from a list of factors.
    Factors returned with the smallest first.
    """
    candidates = []
    for x in fac:
        for y in fac:
            if x*y == num:
                candidates.append(abs(x-y))
    most_square = np.min(candidates)
    for x in fac:
        for y in fac:
            if x*y == num:
                if x-y == most_square:
                    factor = [x, y]
    if factor[0] > factor[1]:
        factor = factor[::-1]
    
    return factor

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
    flag = 0  # ascending

    for i, dim in enumerate(filename.shape): # loop through (x, y, z)

        # ascending search
        while flag == 0:
            for dim_test in np.arange(dim):

                # get sum of all values in each slice
                if i == 0:   test = np.sum(filename[dim_test, :, :])
                elif i == 1: test = np.sum(filename[:, dim_test, :])
                elif i == 2: test = np.sum(filename[:, :, dim_test])

                # if slice is nonzero, set starting bound, switch to descending
                if test >= 1:
                    box[i, 0] = dim_test
                    flag = 1
                    break

        # descending search
        while flag == 1:
            for dim_test in np.arange(dim):
                
                dim_test = dim-dim_test - 1  # we have to reverse things

                # get sum of all values in each slice
                if i == 0:   test = np.sum(filename[dim_test, :, :])
                elif i == 1: test = np.sum(filename[:, dim_test, :])
                elif i == 2: test = np.sum(filename[:, :, dim_test])

                # if slice is nonzero, set ending bound, switch to ascending
                if test >= 1:
                    box[i, 1] = dim_test
                    flag = 0
                    break

    return box

def reorient_4d_image(image):
    """
    Reorients the data to radiological, one TR at a time
    """
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

    return image

def montage(image, name, filename, pdf, cmaptype='grey', mode='3d', minval=None, maxval=None, box=None):
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
        mode     -- '3d' (prints through space) or '4d' (prints through time)
        filename -- qc image file name  
        pdf      -- PDF object to save the figure to
        box      -- a (3,2) tuple that describes the start and end voxel 
                    for x, y, and z, respectively. If None, we find it ourselves.
    """
    image = str(image) # input checks
    opath = os.path.dirname(image) # grab the image folder
    output = str(image)
    image = nib.load(image).get_data() # load in the daterbytes

    if mode == '3d':  
        if len(image.shape) > 3: # if image is 4D, only keep the first time-point
            image = image[:, :, :, 0]

        image = np.transpose(image, (2,0,1))
        image = np.rot90(image, 2)
        steps = np.round(np.linspace(0,np.shape(image)[0]-2, 36)) # coronal plane
        factor = 6

        # use bounding box (submitted or found) to crop extra-brain regions
        if box == None:
            box = bounding_box(image) # get the image bounds
        elif box.shape != (3,2): # if we did, ensure it is the right shape
            error('ERROR: Bounding box should have shape = (3,2).')
            raise ValueError
        image = image[box[0,0]:box[0,1], box[1,0]:box[1,1], box[2,0]:box[2,1]]

    if mode == '4d':
        image = reorient_4d_image(image)
        midslice = np.floor((image.shape[2]-1)/2) # print a single plane across all slices 
        factor = np.ceil(np.sqrt(image.shape[3])) # print all timepoints
        factor = factor.astype(int)

    # colormapping -- set value
    if cmaptype == 'redblue': cmap = plt.cm.RdBu_r 
    elif cmaptype == 'hot': cmap = plt.cm.OrRd
    elif cmaptype == 'gray': cmap = plt.cm.gray
    else:
        debug('No valid colormap supplied, default = greyscale.')
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

    fig, axes = plt.subplots(nrows=factor, ncols=factor, facecolor='white')
    for i, ax in enumerate(axes.flat):

        if mode == '3d':
            im = ax.imshow(image[steps[i], :, :], cmap=cmap, interpolation='nearest', vmin=minval, vmax=maxval)
            ax.set_frame_on(False) 
            ax.axes.get_xaxis().set_visible(False)
            ax.axes.get_yaxis().set_visible(False)

        elif mode == '4d' and i < image.shape[3]:
            im = ax.imshow(image[:, :, midslice, i], cmap=cmap, interpolation='nearest')
            ax.set_frame_on(False) 
            ax.axes.get_xaxis().set_visible(False)
            ax.axes.get_yaxis().set_visible(False)

        elif mode == '4d' and i >= image.shape[3]:
            ax.set_axis_off() # removes extra axes from plot

    fig.subplots_adjust(right=0.8)
    cbar_ax = fig.add_axes([0.85, 0.15, 0.05, 0.7])
    cb = fig.colorbar(im, cax=cbar_ax)
    #cb.set_label(name, labelpad=0, y=0.5)
    fig.suptitle(filename + '\n' + name, size=10)

    fig.savefig(pdf, format='pdf')
    plt.close()

    return pdf

def find_epi_spikes(image, filename, pdf, bvec=None):

    """
    Plots, for each axial slice, the mean instensity over all TRs. 
    Strong deviations are an indication of the presence of spike
    noise.

    If bvec is supplied, we remove all time points that are 0 in the bvec
    vector.

    Usage:
        find_epi_spikes(image, filename, pdf)

        image    -- submitted image file name
        filename -- qc image file name  
        pdf      -- PDF object to save the figure to
        bvec     -- numpy array of bvecs (for finding direction = 0)

    """

    image = str(image)             # input checks
    opath = os.path.dirname(image) # grab the image folder

    # load in the daterbytes
    output = str(image)
    image = nib.load(image).get_data()
    image = reorient_4d_image(image)

    x = image.shape[1]
    y = image.shape[2]
    z = image.shape[0]
    t = image.shape[3]

    # find the most square set of factors for n_trs
    factor = np.ceil(np.sqrt(z))
    factor = factor.astype(int)

    fig, axes = plt.subplots(nrows=factor, ncols=factor, facecolor='white')

    # sets the bounds of the image
    c1 = np.round(x*0.25)
    c2 = np.round(x*0.75)

    # for each axial slice
    for i, ax in enumerate(axes.flat):
        if i < z:

            v_mean = np.array([])
            v_sd = np.array([])

            # find the mean, STD, of each dir and concatenate w. vector
            for j in np.arange(t):

                # gives us a subset of the image
                sample = image[i, c1:c2, c1:c2, j]
                mean = np.mean(sample)
                sd = np.std(sample)

                if j == 0:
                    v_mean = copy(mean)
                    v_sd = copy(sd)
                else:
                    v_mean = np.hstack((v_mean, mean))
                    v_sd = np.hstack((v_sd, sd))

            # crop out b0 images
            if bvec != None:
                idx = np.where(bvec != 0)[0]
                v_mean = v_mean[idx]
                v_sd = v_sd[idx]
                v_t = np.arange(len(idx))
            else:
                v_t = np.arange(t)

            ax.plot(v_mean, color='black')
            ax.fill_between(v_t, v_mean-v_sd, v_mean+v_sd, alpha=0.5, color='black')
            ax.set_frame_on(False)
            ax.axes.get_xaxis().set_visible(False)
            ax.axes.get_yaxis().set_visible(False)
        else:
            ax.set_axis_off()

    plt.suptitle(filename + '\n' + 'DTI Slice/TR Wise Abnormalities', size=10)
    plt.savefig(pdf, format='pdf')
    plt.close()

    return pdf

def fmri_plots(func, mask, f, filename, pdf):
    """
    Calculates and plots:
         + Mean and SD of normalized spectra across brain.
         + Framewise displacement (mm/TR) of head motion.
         + Mean correlation from 10% of the in-brain voxels.
         + EMPTY ADD KEWL PLOT HERE PLZ.

    """
    ##############################################################################
    # spectra
    plt.subplot(2,2,1)
    func = load_masked_data(func, mask)
    spec = sig.detrend(func, type='linear')
    spec = sig.periodogram(spec, fs=0.5, return_onesided=True, scaling='density')
    freq = spec[0]
    spec = spec[1]
    sd = np.nanstd(spec, axis=0)
    mean = np.nanmean(spec, axis=0)

    plt.plot(freq, mean, color='black', linewidth=2)
    plt.plot(freq, mean + sd, color='black', linestyle='-.', linewidth=0.5)
    plt.plot(freq, mean - sd, color='black', linestyle='-.', linewidth=0.5)
    plt.title('Whole-brain spectra mean, SD', size=6)
    plt.xticks(size=6)
    plt.yticks(size=6)
    plt.xlabel('Frequency (Hz)', size=6)
    plt.ylabel('Power', size=6)
    plt.xticks([])

    ##############################################################################
    # framewise displacement
    plt.subplot(2,2,2)
    f = np.genfromtxt(f)
    f[:,0] = np.radians(f[:,0]) * 50 # 50 = head radius, need not be constant.
    f[:,1] = np.radians(f[:,1]) * 50 # 50 = head radius, need not be constant.
    f[:,2] = np.radians(f[:,2]) * 50 # 50 = head radius, need not be constant.
    f = np.abs(np.diff(f, n=1, axis=0))
    f = np.sum(f, axis=1)
    t = np.arange(len(f))

    plt.plot(t, f.T, lw=1, color='black')
    plt.axhline(y=0.5, xmin=0, xmax=len(t), color='r')
    plt.xlim((-3, len(t) + 3)) # this is in TRs
    plt.ylim(0, 2) # this is in mm/TRs
    plt.xticks(size=6)
    plt.yticks(size=6)
    plt.xlabel('TR', size=6)
    plt.ylabel('Framewise displacement (mm/TR)', size=6)
    plt.title('Head motion', size=6)

    ##############################################################################
    # whole brain correlation
    plt.subplot(2,2,3)
    idx = np.random.choice(func.shape[0], func.shape[0]/10, replace=False)
    corr = func[idx, :]
    corr = sp.corrcoef(corr, rowvar=1)
    mean = np.mean(corr, axis=None)
    std = np.std(corr, axis=None)

    im = plt.imshow(corr, cmap=plt.cm.RdBu_r, interpolation='nearest', vmin=-1, vmax=1)
    plt.xlabel('Voxel', size=6)
    plt.ylabel('Voxel', size=6)
    plt.xticks([])
    plt.yticks([])
    cb = plt.colorbar(im)
    cb.set_label('Correlation (r)', labelpad=0, y=0.5, size=6)
    for tick in cb.ax.get_yticklabels():
        tick.set_fontsize(6)
    plt.title('Whole-brain r mean={}, SD={}'.format(str(mean), str(std)), size=6)

    ##############################################################################
    # add a final plot?
    plt.suptitle(filename)
    plt.savefig(pdf, format='pdf')
    plt.close()

    return pdf

def fmri_qc(fpath, pdf):
    """
    This takes an input image, motion corrects, and generates a brain mask. 
    It then calculates a signal to noise ratio map and framewise displacement
    plot for the file.
    """
    # if the number of TRs is too little, we skip the pipeline
    ntrs = check_n_trs(fpath)

    if ntrs < 20:
        return pdf

    filename = os.path.basename(fpath)
    tmpdir = tempfile.mkdtemp(prefix='qc-')

    run('3dvolreg -prefix {t}/mcorr.nii.gz -twopass -twoblur 3 -Fourier -1Dfile {t}/motion.1D {}'.format(t=tmpdir, fpath))
    run('3dTstat -prefix {t}/mean.nii.gz {t}/mcorr.nii.gz'.format(t=tmpdir))
    run('3dAutomask -prefix {t}/mask.nii.gz -clfrac 0.5 -peels 3 {t}/mean.nii.gz'.format(t=tmpdir))
    run('3dTstat -prefix {t}/std.nii.gz  -stdev {t}/mcorr.nii.gz'.format(t=tmpdir))
    run("""3dcalc -prefix {t}/sfnr.nii.gz -a {t}/mean.nii.gz -b {t}/std.nii.gz -expr 'a/b'""".format(t=tmpdir))

    pdf = montage(fpath, 'BOLD-contrast', filename, pdf, maxval=0.75)
    pdf = fmri_plots('{t}/mcorr.nii.gz'.format(t=tmpdir), '{t}/mask.nii.gz'.format(t=tmpdir), '{t}/motion.1D'.format(t=tmpdir), filename, pdf)
    pdf = montage('{t}/sfnr.nii.gz'.format(t=tmpdir), 'SFNR', filename, pdf, cmaptype='hot', maxval=0.75)
    pdf = find_epi_spikes(fpath, filename, pdf)

    run('rm r {}'.format(tmpdir))

    return pdf

def t1_qc(fpath, pdf):
    pdf = montage(fpath, 'T1-contrast', os.path.basename(fpath), pdf, maxval=0.25)
    return pdf

def pd_qc(fpath, pdf):
    pdf = montage(fpath, 'PD-contrast', os.path.basename(fpath), pdf, maxval=0.4)
    return pdf

def t2_qc(fpath, pdf):
    pdf = montage(fpath, 'T2-contrast', os.path.basename(fpath), pdf, maxval=0.5)
    return pdf

def flair_qc(fpath, pdf):
    pdf = montage(fpath, 'FLAIR-contrast', os.path.basename(fpath), pdf, maxval=0.3)
    return pdf

def dti_qc(fpath, pdf):
    """
    Runs the QC pipeline on the DTI inputs. We use the BVEC (not BVAL)
    file to find B0 images (in some scans, mid-sequence B0s are coded
    as non-B0s for some reason, so the 0-direction locations in BVEC
    seem to be the safer choice).
    """
    filename = os.path.basename(fpath)
    directory = os.path.dirname(fpath)

    # load in bvec file
    bvec = filename.split('.')
    try:
        bvec.remove('gz')
    except:
        pass
    try:
        bvec.remove('nii')
    except:
        pass

    bvec = np.genfromtxt(os.path.join(directory, ".".join(bvec) + '.bvec'))
    bvec = np.sum(bvec, axis=0)

    pdf = montage(fpath, 'B0-contrast', filename, pdf, maxval=0.25)
    pdf = montage(fpath, 'DTI Directions', filename, pdf, mode='4d', maxval=0.25)
    pdf = find_epi_spikes(fpath, filename, pdf, bvec)

    return pdf

def qc_folder(scanpath, prefix, qcdir, QC_HANDLERS):
    """
    QC all the images in a folder (scanpath).

    Outputs PDF and other files to outputdir. All files named startng with
    prefix.
    """

    qcdir = dm.utils.define_folder(qcdir)
    pdffile = os.path.join(qcdir, 'qc_' + prefix + '.pdf')
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
        if tag not in QC_HANDLERS:
            log("QC hanlder for scan {} (tag {}) not found. Skipping.".format(fname, tag))
            continue
        QC_HANDLERS[tag](fname, pdf)

    # finally, close the pdf
    d = pdf.infodict()
    d['CreationDate'] = datetime.datetime.today()
    d['ModDate'] = datetime.datetime.today()
    pdf.close()

def main():
    """
    This spits out our QCed data
    """
    global VERBOSE
    global DEBUG
    global DRYRUN
    
    QC_HANDLERS = {   # map from tag to QC function 
            "T1"          : t1_qc,
            "T2"          : t2_qc,
            "PD"          : pd_qc,
            "PDT2"        : ignore,
            "FLAIR"       : flair_qc,
            "FMAP"        : ignore,
            "FMAP-6.5"    : ignore,
            "FMAP-8.5"    : ignore,
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
            qc_folder(path, timepoint, qcdir, QC_HANDLERS) 

if __name__ == "__main__":
    main()
