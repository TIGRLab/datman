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
    --adni                   Run on ADNI phantom data
    --fmri                   Run on fBIRN fMRI phantom data
    --dti                    Run of fBIRN DTI phantom data

DETAILS

    This program find phantom data (supported: ADNI, fBIRN fMRI, fBIRN DTI)
    and calcuates relevant statistics on them.

    This expects properly-formatted phantom tags:
        ADNI       -- T1
        fBIRN fMRI -- RST
        fBIRN DIT  -- DTI

    Each file is then sent through the appropriate analysis pipeline, if the
    outputs do not already exist. Finally, this compiles results of the last
    n weeks into a plot that summarizes the data from the submitted sites.

    Often, you will want to plot all sites together, and then each site one
    by one, if the scales are substantially different across sites.

DEPENDENCIES

    + matlab
    + afni
    + fsl

    This message is printed with the -h, --help flags.
"""

import os, sys
import time, datetime
import csv, yaml

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

def parse_config(filename, field):
    """
    Return the contents of the specified field, if found. If not, return None.
    """
    with open(filename, 'r') as fname:
        data = yaml.load(fname)

    try:
        return data[field]
    except KeyError:
        print('ERROR: Field {} does not exist in {}.'.format(field, filename))
        return None

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

def find_fmri_vals(base_path, subj, phantom):
    """
    This runs the spins_fbirn matlab code if required, and returns the output
    as a vector.
    """
    datman_config = os.getenv('datman_config')
    if datman_config:
        qc_code = parse_config(datman_config, 'phantom-qc')
    else:
        sys.exit('ERROR: datman_config env variable is not defined.')

    outputfile = os.path.join(base_path, 'qc/phantom/fmri/', subj + '.csv')
    if os.path.isfile(outputfile) == False:
        cmd = (r"addpath(genpath('{}')); analyze_fmri_phantom('{}','{}','{}')".format(qc_code, base_path, subj, phantom))
        os.system('matlab -nodisplay -nosplash -r "' + cmd + '"')

    data = np.genfromtxt(outputfile, delimiter=',',dtype=np.float, skip_header=1)

    return data[1:]

def find_dti_vals(base_path, subj, raw, bval, fa):
    """
    This runs the spins_fbirn matlab code if required, and returns the output
    as a vector.
    """
    datman_config = os.getenv('datman_config')
    if datman_config:
        qc_code = parse_config(datman_config, 'phantom-qc')
    else:
        sys.exit('ERROR: datman_config env variable is not defined.')

    output = os.path.join(base_path, 'qc/phantom/dti/', subj)
    dm.utils.makedirs(output)
    outputfile = os.path.join(output, 'main_stats.csv')

    if os.path.isfile(outputfile) == False:
        cmd = (r"addpath(genpath('{}')); analyze_dti_phantom('{}','{}','{}', '{}', {})".format(
                                               qc_code, raw, fa, bval, output, 1))
        os.system('matlab -nodisplay -nosplash -r "' + cmd + '"')

    data = np.genfromtxt(outputfile, delimiter=',',dtype=np.float, skip_header=1)

    return data

def get_scan_range(timearray):
    """
    Takes the week indicies from a time array and returns the total extent
    of time to plot (as not all sites will have data available for each week).

    l = the labels for the given time points
    """
    # use the derivative to find years
    first_year_mins = []
    first_year_maxs = []
    last_year_maxs = []
    number_of_years = []

    # collect the number of years, earliest week, latest week from each site
    for site in timearray:
        timediff = np.where(np.diff(site) < 1)[0]
        n_years = len(timediff) # number of year rollovers

        if n_years > 0:
            first_year = np.split(site, [timediff[0]+1])[0]
            last_year = np.split(site, [timediff[-1]+1])[-1]

            first_year_mins.append(first_year[0])
            last_year_maxs.append(last_year[-1])
            number_of_years.append(n_years)

        else:
            first_year_mins.append(site[0])
            first_year_maxs.append(site[0])

    # now construct a timearray spanning the entire range
    minimum = np.min(first_year_mins)
    if len(last_year_maxs) == 0:
        maximum = np.max(first_year_maxs)
    else:
        maximum = np.max(last_year_maxs)

    if len(number_of_years) > 0:
        years = max(number_of_years)

        l = np.hstack((np.linspace(minimum, 51, num=52-minimum),
                       np.tile(np.linspace(0, 51, 52), years-1),
                       np.linspace(0, maximum, num=maximum+1)))

    else:
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

def get_scan_date(data_path, subject):
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
                    disc = datetime.datetime.fromtimestamp(float(imgdate)).strftime("%Y %B %d")
                    imgdate = datetime.datetime.fromtimestamp(float(imgdate)).strftime("%U")
                    return int(imgdate), disc
                except:
                    pass

            if t == 'seriesdate':
                try:
                    imgdate = d['0008','0021'].value
                    disc = datetime.datetime.strptime(imgdate, '%Y%m%d').strftime("%Y %B %d")
                    imgdate = datetime.datetime.strptime(imgdate, '%Y%m%d').strftime("%U")
                    return int(imgdate), disc
                except:
                    pass

    # if we don't find a date, return -1. This won't break the code, but
    # will raise the alarm that somthing is wrong.
    print("ERROR: No DICOMs with valid date field found for {} !".format(subject))
    return -1, 'NA'

def get_time_array(sites, dtype, subjects, data_path, tp):
    """
    Returns an array of the scan weeks for each site (a list), for a given
    datatype. In the multiphantom case we assume all phantoms were collected
    at the same time.

    Also returns a list of datetime strings for humans to read.
    """

    # init array
    timearray = []
    discarray = []
    for site in sites:

        # init vector
        timepoints = []
        timediscription = []

        # filter by site, then datatype
        sitesubj = filter(lambda x: site in x, subjects)
        sitesubj = filter(lambda x: dtype in x, sitesubj)

        # now grab the weeks
        for ss in sitesubj:
            week, fulldate = get_scan_date(data_path, ss)
            timepoints.append(week)
            timediscription.append(fulldate)

        # keep only the last n timepoints, append to array
        timepoints = timepoints[-tp:]
        timediscription = timediscription[-tp:]
        timearray.append(timepoints)
        discarray.append(timediscription)

    # convert to numpy array
    timearray = np.array(timearray)

    return timearray, discarray

def find_adni_niftis(subject_folder):
    """
    Returns all of the candidate ADNI phantom files in a subject folder.
    """
    candidates = filter(lambda x: '.nii.gz' in x, os.listdir(subject_folder))
    candidates = filter(lambda x: 't1' in x.lower(), candidates)
    candidates.sort()

    return candidates

def find_fmri_inputs(subject_folder):
    """
    Returns all of the candidate fMRI phantom files in a subject folder.
    """
    candidates = filter(lambda x: '.nii.gz' in x, os.listdir(subject_folder))
    candidates = filter(lambda x: 'resting' in x.lower(), candidates)
    candidates.sort()

    return candidates

def find_dti_inputs(folder, subj):
    """
    Returns all of the candidate DTI phantom files in a subject folder.
    """
    nifti_folder = os.path.join(folder, 'nii', subj)
    dtifit_folder = os.path.join(folder, 'dtifit', subj)

    # get the last raw nifti with no acceleration found
    candidates = filter(lambda x: '.nii.gz' in x, os.listdir(nifti_folder))
    candidates = filter(lambda x: 'dti' in x.lower() and 'no' in x.lower(), candidates)
    candidates.sort()
    raw = os.path.join(nifti_folder, candidates[-1])

    # get the bval file
    discription = dm.utils.scanid.parse_filename(raw)[3]
    candidates = filter(lambda x: discription in x and '.bval' in x, os.listdir(nifti_folder))
    bval = os.path.join(nifti_folder, candidates[-1])

    # get the FA map
    sn = dm.utils.scanid.parse_filename(raw)[2]
    candidates = filter(lambda x: '_{}_'.format(sn) in x and '_FA' in x, os.listdir(dtifit_folder))
    fa = os.path.join(dtifit_folder, candidates[-1])

    return raw, bval, fa

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
    timearray, discarray = get_time_array(sites, dtype, subjects, data_path, tp)
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

            candidates = find_fmri_inputs(os.path.join(data_path, 'nii', subj))
            phantom = candidates[-1] # for upper bound of time range
            fbirn = find_fmri_vals(project, subj, phantom)
            array[:, i, j] = fbirn

    for plotnum, plot in enumerate(array):

        output = []

        # construct header
        o = []
        o.append('x')
        #o.append('date')
        for s in sites:
            o.append(str(s))
        output.append(o)

        # construct string dict
        datedict = {}
        for row in np.arange(len(l)):
            weeknum = l[row]
            for s in np.arange(len(sites)):
                for i, week in enumerate(timearray[s]):
                    if weeknum == week:
                        datedict[week] = discarray[s][i]

        # now add the data
        for row in np.arange(len(l)):
            o = []
            o.append(row)

            # append the string discription for the first site that matches
            weeknum = l[row]
            # o.append(datedict[weeknum])

            for s in np.arange(len(sites)):
                tmp = list(timearray[s])
                try:
                    idx = tmp.index(weeknum)
                    o.append(plot[s][idx])
                except:
                    o.append('')
            output.append(o)

        fname = '{}/qc/phantom/fmri/{}_fmri_{}.csv'.format(
                              project, time.strftime("%y-%m-%d"), str(plotnum))
        with open(fname, 'wb') as csvfile:
            writer = csv.writer(csvfile, delimiter=',',
                            quotechar='"', quoting=csv.QUOTE_MINIMAL)
            for row in output:
                writer.writerow(row)

def main_dti(project, sites, tp):
    """
    Finds the relevant fBRIN fMRI scans and submits them to the fBIRN pipeline,
    which is a matlab script kept in code/.

    The outputs of this pipeline are then plotted and exported as a PDF.
    """

    data_path = os.path.join(project, 'data')
    dtype = 'FBN'
    subjects = dm.utils.get_phantoms(os.path.join(data_path, 'nii'))

    # get the timepoint arrays for each site, and the x-values for the plots
    timearray, discarray = get_time_array(sites, dtype, subjects, data_path, tp)
    l = get_scan_range(timearray)
    cmap = get_discrete_colormap(len(sites), plt.cm.rainbow)
    # for each site, for each subject, for each week, get the dti measurements
    array = np.zeros((14, len(sites), tp))

    for i, site in enumerate(sites):

        # get the n most recent subjects
        sitesubj = filter(lambda x: site in x, subjects)
        sitesubj = filter(lambda x: dtype in x, sitesubj)
        sitesubj = sitesubj[-tp:]

        for j, subj in enumerate(sitesubj):

            raw, bval, fa = find_dti_inputs(data_path, subj)
            data = find_dti_vals(project, subj, raw, bval, fa)
            array[:, i, j] = data

    for plotnum, plot in enumerate(array):

        output = []
        o = []
        o.append('x')
        for s in sites:
            o.append(str(s))
        output.append(o)

        # construct string dict
        datedict = {}
        for row in np.arange(len(l)):
            weeknum = l[row]
            for s in np.arange(len(sites)):
                for i, week in enumerate(timearray[s]):
                    if weeknum == week:
                        datedict[week] = discarray[s][i]

        # now add the data
        for row in np.arange(len(l)):
            o = []
            o.append(row)

            # append the string discription for the first site that matches
            weeknum = l[row]

            for s in np.arange(len(sites)):
                tmp = list(timearray[s])
                try:
                    idx = tmp.index(weeknum)
                    o.append(plot[s][idx])
                except:
                    o.append('')
            output.append(o)

        fname = '{}/qc/phantom/dti/{}_dti_{}.csv'.format(
                              project, time.strftime("%y-%m-%d"), str(plotnum))
        with open(fname, 'wb') as csvfile:
            writer = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            for row in output:
                writer.writerow(row)

def main():
    global VERBOSE
    global DEBUG
    arguments = docopt(__doc__)
    sites     = arguments['<sites>']
    ntp       = arguments['<ntp>']
    project   = arguments['<project>']
    VERBOSE   = arguments['--verbose']
    DEBUG     = arguments['--debug']
    adni      = arguments['--adni']
    fmri      = arguments['--fmri']
    dti       = arguments['--dti']

    if not os.getenv('datman_config'):
        sys.exit('ERROR: datman_config environment variable is not defined.')

    if adni:
        main_adni(project, sites, int(ntp))

    if fmri:
        main_fmri(project, sites, int(ntp))

    if dti:
        main_dti(project, sites, int(ntp))

if __name__ == '__main__':
    main()
