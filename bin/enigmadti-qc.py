#!/usr/bin/env python
"""
Run QC -stuff for enigma dti pipeline.
By default the resutls are put in <outputdir>/ENIGMA-DTI-results.csv

Usage:
  enigmadti-qc.py [options] <outputdir>

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
This creates some QC outputs from of enigmaDTI pipeline stuff.
This is configured to work for file of the enigma dti pipeline.

Write now if pastes together a lot of info in pdfs like
http://enigma.ini.usc.edu/wp-content/uploads/DTI_Protocols/ENIGMA_FA_Skel_QC_protocol_USC.pdf

Written by Erin W Dickie, July 30 2015
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
ENIGMAQCPATH = '/home/edickie/code/ENIGMA_QC/enigmaDTI_QC/'
### Erin's little function for running things in the shell
def docmd(cmdlist):
    "sends a command (inputed as a list) to the shell"
    if DEBUG: print ' '.join(cmdlist)
    if not DRYRUN: subprocess.call(cmdlist)

## find the files that match the resutls tag...first using the place it should be from doInd-enigma-dti.py
results = pd.read_csv(resultsfile, sep=',', dtype=str, comment='#')
QCdir = os.path.join(outputdir,'QC')
QCskeldir = os.path.join(QCdir,'FAskel')

for i in range(0,len(results)):
    ## read the subject vars from the checklist
    subid = str(results['id'][i])
    FAorig = str(results['FA_nii'][i])
    FA_to_target = FAorig.replace('.nii.gz','_FA_to_target.nii.gz')
    FAskel = FAorig.replace('.nii.gz','_FA_to_target_FAskel.nii.gz')
    matlabcmd = ['addpath '+ ENIGMAQCPATH + ';' + \
        'func_QC_enigmaDTI_FA_skel(\'' + subid + '\',\'' + \
        os.path.join(outputdir,subid,'FA',FA_to_target) + '\',\'' + \
        os.path.join(outputdir,subid,'FA',FAskel) + '\',\'' + \
        QCskeldir + '\');exit']
    docmd(['matlab', '-nodisplay', '-nosplash', '-r',"\"{}\"".format(matlabcmd[0])])
