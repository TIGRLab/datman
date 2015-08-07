#!/usr/bin/env python
"""
Combines the outputs of enigma dti into one file.
By default the resutls are put in <outputdir>/ENIGMA-DTI-results.csv

Usage:
  doInd-enigmaconcat.py [options] <outputdir>

Arguments:
    <outputdir>        Top directory for the output file structure

Options:
  --gen-results            Genereate a new resutls file from the available data
  --ROItxt-tag STR         String within the individual participants results that identifies their data (default = 'ROIout_avg')
  --results FILE           Filename for the results csv output
  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run

DETAILS
This concatenates all the FA info inside  *_ROIout_avg.csv files from the enigma dti pipeline.

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
resultsfile     = arguments['--results']
GENresults      = arguments['--gen-results']
ROItxt_tag      = arguments['--ROItxt-tag']
VERBOSE         = arguments['--verbose']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']

if DEBUG: print arguments

## if no result file is given use the default name
outputdir = os.path.normpath(outputdir)
if resultsfile == None:
    resultsfile = os.path.join(outputdir,'ENIGMA-DTI-results.csv')
if ROItxt_tag == None: ROItxt_tag = '_ROIout_avg'

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

####set checklist dataframe structure here
#because even if we do not create it - it will be needed for newsubs_df (line 80)
# if the checklist exists - open it, if not - create the dataframe
if GENresults == False:
    if os.path.isfile(resultsfile):
        ## read in the file
    	results = pd.read_csv(resultsfile, sep=',', dtype=str, comment='#')
        cols = list(results.columns.values)
        if len(set(tractnames) & set(cols)) < len(tractnames):
            print("warning - not all tractnames in header...")
    else:
        sys.exit('Could not find {}'.format(resultsfile))
else:
    cols = ['id'] + tractnames
    results = pd.DataFrame(columns = cols)

###now need to insert the new dataness...
for csvfile in ROIfiles:
    csvdata = pd.read_csv(csvfile, sep=',', dtype=str, comment='#')
    if SUBFOLDERS == True:
        this_id = os.path.basename(os.path.dirname(os.path.dirname(csvfile)))
    else:
        this_id = os.path.basename(csvfile)
    if this_id in results.id:
        idx = results[results.id == this_id].index[0]
    else:
        idx = len(results)
        results = results.append(pd.DataFrame(columns = cols, index = [idx]))
        results.id[idx] = this_id
    for tractname in tractnames:
        results[tractname][idx] = csvdata['Average'][csvdata['Tract']==tractname]

## write the checklist out to a file
results.to_csv(resultsfile, sep=',', columns = cols, index = False)
