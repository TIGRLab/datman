#!/usr/bin/env python
"""
This run ENIGMA DTI pipeline on one FA map.
This was made to be called from dm-proc-engimadti.py.

Usage:
  doInd-enigma-dti.py [options] <outputdir> <inputbase>

Arguments:
    <outputdir>        Top directory for the output file structure
    <inputbase>        Path to output input file minus the "_FA.nii.gz"

Options:
  --calc-MD                Option to process MD image as well
  --calc-all               Option to process MD, AD and RD
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
inputbase       = arguments['<map_base>']
CALC_MD         = arguments['--calc-MD']
CALC_ALL        = arguments['--calc-all']
VERBOSE         = arguments['--verbose']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']

if DEBUG: print arguments
PROCESS_MD = False if MDmap == None else True

### Erin's little function for running things in the shell
def docmd(cmdlist):
    "sends a command (inputed as a list) to the shell"
    if DEBUG: print ' '.join(cmdlist)
    if not DRYRUN: subprocess.call(cmdlist)

# check that ENIGMAHOME environment variable exists
ENIGMAHOME = os.getenv('ENIGMAHOME')
if ENIGMAHOME==None:
    sys.exit("ENIGMAHOME environment variable is undefined. Try again.")
# check that FSLDIR environment variable exists
FSLDIR = os.getenv('FSLDIR')
if FSLDIR==None:
    sys.exit("FSLDIR environment variable is undefined. Try again.")
# check that the input FA map exists
FAmap = inputbase + '_FA.nii.gz'
if os.path.isfile(FAmap) == False:
    sys.exit("Input file {} doesn't exist.".format(FAmap))
# check that the input MD map exists - if MD CALC chosen
if CALC_MD | CALC_ALL:
    MDmap = inputbase + '_MD.nii.gz'
    if os.path.isfile(MDmap) == False:
      sys.exit("Input file {} doesn't exist.".format(MDmap))
# check that the input L1, L2, and L3 maps exists - if CALC_ALL chosen
if CALC_ALL:
    for L in ['L1','L2','L3']
    Lmap = inputbase + '_' L + '.nii.gz'
    if os.path.isfile(MDmap) == False:
      sys.exit("Input file {} doesn't exist.".format(Lmap))

# make some output directories
outputdir = os.path.abspath(outputdir)

## These are the links to some templates and settings from enigma
skel_thresh = 0.049
distancemap = os.path.join(ENIGMAHOME,'ENIGMA_DTI_FA_skeleton_mask_dst.nii.gz')
search_rule_mask = os.path.join(FSLDIR,'data','standard','LowerCingulum_1mm.nii.gz')
tbss_skeleton_input = os.path.join(ENIGMAHOME,'ENIGMA_DTI_FA.nii.gz')
tbss_skeleton_alt = os.path.join(ENIGMAHOME, 'ENIGMA_DTI_FA_skeleton_mask.nii.gz')
ROIoutdir = os.path.join(outputdir, 'ROI')
dm.utils.makedirs(ROIoutdir)
image_noext = os.path.basename(inputbase)
FAimage = image_noext + '.nii.gz'
csvout1 = os.path.join(ROIoutdir, image_noext + '_FA_to_target_FAskel_ROIout')
csvout2 = os.path.join(ROIoutdir, image_noext + '_FA_to_target_FAskel_ROIout_avg')
FAskel = os.path.join(outputdir,'FA', image_noext + '_FA_to_target_FAskel.nii.gz')
###############################################################################
## setting up
## if teh outputfile is not inside the outputdir than copy it there
if os.path.isfile(os.path.join(outputdir,FAimage)) == False:
    docmd(['cp',FAmap,os.path.join(outputdir,FAimage)])

## cd into the output directory
os.chdir(outputdir)
os.putenv('SGE_ON','false')
###############################################################################
print("TBSS STEP 1")

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
docmd(['tbss_skeleton', \
      '-i', tbss_skeleton_input, \
      '-s', tbss_skeleton_alt, \
      '-p', str(skel_thresh), distancemap, search_rule_mask,
       'FA/' + FAimage_noext + '_FA_to_target.nii.gz',
       FAskel])

###############################################################################
print("Convert skeleton datatype to 'float'...")
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
docmd([os.path.join(ENIGMAHOME, 'averageSubjectTracts_exe'), csvout1 + '.csv', csvout2 + '.csv'])

##############################################################################
## Now process the MD if that option was asked for
## if processing MD also set up for MD-ness
def run_non_FA(DTItag):
    """
    The Pipeline to run to extract non-FA values (MD, AD or RD)
    """
    O_dir = os.path.join(outputdir,tag)
    O_dir_orig = os.path.join(O_dir, 'origdata')
    dm.utils.makedirs(O_dir)

    if DTItag == 'MD':
        image_i = inputbase + '_' + DTItag + '.nii.gz'
        image_o = os.path.join(O_dir_orig,image_noext + '_' + DTItag + '.nii.gz')
        # copy over the MD image if not done already
        if os.path.isfile(image_o) == False:
            docmd(['cp',image_i,image_o])

    if DTItag == 'AD':
        image_i = inputbase + '_L1.nii.gz'
        image_o = os.path.join(O_dir_orig,image_noext + '_' + DTItag + '.nii.gz')
        # copy over the AD image - this is _L1 in dti-fit
        if os.path.isfile(image_o) == False:
            docmd(['cp',image_i,image_o])

    if DTItag == 'RD':
        image_l2 = inputbase + '_L2.nii.gz'
        image_l3 = inputbase + '_L3.nii.gz'
        image_o = os.path.join(O_dir_orig,image_noext + '_' + DTItag + '.nii.gz')
        # create the RD image as an average of '_L2' and '_L3' images from dti-fit
        if os.path.isfile(image_o) == False:
            docmd(['fslmaths', image_l2, '–add', image_l3, '-div', '2', image_o])


    masked =    os.path.join(O_dir,image_noext + '_' + DTItag + '.nii.gz')
    to_target = os.path.join(O_dir,image_noext + '_' + DTItag + 'to_target.nii.gz')
    skel =      os.path.join(O_dir, image_noext + '_' + DTItag +'skel.nii.gz')
    csvout1 =   os.path.join(ROIoutdir, image_noext + '_' + DTItag + 'skel_ROIout')
    csvout2 =   os.path.join(ROIoutdir, image_noext + '_' + DTItag + 'skel_ROIout_avg')

    ## mask with subjects FA mask
    docmd(['fslmaths', image_o, '-mas', \
      os.path.join(outputdir,'FA', image_noext + '_FA_mask.nii.gz') \
      masked)])

    # applywarp calculated for FA map
    docmd(['applywarp', '-i', masked), \
        '-o', to_target,
        '-r', os.path.join(outputdir,'FA', 'target')
        '-w', os.path.join(O_dir, image_noext + 'FA_to_target_warp.nii.gz'))

    ## tbss_skeleton step
    docmd(['tbss_skeleton', \
          '-i', tbss_skeleton_input, \
          '-s', tbss_skeleton_alt, \
          '-p', str(skel_thresh), distancemap, search_rule_mask,
           to_target, skel])

    ## ROI extract
    docmd([os.path.join(ENIGMAHOME,'singleSubjROI_exe'),
              os.path.join(ENIGMAHOME,'ENIGMA_look_up_table.txt'), \
              os.path.join(ENIGMAHOME, 'ENIGMA_DTI_FA_skeleton.nii.gz'), \
              os.path.join(ENIGMAHOME, 'JHU-WhiteMatter-labels-1mm.nii.gz'), \
              csvout1, skel])

    ## ROI average
    docmd([os.path.join(ENIGMAHOME, 'averageSubjectTracts_exe'), csvout1 + '.csv', csvout2 + '.csv'])

## run the pipeline for MD - if asked
if CALC_MD | CALC_ALL: == True:
    run_non_FA('MD')

## run the pipeline for AD and RD - if asked
if CALC_ALL:
    run_non_FA('AD')
    run_non_FA('RD')

###############################################################################
os.putenv('SGE_ON','true')
print("Done !!")
