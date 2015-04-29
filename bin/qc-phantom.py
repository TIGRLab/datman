#!/usr/bin/env python
"""
This runs the QC on the ADNI, fMRI, and DTI data, respectively. Allows 
you to specify plotting of all sites concurrently or a single site. If a
number of time-points is specified, we submit those to each function.

Usage:
    qc-phantom.py [options] <project> <ntp> <sites>...

Arguments: 
    <sites>             List of sites to plot.
    <ntp>               Number of previous time points to plot. 
    <project>           Full path to the project directory containing data/.

Options:
    -v,--verbose             Verbose logging
    --debug                  Debug logging

DETAILS

    This program find phantom data (supported: ADNI, fBIRN fMRI, fBIRN DTI)
    and calcuates relevant statistics on them.

    This expects properly-formatted phantom tags:
        ADNI       -- PHA-ADN
        fBIRN fMRI -- PHA-fMR
        fBIRN DIT  -- PHA-DTI

    Each file is then sent through the appropriate analysis pipeline, if the
    outputs do not already exist. Finally, this compiles results of the last 
    n weeks into a plot that summarizes the data from the submitted sites.

DEPENDENCIES

    + matlab
    + afni

    This message is printed with the -h, --help flags.
"""

import os, sys
import time, datetime

import datman as dm
import dicom as dcm
from docopt import docopt
import tempfile

import numpy as np
import nibabel as nib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

VERBOSE = False
DRYRUN  = False
DEBUG   = False

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

def get_discrete_colormap(n, cmap):
    """
    Returns the submitted colormap and normalizer. Use like this...

    # make the scatter
    plot = ax.scatter(x, y, c=tag, s=np.random.randint(100,500,20), cmap=cmap, 
                                                                    norm=norm)

    # create a second axes for the colorbar
    ax2 = fig.add_axes([0.95, 0.1, 0.03, 0.8])
    cb = mpl.colorbar.ColorbarBase(ax2, cmap=cmap, 
                                        norm=norm, 
                                        spacing='proportional', 
                                        ticks=bounds, 
                                        boundaries=bounds, 
                                        format='%1i')
    """

    # extract all colors from colormap, set first color to be black
    cmaplist = [cmap(i) for i in range(cmap.N)]
    cmaplist[0] = (0, 0, 0, 1.0)

    # create the new map witn n bins
    cmap = cmap.from_list('discrete-cmap', cmaplist, n)
    cmap = [cmap(i) for i in range(cmap.N)]

    # define bins and normalize
    # bounds = np.linspace(0, n, n+1)
    # norm = matplotlib.colors.BoundaryNorm(bounds, cmap.N)

    return cmap #, norm, bounds

def remove_region(data, i):
    """
    Removes the ROIs containing the value i from the data. 
    """
    x = data.shape[0]
    y = data.shape[1]

    data = data.reshape(x * y)
    idx = np.where(data == i)[0] 
    data[idx] = 0
    data = data.reshape(x, y)

    return data

def retain_n_segments(data, nseg):
    """
    This takes in a set of ROIs and returns the same set with only the top n
    largest segments. All of the other regions will be replaced with zeros.

    0 is treated as the background and is not considered.
    """
    # get the ROIs, create a size vector
    rois = filter(lambda x: x > 0, np.unique(data))
    sizes = np.zeros(len(rois))

    # find the size of each ROI
    for i, roi in enumerate(rois):
        sizes[i] = len(np.where(data == roi)[0])

    # sort smallest --> largest, find regions to remove
    idx = np.argsort(sizes)
    rois = np.array(rois)
    rois = rois[idx]
    idx = rois[0:-nseg]

    # remove regions
    for i in idx:
        data = remove_region(data, i)

    return data

def sample_centroids(data, radius=5):
    """
    Takes in a label file and places equally-sized disks of radius r at each
    ROIs centroid. This returns an ROI matrix with equally sized ROIs.
    """
    from skimage.draw import circle
    from skimage.measure import regionprops

    props = regionprops(data, intensity_image=None, cache=True)
    for prop in props:
        x = prop.centroid[0]
        y = prop.centroid[1]
        roi = data[x, y]

        # set region to be zero
        data = remove_region(data, roi)

        # place circle --  watch these indicies -- keep flipping)
        rr, cc = circle(y, x, 5, data.shape)
        data[cc, rr] = roi

    return data

def print_adni_qc(project, data, title):
    """
    Prints out the supplied ADNI phantom (masked?) to a QC folder for eyeballs.
    """
    # extract filename for title
    title = os.path.basename(title)

    maximum = np.max(data)
    plt.imshow(data, cmap=plt.cm.jet, interpolation='nearest',
                                      vmin=0.15*maximum, vmax=0.75*maximum)
    plt.colorbar()
    plt.title(os.path.basename(title), fontsize=8)
    plt.xticks([])
    plt.yticks([])
    plt.tight_layout()
    plt.savefig(os.path.join(project, 'qc/phantom/adni/{}.jpg'.format(title)))
    plt.close()

def find_adni_t1_vals(project, data, erosion=13):
    """
    Find the 5 ROIs of interest using the random walker algorithm [1]. Uses the
    image mean as the lower threshold, and 2x the mean as an upper threshold.

    Further, we find the 5 largest connected components, and erode these masks
    by `erosion` voxels. The mean of these eroded masks are used as our ADNI 
    samples and passed along for plotting.

    This also calculates the relevant T1 ratios: s2/s1, s3/s1, s4/s1, s5/s1.

    http://scikit-image.org/docs/dev/auto_examples

    [1] Random walks for image segmentation, Leo Grady, IEEE Trans. 
        Pattern Anal. Mach. Intell. 2006 Nov; 28(11):1768-83
    """
    from copy import copy
    from skimage.measure import label
    from skimage.segmentation import random_walker

    print(data)

    title = copy(data) # QC

    # convert data to LPI orientation
    tmpdir = tempfile.mkdtemp(prefix='adni-')
    os.system('3daxialize -prefix {}/adni-lpi.nii.gz -orient LPI {}'.format(
                                                               tmpdir, data))

    data = nib.load(os.path.join(tmpdir, 'adni-lpi.nii.gz')).get_data() # import
    os.system('rm -r {}'.format(tmpdir))

    data = data[:, :, data.shape[2]/2] # take central axial slice
    data = np.fliplr(np.rot90(data)) # rotate 90 deg --> flip l-r

    # random walker segmentation
    markers = np.zeros(data.shape, dtype=np.uint)
    markers[data < np.mean(data)] = 1
    markers[data > np.mean(data)*2] = 2
    labels = random_walker(data, markers, beta=10, mode='bf')

    # number labeled regions (convert mask to E[0,1])
    labels = label(labels, neighbors=8)

    # retain the largest 5 rois
    labels = retain_n_segments(labels, 5)

    # generate QC output
    mask = np.where(labels == 0)
    plot = copy(data)
    plot[mask] = 0
    print_adni_qc(project, plot, title)
    
    # find the central roi
    center = np.max(retain_n_segments(copy(labels), 1))

    # set rois to have the same sized centroid sample
    labels = sample_centroids(labels, 10)

    # find quadrants (start in bottom lh corner, moving counter-clockwise)
    x = labels.shape[1] / 2
    y = labels.shape[0] / 2
    
    q1 = labels[y:, 0:x]
    q2 = labels[y:, x:]
    q3 = labels[0:y, x:]
    q4 = labels[0:y, 0:x]

    # find the ball unique to each quadrant
    idx1 = np.setdiff1d(np.unique(q1), center)
    idx2 = np.setdiff1d(np.unique(q2), center)
    idx3 = np.setdiff1d(np.unique(q3), center)
    idx4 = np.setdiff1d(np.unique(q4), center)

    # reshape the data to 1D for the last bit
    x = data.shape[0]
    y = data.shape[1]
    data = data.reshape(x * y)
    labels = labels.reshape(x * y)

    # place mean intensity from each ROI into an raw_adni output array
    adni = np.zeros(9)

    idx = np.where(labels == idx1[1])[0]
    adni[0] = np.mean(data[idx])
    idx = np.where(labels == idx2[1])[0]
    adni[1] = np.mean(data[idx])
    idx = np.where(labels == idx3[1])[0]
    adni[2] = np.mean(data[idx])
    idx = np.where(labels == idx4[1])[0]
    adni[3] = np.mean(data[idx])
    idx = np.where(labels == np.array([center]))[0]
    adni[4] = np.mean(data[idx])

    # add in the ratios: s2/s1, s3/s1, s4/s1, s5/s1
    adni[5] = adni[1] / adni[0]
    adni[6] = adni[2] / adni[0]
    adni[7] = adni[3] / adni[0]
    adni[8] = adni[4] / adni[0]

    return adni

def find_fbirn_fmri_vals(base_path, subj, phantom):
    """
    This runs the spins_fbirn matlab code if required, and returns the output
    as a vector.
    """

    assets = os.getenv('DATMAN_ASSETS')

    if os.path.isfile(os.path.join(base_path, 'qc/phantom/fmri/', 
                                                   subj + '.csv')) == False:
        cmd = (r"addpath(genpath('{}')); compute_fbirn('{}','{}','{}')".format(
                                              assets, base_path, subj, phantom)) 
        os.system('matlab -nodisplay -nosplash -r "' + cmd + '"')

    fbirn = np.genfromtxt(os.path.join(
                          base_path, 'qc/phantom/fmri/', subj + '.csv'), 
                           delimiter=',',dtype=np.float, skip_header=1)
    fbirn = fbirn[1:]

    return fbirn

def get_scan_range(timearray):
    """
    Takes the week indicies from a time array and returns the total extent
    of time to plot (as not all sites will have data available for each week).

    l = the labels for the given time points
    """
    minimum = np.min(timearray[:,0])
    maximum = np.max(timearray[:,-1])

    # deal with cases where we've rolled over to a new year
    if maximum - minimum < 0:
        length = maximum + 52 - minimum + 1
        l1 = np.linspace(minimum, 52, 52-minimum+1)
        l2 = np.linspace(1, maximum, maximum)
        l = np.hstack((l1, l2))

    else:
        length = maximum - minimum + 1
        l = np.linspace(minimum, maximum, maximum-minimum+1)

    return l

def get_scatter_x(tp, l, timevector):
    """
    Determines the location of the datapoints on the x-axis across all sites
    with the timevector passed to it (timevector comes from timearray).

    In the case that we get a bad timepoint from the headers, we just copy
    the previous week's number.
    """
    x = np.zeros(tp)
    for j, t in enumerate(timevector):
        try:
            x[j] = np.where(l == t)[0]
        # if we don't get a valid timestamp from some data,
        # we use the previous week.
        except:
            x[j] = x[j-1]
    
    return x

def get_scan_week(data_path, subject):
    """
    This finds the 'imageactualdate' field and converts it to week number.
    If we don't find this date, we return -1.
    """
    dcm_path = os.path.join(data_path, 'dcm', subject)
    dicoms = os.listdir(dcm_path)
    trys = ['imageactualdate', 'seriesdate']
    for dicom in dicoms:
        # read in the dicom header
        d = dcm.read_file(os.path.join(dcm_path, dicom))
        
        for t in trys:
            if t == 'imageactualdate':
                try: 
                    imgdate = d['0009','1027'].value
                    imgdate = datetime.datetime.fromtimestamp(
                                       float(imgdate)).strftime("%U")
                    return int(imgdate)
                except:
                    pass

            if t == 'seriesdate':
                try:
                    imgdate = d['0008','0021'].value
                    imgdate = datetime.datetime.strptime(
                                       imgdate, '%Y%m%d').strftime("%U")
                    return int(imgdate)
                except:
                    pass

    # if we don't find a date, return -1. This won't break the code, but
    # will raise the alarm that somthing is wrong.
    print("ERROR: No DICOMs with imageactualdate found for {} !".format(subject))
    return -1

def get_time_array(sites, dtype, subjects, data_path, tp):
    """
    Returns an array of the scan weeks for each site (a list), for a given
    datatype. In spins it is pretty safe to assume that FBN and ADN were 
    acquired at the same time, so we only check ADN.
    """

    # init array
    timearray = []
    for site in sites:
        
        # init vector
        timepoints = []

        # filter by site, then datatype
        sitesubj = filter(lambda x: site in x, subjects)
        sitesubj = filter(lambda x: dtype in x, sitesubj)

        # now grab the weeks
        for ss in sitesubj:
            week = get_scan_week(data_path, ss)
            timepoints.append(week)

        # keep only the last n timepoints, append to array
        timepoints = timepoints[-tp:]
        timearray.append(timepoints)

    # convert to numpy array
    timearray = np.array(timearray)

    return timearray

def find_adni_niftis(subject_folder):
    """
    Returns all of the candidate ADNI phantom files in a subject folder.
    """
    candidates = filter(lambda x: '.nii.gz' in x, os.listdir(subject_folder))
    candidates = filter(lambda x: 'bravo' in x.lower() 
                               or 'mprage' in x.lower() 
                               or 'fspgr' in x.lower(), candidates)
    candidates.sort()

    return candidates

def find_fmri_niftis(subject_folder):
    """
    Returns all of the candidate ADNI phantom files in a subject folder.
    """
    candidates = filter(lambda x: '.nii.gz' in x, os.listdir(subject_folder))
    candidates = filter(lambda x: 'resting' in x.lower(), candidates)
    candidates.sort()

    return candidates

def main_adni(project, sites, tp):
    # set paths, datatype
    data_path = os.path.join(project, 'data')
    dtype = 'ADN'
    subjects = dm.utils.get_phantoms(os.path.join(data_path, 'nii'))

    # get the timepoint arrays for each site, and the x-values for the plots
    timearray = get_time_array(sites, dtype, subjects, data_path, tp)
    l = get_scan_range(timearray)
    cmap = get_discrete_colormap(len(sites), plt.cm.rainbow)

    # for each site, for each subject, for each week, get the ADNI measurements
    # and store them in a 9 x site x timepoint array:
    array = np.zeros((9, len(sites), tp))

    for i, site in enumerate(sites):

        # get the n most recent subjects
        sitesubj = filter(lambda x: site in x, subjects)
        sitesubj = filter(lambda x: dtype in x, sitesubj)
        sitesubj = sitesubj[-tp:]

        for j, subj in enumerate(sitesubj):

            candidates = find_adni_niftis(os.path.join(data_path, 'nii', subj))
            phantom = candidates[-1]
            if os.path.isfile(os.path.join(project, 'qc/phantom/adni', subj + '.csv')) == False:
                adni = find_adni_t1_vals(project, 
                           os.path.join(data_path, 'nii', subj, phantom),erosion=13)
                # write csv file header='s1,s2,s3,s4,s5,s2/s1,s3/s1,s4/s1,s5/s1')
                np.savetxt(os.path.join(
                           project, 'qc/phantom/adni', subj + '.csv'), adni.T,
                                      delimiter=',', newline=',', comments='')
            else:
                adni = np.genfromtxt(os.path.join(project, 'qc/phantom/adni', subj + '.csv'))
                adni = adni.T

            array[:, i, j] = adni

    # now plot these values in 9 subplots, respecting upload week
    h, w = plt.figaspect(3/3)
    plt.figure(figsize=(w*2.5, h*2.5))

    titles = ['S1 T1 Contrast', 'S2 T1 Contrast', 'S3 T1 Contrast',
              'S4 T1 Contrast', 'S5 T1 Contrast',
              'S2/S1 Ratio', 'S3/S1 Ratio', 'S4/S1 Ratio', 'S5/S1 Ratio']

    for i, plot in enumerate(array):
        
        # generate the scatterplot
        plt.subplot(5, 2, i+1)
        for s in np.arange(len(sites)):
            x = get_scatter_x(tp, l, timearray[s])
            plt.scatter(x, plot[s], c=cmap[s], marker="o")
        
        # set common elements
        plt.xticks(np.arange(len(l)), l.astype(np.int))
        plt.xlabel('Week Number', size=10)

        if len(sites) > 1:
            plt.legend(sites, loc='right', fontsize=8)

        # set figure-dependent elements
        plt.ylabel(titles[i], fontsize=10)
        plt.title(titles[i], size=10)

    # finish up
    plt.tight_layout() # do most of the formatting for us automatically
    if len(sites) == 1:
        title = '{} ADNI phantoms: {}, {} timepoints \n\n'.format(
                                site, time.strftime("%x"), str(tp))

    else:
        title = 'ADNI phantoms: {}, {} timepoints \n\n'.format(
                                      time.strftime("%x"), str(tp))
    plt.suptitle(title)
    plt.subplots_adjust(top=0.9) # give our title some breathing room

    if len(sites) == 1:
        filename = '{}/qc/phantom/adni/{}_ADNI_QC_{}.pdf'.format(
                                project, time.strftime("%y-%m-%d"), sites[0]) 
    else:
        filename = '{}/qc/phantom/adni/{}_ADNI_QC.pdf'.format(
                                project, time.strftime("%y-%m-%d")) 

    plt.savefig(filename)
    print('Successfully exported ' + filename)
    plt.close()

def main_fmri(project, sites, tp):
    """
    Finds the relevant fBRIN fMRI scans and submits them to the fBIRN pipeline,
    which is a matlab script kept in code/.

    The outputs of this pipeline are then plotted and exported as a PDF. 
    """
    # set paths, datatype
    data_path = os.path.join(project, 'data')
    dtype = 'FBN'
    subjects = dm.utils.get_phantoms(os.path.join(data_path, 'nii'))

    # get the timepoint arrays for each site, and the x-values for the plots
    timearray = get_time_array(sites, dtype, subjects, data_path, tp)
    l = get_scan_range(timearray)
    cmap = get_discrete_colormap(len(sites), plt.cm.rainbow)

    # for each site, for each subject, for each week, get the ADNI measurements
    # and store them in a 9 x site x timepoint array:
    array = np.zeros((7, len(sites), tp))

    for i, site in enumerate(sites):

        # get the n most recent subjects
        sitesubj = filter(lambda x: site in x, subjects)
        sitesubj = filter(lambda x: dtype in x, sitesubj)
        sitesubj = sitesubj[-tp:]

        for j, subj in enumerate(sitesubj):

            candidates = find_fmri_niftis(os.path.join(data_path, 'nii', subj))
            phantom = candidates[-1] # for upper bound of time range
            fbirn = find_fbirn_fmri_vals(project, subj, phantom)
            array[:, i, j] = fbirn

    # now plot these values in 7 subplots, respecting upload week
    h, w = plt.figaspect(3/3)
    plt.figure(figsize=(w*2.5, h*2.5))

    titles = [r'$\bar{x}$', r'$\sigma$', '% fluctuation', 
                           'Drift', 'SNR', 'SFNR', 'RDC']

    for i, plot in enumerate(array):

        # generate the scatterplot
        plt.subplot(4, 2, i+1)
        for s in np.arange(len(sites)):
            x = get_scatter_x(tp, l, timearray[s])
            plt.scatter(x, plot[s], c=cmap[s], marker="o")
        
        # set common elements
        plt.xticks(np.arange(len(l)), l.astype(np.int))
        plt.xlabel('Week Number', size=10)

        if len(sites) > 1:
            plt.legend(sites, loc='right', fontsize=8)

        # figure-specific titles


    # finish up
    plt.tight_layout() # do most of the formatting for us automatically
    if len(sites) == 1:
        title = '{} fMRI fBIRN phantoms: {}, {} timepoints \n\n'.format(
                                site, time.strftime("%x"), str(tp))

    else:
        title = 'fMRI fBIRN phantoms: {}, {} timepoints \n\n'.format(
                                      time.strftime("%x"), str(tp))
    plt.suptitle(title)
    plt.subplots_adjust(top=0.9) # give our title some breathing room

    if len(sites) == 1:
        filename = '{}/qc/phantom/fmri/{}_fMRI_QC_{}.pdf'.format(
                                project, time.strftime("%y-%m-%d"), sites[0]) 
    else:
        filename = '{}/qc/phantom/fmri/{}_fMRI_QC.pdf'.format(
                                project, time.strftime("%y-%m-%d")) 

    plt.savefig(filename)
    print('Successfully exported ' + filename)
    plt.close()

def main():
    global VERBOSE 
    global DEBUG
    arguments = docopt(__doc__)
    sites     = arguments['<sites>']
    ntp       = arguments['<ntp>']
    project   = arguments['<project>']
    VERBOSE   = arguments['--verbose']
    DEBUG     = arguments['--debug']

    main_adni(project, sites, int(ntp))
    main_fmri(project, sites, int(ntp))

if __name__ == '__main__':
    main()
