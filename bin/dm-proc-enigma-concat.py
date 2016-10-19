#!/usr/bin/env python
"""
Combines the outputs of enigma dti into one file.
By default the resutls are put in <outputdir>/ENIGMA-DTI-results.csv

Usage:
  dm-proc-enigma-concat.py [options] <outputdir> <postfix> <resultsfile>

Arguments:
    <outputdir>        Top directory for the output file structure
    <postfix>          Postfix that get appended to columnname (ex FA, MD, RD)
    <resultsfile>      Filename for the results csv output

Options:
  --ROItxt-tag STR         String within the individual participants results that identifies their data (default = 'ROIout_avg')
  --output-nVox            Output value from "nVoxels" column instead of "Average"
  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run

DETAILS
This concatenates all the FA info inside  *_ROIout_avg.csv files
This is configured to work for file of the enigma dti pipeline - but could easily
be adapted to work on other output files.

The default setting are made to work with the outputs of dm-proc-enigmadti.py - and to
update to the results csv file created by that pipeline.
However, using the optional arguments (--gen-results and --results <FILE>) you can
apply this script to concatenate results of older pipelines - not following
the dm-proc-enigmadti.py file structure, and/or to change the name (and/or location)
of the output file.

The option "--ROItxt-tag <STR>" can be used to change the search string "_ROIout_avg"
in order to search for different pipeline output files.

Written by Erin W Dickie, July 30 2015
Adapted from ENIGMA_MASTER.sh - Generalized October 2nd David Rotenberg Updated Feb 2015 by JP+TB
#Note -need ot expand path on FAskel -or it fails if relative paths given...
"""
from docopt import docopt
import pandas as pd
import datman as dm
import datman.utils
import datman.scanid
import glob
import os
import sys
import subprocess
import datetime

arguments       = docopt(__doc__)
outputdir       = arguments['<outputdir>']
postfix         = arguments['<postfix>']
resultsfile     = arguments['<resultsfile>']
ROItxt_tag      = arguments['--ROItxt-tag']
OUTPUT_nVOXELS  = arguments['--output-nVox']
VERBOSE         = arguments['--verbose']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']

if DEBUG: print arguments

## if no result file is given use the default name
outputdir = os.path.normpath(outputdir)
if resultsfile == None:
    resultsfile = os.path.join(outputdir,'ENIGMA-DTI-results.csv')
if ROItxt_tag == None: ROItxt_tag = postfix + 'skel_ROIout_avg'

SUBFOLDERS = True ## assume that the file is inside a heirarchy that contains folders with subject names
## find the files that match the resutls tag...first using the place it should be from doInd-enigma-dti.py
ROIfiles = glob.glob(outputdir + '/*/*/*' +  ROItxt_tag + '*')
## if that doesn't work, try the pattern from ENIGMA_MASTER.sh (it could be old data)
if len(ROIfiles) == 0:
    ROIfiles = glob.glob(outputdir + '/*/*' +  ROItxt_tag + '*')
    SUBFOLDERS = False #there are probaly not individual subject folders
## if that doesn't work - try one more level up...
if len(ROIfiles) == 0:
    ROIfiles = glob.glob(outputdir + '/*' +  ROItxt_tag + '*')
## if we still haven't found any files..give up and exit
if len(ROIfiles) == 0:
    sys.exit('Could not find any csv files with tag *{}*'.format(ROItxt_tag))
if DEBUG: print ROIfiles

## load the first ROIfile to get column header info
firstROItxt = pd.read_csv(ROIfiles[0], sep=',', dtype=str, comment='#')
tractnames = firstROItxt['Tract'].tolist() # reads the tract names from the 'Tract' column for template
tractcolnames = [tract + '_' + postfix for tract in tractnames]

####set up the resutls dataframe
if os.path.isfile(resultsfile):
    ## if the resultsfile exists - then read it in or exit
    results = pd.read_csv(resultsfile, sep=',', dtype=str, comment='#')
    # double check that all the tractnames are present in the header
    cols = list(results.columns.values)
    if len(set(tractcolnames) & set(cols)) < len(tractcolnames):
        print("warning - not all tractnames in header...")
else:
    cols = ['id'] + tractcolnames
    results = pd.DataFrame(columns = cols)


###now need to insert the new dataness...
for csvfile in ROIfiles:
    # for each csv - read it using pandas
    csvdata = pd.read_csv(csvfile, sep=',', dtype=str, comment='#')
    if SUBFOLDERS == True:
        # if this data follows the dm-proc-enigmadti.py structure: search for the subid
        ###### if should be two direcotories up from the file
        this_id = os.path.basename(os.path.dirname(os.path.dirname(csvfile)))
    else:
        ## if not - use the csv filename as the subgject id
        this_id = os.path.basename(csvfile)
    if this_id in set(results.id):
        ## search for the correct row
        idx = results[results.id == this_id].index[0]
    else:
        ## if the subject id is not present in the results dataframe - create a new row for it
        idx = len(results)
        results = results.append(pd.DataFrame(columns = cols, index = [idx]))
        results.id[idx] = this_id
    for i in range(len(tractnames)):
        ## for each tract in the list, update the value in the results
        tractname = tractnames[i]
        tractcolname = tractcolnames[i]
        if OUTPUT_nVOXELS:
            val = int(csvdata.loc[csvdata['Tract']==tractname]['nVoxels'])
        else:
            val = float(csvdata.loc[csvdata['Tract']==tractname]['Average'])
        results[tractcolname][idx] = val

## write the results out to a file
results.to_csv(resultsfile, sep=',', columns = cols, index = False)
