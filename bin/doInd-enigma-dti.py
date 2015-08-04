#!/usr/bin/env python
"""
This run ENIGMA DTI pipeline on one FA map.
This was made to be called from dm-proc-engimadti.py.

Usage:
  doInd-enigma-dti.py [options] <outputdir> <FAmap.nii.gz>

Arguments:
    <outputdir>        Top directory for the output file structure
    <FAmap.nii.gz>     Fractional Anisotropy Image in nifti format to start from

Options:
  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run

DETAILS
This run ENIGMA DTI pipeline on one FA map.
This was made to be called from dm-proc-engimadti.py - which runs enigma-dti protocol
for a group of subjects (or study) - then creates a group csv output.

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
outputdir       = arguments['<outputdir>']
FAmap           = arguments['<FAmap.nii.gz>']
VERBOSE         = arguments['--verbose']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']

if DEBUG: print arguments



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

## These are the links to some templates and settings from enigma
skel_thresh = 0.049
distancemap = os.path.join(ENIGMAHOME,'ENIGMA_DTI_FA_skeleton_mask_dst.nii.gz')
search_rule_mask = os.path.join(FSLDIR,'data','standard','LowerCingulum_1mm.nii.gz')
tbss_skeleton_input = os.path.join(ENIGMAHOME,'ENIGMA_DTI_FA.nii.gz')
tbss_skeleton_alt = os.path.join(ENIGMAHOME, 'ENIGMA_DTI_FA_skeleton_mask.nii.gz')

# make some output directories
outputdir = os.path.normpath(outputdir)
## orig version of ENIGMA_MASTER.sh protocol used these directories to organize data
# FA_to_target_dir = os.path.join(outputdir,'FA_to_target')
# FA_skels_dir = os.path.join(outputdir,'FA_skels')
# dm.utils.mkdir(FA_to_target_dir)
# dm.utils.mkdir(FA_skels_dir)

## if nifti input is not inside the outputdir than copy it here
FAimage = os.path.basename(FAmap)
FAimage_noext = FAimage.replace(dm.utils.get_extension(FAimage),'')
if os.path.dirname(FAimage) != outputdir:
    docmd(['cp',FAmap,os.path.join(outputdir,FAimage)])

ROIoutdir = os.path.join(outputdir, 'ROI')
dm.utils.makedirs(ROIoutdir)
csvout1 = os.path.join(ROIoutdir, FAimage_noext + '_FA_to_target_FAskel_ROIout.csv')
csvout2 = os.path.join(ROIoutdir, FAimage_noext + '_FA_to_target_FAskel_ROIout_avg.csv')

###############################################################################
print("TBSS STEP 1")
## cd into the output directory
os.chdir(outputdir)
docmd(['tbss_1_preproc', FAimage])

###############################################################################
print("TBSS STEP 2")
docmd(['tbss_2_reg', '-t', os.path.join(ENIGMAHOME,'ENIGMA_DTI_FA.nii.gz')])

###############################################################################
print("TBSS STEP 3")
docmd(['tbss_3_postreg','-S'])
##kinda a useless step....
#docmd(['cp', 'FA/' + FAimage_noext + '_FA_to_target.nii.gz', FA_to_target_dir])

###############################################################################
print("Skeletonize...")
# Note many of the options for this are printed at the top of this script
FAskel = os.path.join(ouputdir,'FA', FAimage_noext + '_FA_to_target_FAskel.nii.gz')
docmd('tbss_skeleton', \
      '-i', tbss_skeleton_input, \
      '-s', tbss_skeleton_alt, \
      '-p', str(skel_thresh), distancemap, search_rule_mask,
       'FA/' + FAimage_noext + '_FA_to_target.nii.gz',
       FAskel)

###############################################################################
echo "Convert skeleton datatype to 'float'..."
docmd(['fslmaths', FAskel, '-mul', '1', FAskel, '-odt', 'float'])

###############################################################################
print("ROI part 1...")
## note - right now this uses the _exe for ENIGMA - can probably rewrite this with nibabel

docmd([os.path.join(ENIGMAHOME,'singleSubjROI_exe'),
          os.path.join(ENIGMAHOME,'ENIGMA_look_up_table.txt'), \
          os.path.join(ENIGMAHOME, 'ENIGMA_DTI_FA_skeleton.nii.gz'), \
          os.path.join(ENIGMAHOME, 'JHU-WhiteMatter-labels-1mm.nii.gz'), \
          csvout1, FAskel])

###############################################################################
## part 2 - loop through all subjects to create ROI file
##			removing ROIs not of interest and averaging others
##          note: also using the _exe files to do this at the moment
print("ROI part 2...")
# ROIoutdir2 = os.path.join(outputdir, 'ROI_part2')
# dm.utils.makedirs(ROIoutdir2)
docmd([os.path.join(ENIGMAHOME, 'averageSubjectTracts_exe'), csvout1, csvout2])

###############################################################################
print("Done !!")
