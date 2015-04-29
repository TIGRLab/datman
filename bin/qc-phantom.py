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
    + 

    This message is printed with the -h, --help flags.
"""

import os, sys
import time, datetime

import datman as dm
import dicom as dcm
from docopt import docopt

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

def print_adni_qc(data, title):
    """
    Prints out the supplied ADNI phantom (masked?) to a QC folder for eyeballs.
    """
    # extract path for QC saving
    path = title.split('nifti')[0]
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
    plt.savefig(path + '/qc/phantom/adni/' + title + '.jpg')
    plt.close()

def find_adni_t1_vals(data, erosion=13):
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

    title = copy(data) # QC

    data = nib.load(data).get_data() # import
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
    print_adni_qc(plot, title)
    
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
        print(l)
        print(t)
        print(np.where(l == t)[0])
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
    for dicom in dicoms:
        try: 
            d = dcm.read_file(os.path.join(dcm_path, dicom))
            imgdate = d['0009','1027'].value
            imgdate = datetime.datetime.fromtimestamp(
                               float(imgdate)).strftime("%U")
            return int(imgdate)

        except:
            continue

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
    subjects = dm.utils.get_phantoms(data_path)

    # get the timepoint arrays for each site, and the x-values for the plots
    timearray = get_time_array(sites, dtype, subjects, data_path, tp)
    l = get_scan_range(timearray)

    # for each site, for each subject, for each week, get the ADNI measurements
    # and store them in a 9 x site x timepoint array:
    array = np.zeros((9, len(sites), tp))

    for i, site in enumerate(sites):

        # get the n most recent subjects
        sitesubj = filter(lambda x: site in x, subjects)
        sitesubj = filter(lambda x: dtype in x, sitesubj)
        sitesubj = sitesubj[-tp:]

        for j, subj in enumerate(sitesubj):

            candidates = find_adni_niftis(os.path.join(
                                              data_path, 'nifti', subj))
            # the last candidate will be the final phantom scanned, and the
            # reoriented output from dcm2nii ('_3')
            phantom = candidates[-1]

            adni = find_adni_t1_vals(os.path.join(
                                         data_path, 'nifti', subj, phantom),
                                                                 erosion=13)
            # write csv file
            np.savetxt(os.path.join(
                       data_path, 'qc/phantom/adni', subj + '.csv'), adni.T,
                       delimiter=',', newline=',', comments='')#,
                       #header='s1,s2,s3,s4,s5,s2/s1,s3/s1,s4/s1,s5/s1')

            #print('site ' + str(site) + '; subj ' + str(subj))
            array[:, i, j] = adni

    # now plot these values in 9 subplots, respecting upload week
    h, w = plt.figaspect(3/3)
    plt.figure(figsize=(w*2, h*2))

    titles = ['S1 T1 Contrast', 'S2 T1 Contrast', 'S3 T1 Contrast',
              'S4 T1 Contrast', 'S5 T1 Contrast',
              'S2/S1 Ratio', 'S3/S1 Ratio', 'S4/S1 Ratio', 'S5/S1 Ratio']

    for i,  plot in enumerate(array):
        plt.subplot(3, 3, i+1)

        if len(sites) > 1:
            x = get_scatter_x(tp, l, timearray[0])
            plt.scatter(x, plot[0], c='black', marker="o")
            x = get_scatter_x(tp, l, timearray[1])
            plt.scatter(x, plot[1], c='red', marker="1")
            x = get_scatter_x(tp, l, timearray[2])
            plt.scatter(x, plot[2], c='green', marker="s")

        else:
            x = get_scatter_x(tp, l, timearray[0])
            plt.scatter(x, plot[0], c='black', marker="o")
        
        # set common elements
        plt.xticks(np.arange(len(l)), l.astype(np.int))
        plt.xlabel('Week Number', size=10)
        if len(sites) > 1:
            plt.legend(sites, loc='right', fontsize=8)

        # set figure-dependent elements
        if i < 6:
            plt.ylabel('T1 Constrast', size=10)
        else:
            plt.ylabel('T1 Ratio', size=10)

        plt.title(titles[i], size=10)

    # finish up
    plt.tight_layout() # do most of the formatting for us automatically

    if len(sites) == 1:
        plt.suptitle(sites[0] + ' ADNI phantoms: ' + time.strftime("%x") 
                              + ', ' + str(tp) + ' timepoints \n\n')
    else:
        plt.suptitle('ADNI phantoms: ' + time.strftime("%x") 
                                + ', ' + str(tp) + ' timepoints \n\n')
    plt.subplots_adjust(top=0.9) # give our title some breathing room

    if len(sites) == 1:
        filename = (data_path + '/qc/phantom/adni/' + time.strftime("%y-%m-%d")
                              + '_ADNI_QC_' + sites[0] + '.pdf')
    elif len(sites) > 1:
        filename = (data_path + '/qc/phantom/adni/' + time.strftime("%y-%m-%d") 
                              + '_ADNI_QC.pdf')
    
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
    n_sites = len(sites)
    cmap = get_discrete_colormap(n_sites, plt.cm.rainbow)

    # for each site, for each subject, for each week, get the ADNI measurements
    # and store them in a 9 x site x timepoint array:
    array = np.zeros((7, n_sites, tp))

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

    # now plot these values in 6 subplots, respecting upload week
    h, w = plt.figaspect(3/3)
    plt.figure(figsize=(w*2, h*2))

    titles = ['Mean +/- SD', '% fluctuation', 'Drift', 'SNR', 'SFNR', 'RDC']

    for i, plot in enumerate(array):

        # keep track of subplots in the all case
        if i == 0:
            plt.subplot(3, 2, i+1)
            errors = array[1, :, :]

            for s in np.arange(n_sites):
                x = get_scatter_x(tp, l, timearray[s])
                plt.errorbar(x, plot[s], yerr=errors[s], c=cmap[s], marker="o")

        # skip the SD plot (merge with mean)
        if i == 1:
            continue

        elif i > 0 and len(sites) > 1:
            plt.subplot(3, 2, i)

            for s in np.arange(n_sites):
                x = get_scatter_x(tp, l, timearray[s])
                plt.scatter(x, plot[s], c=cmap[s], marker="o")
        
        # set common elements
        plt.xticks(np.arange(len(l)), l.astype(np.int))
        plt.xlabel('Week Number', size=10)

        if len(sites) > 1:
            plt.legend(sites, loc='right', fontsize=8)

        # set figure-dependent elements
        if i == 0:
            plt.ylabel(r'$\bar{x}$ and $\pm \sigma$', fontsize=10)
        elif i == 2:
            plt.ylabel('% fluctuation', fontsize=10)
        elif i == 3:
            plt.ylabel('drift', fontsize=10)
        elif i == 4:
            plt.ylabel('SNR', fontsize=10)
        elif i == 5:
            plt.ylabel('SFNR', fontsize=10)
        elif i == 6:
            plt.ylabel('rdc', fontsize=10)

        if i == 0:
            plt.title(titles[i], size=10)
        else:
            plt.title(titles[i-1], size=10)

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

    #main_adni(project, sites, tp)
    main_fmri(project, sites, int(ntp))

if __name__ == '__main__':
    main()
