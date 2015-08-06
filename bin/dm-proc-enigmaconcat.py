#!/usr/bin/env python
"""
Combines the outputs of enigma dti into one file.
By default the resutls are put in <outputdir>/ENIGMA-DTI-results.csv

Usage:
  doInd-enigmaconcat.py [options] <outputdir>

Arguments:
    <outputdir>        Top directory for the output file structure

Options:
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
VERBOSE         = arguments['--verbose']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']

if DEBUG: print arguments

## if no result file is given use the default name
outputdir = os.path.normpath(outputdir)
if resultsfile == None:
    resultsfile = os.path.join(outputdir,ENIGMA-DTI-results.csv)

####set checklist dataframe structure here
#because even if we do not create it - it will be needed for newsubs_df (line 80)
cols = ["id", "FA_nii", "date_ran", "run",\
    "ACR-L","ACR-R","ALIC-L","ALIC-R","AverageFA","BCC","CGC","CGC-L","CGC-R",\
    "CR","CR-L","CR-R","CST","CST-L","CST-R","EC","EC-L","EC-R","FX","GCC",\
    "IC","IC-L","IC-R","IFO","IFO-L","IFO-R","PCR-L","PCR-R","PLIC-L","PLIC-R",\
    "PTR","PTR-L","PTR-R","RLIC-L","RLIC-R","SCC","SCR-L","SCR-R","SFO","SFO-L",\
    "SFO-R","SLF","SLF-L","SLF-R","SS","SS-L","SS-R","UNC-L","UNC-R", \
    "qc_rator", "qc_rating", "notes"]

# if the checklist exists - open it, if not - create the dataframe
if os.path.isfile(resultsfile):
	results = pd.read_csv(results, sep=',', dtype=str, comment='#')
else:
	results = pd.DataFrame(columns = cols)

###now need to insert the new dataness...
