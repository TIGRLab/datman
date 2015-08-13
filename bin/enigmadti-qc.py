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

Requires matlab
module load matlab/R2014b_concurrent

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
    base_nii = str(results['base_nii'][i])
    to_target = base_nii + '_FA_to_target.nii.gz'
    FAskel = base_nii + '_FA_to_target_FAskel.nii.gz'
    docmd(['slices',to_target,'-o',os.path.join(tmpdir,subid + "to_target.gif")])
    docmd(['slices',FAskel,'-o',os.path.join(tmpdir,subid + "FAskel.gif")])
    docmd(['convert', '-negate', os.path.join(tmpdir,subid + "FAskel.gif"), \
        '+level-colors', 'magenta', \
        '-fuzz', '10%', '-transparent', 'white', \
        os.path.join(tmpdir,subid + 'FAskel_mag.gif')])
    docmd(['composite', os.path.join(tmpdir,subid + 'FAskel_mag.gif'),
        os.path.join(tmpdir,subid + 'to_target.gif'),
        os.path.join(QCskeldir,'subid_FAskel.gif'])
