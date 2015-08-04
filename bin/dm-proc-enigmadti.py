#!/usr/bin/env python
"""
This run ENIGMA DTI pipeline on FA maps after DTI-fit has been run.
Calls (or submits) doInd-enigma-dti.py for each subject in order to do so.

Usage:
  dm-proc-enigmadti.py [options] <input-dtifit-dir> <outputdir>

Arguments:
    <input-dtifit-dir>        Top directory for dti-fit output
    <outputdir>               Top directory for the output of enigma DTI

Options:
  --FA-tag  STR            String used to identify FA maps within DTI-fit input (default = '_FA'))
  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run

DETAILS
This run ENIGMA DTI pipeline on FA maps after DTI-fit has been run.
Calls (or submits) doInd-enigma-dti.py for each subject in order to do so.

Requires ENIGMA dti enviroment to be set (for example):
module load FSL/5.0.7 R/3.1.1 ENIGMA-DTI/2015.01

Written by Erin W Dickie, July 30 2015
Adapted from ENIGMA_MASTER.sh - Generalized October 2nd David Rotenberg Updated Feb 2015 by JP+TB
"""
from docopt import docopt
import pandas as pd
import datman as dm
import datman.utils
import datman.scanid
import glob
import os.environ
import os.path
import sys
import subprocess
import datetime

arguments       = docopt(__doc__)
dtifit_dir      = arguments['<input-dtifit-dir>']
outputdir       = arguments['<outputdir>']
FA_tag          = arguments['--FA-tag']
VERBOSE         = arguments['--verbose']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']

if DEBUG: print arguments
#set default tag values
if --FA-tag == None: T1_TAG = '_FA'

### Erin's little function for running things in the shell
def docmd(cmdlist):
    "sends a command (inputed as a list) to the shell"
    if DEBUG: print ' '.join(cmdlist)
    if not DRYRUN: subprocess.call(cmdlist)

# note - original version not using SGE within FSL
#export SGE_ON="false"    # for now, don't use SGE because it complicates things

ENIGMAHOME = os.environ.get('ENIGMAHOME')
if ENIGMAHOME==None:
    sys.exit("ENIGMAHOME environment variable is undefined. Try again.")
FSLDIR = os.environ.get('FSLDIR')
if FSLDIR==None:
    sys.exit("FSLDIR environment variable is undefined. Try again.")
#something to stop if final csv is found?? maybe not good if we wanna keep adding subs
# if [ ! -e ALL_Subject_Info.csv ];then
# 	echo "ALL_Subject_Info.csv DNE"
# 	exit 1
# fi

# make some output directories
outputdir = os.path.normpath(outputdir)
FA_to_target_dir = os.path.join(outputdir,'FA_to_target')
FA_skels_dir = os.path.join(outputdir,'FA_skels')
dm.utils.mkdir(FA_to_target_dir)
dm.utils.mkdir(FA_skels_dir)

## if nifti input is not inside the outputdir than copy it here
FAimage = os.path.basename(FAmap)
if os.path.dirname(FAimage) != outputdir:
    docmd(['cp',FAmap,os.path.join(outputdir,FAimage)])

## cd into the output directory
os.chdir(outputdir)


###############################################################################
## part 2 - loop through all subjects to create ROI file
##			removing ROIs not of interest and averaging others
echo "ROI part 2..."


if [ ! -e .done_ROI_part2 ]; then
  rm -f subjectList.csv
  for subject in FA_skels/*.nii.gz; do
    echo ${base},${dir02}/${base}_ROIout_avg.csv >> ./subjectList.csv
  done
  touch .done_ROI_part2
fi


###############################################################################
echo "ROI part 3..."

# subjectID in Table must match the first column in subjectList.csv
# keep DTI_ID in Table

Table=ALL_Subject_Info.csv
subjectIDcol=subjectID
subjectList=subjectList.csv
outTable=combinedROItable.csv
Ncov=2
covariates="Age;Sex"
Nroi="all" #2
rois="all"

combine_script=${ENIGMAHOME}/combine_subject_tables.R
echo "Running ${combine_script} with the following settings:
  Table        = ${Table}
  subjectIDcol = ${subjectIDcol}
  subjectList  = ${subjectList}
  outTable     = ${outTable}
  Ncov         = ${Ncov}
  covariates   = ${covariates}
  Nroi         = ${Nroi}
  rois         = ${rois}
"
R --no-save --slave --args \
  ${Table} \
  ${subjectIDcol} \
  ${subjectList} \
  ${outTable} \
  ${Ncov} \
  ${covariates} \
  ${Nroi} \
  ${rois} < ${ENIGMAHOME}/combine_subject_tables.R
