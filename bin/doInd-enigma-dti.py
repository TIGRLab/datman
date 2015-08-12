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
  --MD-image <MD.nii>      Option to process MD image as well (give full path to file)
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
FAmap           = arguments['<FAmap.nii.gz>']
MDmap           = arguments['--MD-image']
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

# note - original version not using SGE within FSL
#export SGE_ON="false"    # for now, don't use SGE because it complicates things

ENIGMAHOME = os.getenv('ENIGMAHOME')
if ENIGMAHOME==None:
    sys.exit("ENIGMAHOME environment variable is undefined. Try again.")
FSLDIR = os.getenv('FSLDIR')
if FSLDIR==None:
    sys.exit("FSLDIR environment variable is undefined. Try again.")
if os.path.isfile(FAmap) == False:
    sys.exit("Input file {} doesn't exist.".format(FAmap))
if PROCESS_MD == True:
    if os.path.isfile(MDmap) == False:
      sys.exit("Input file {} doesn't exist.".format(MDmap))

# make some output directories
outputdir = os.path.abspath(outputdir)

## if nifti input is not inside the outputdir than copy it here
FAimage = os.path.basename(FAmap)
FAimage = FAimage.replace('_FA','') ## removing the _FA part so that TBSS can work for other file types
FAimage_noext = FAimage.replace(dm.utils.get_extension(FAimage),'')


## These are the links to some templates and settings from enigma
skel_thresh = 0.049
distancemap = os.path.join(ENIGMAHOME,'ENIGMA_DTI_FA_skeleton_mask_dst.nii.gz')
search_rule_mask = os.path.join(FSLDIR,'data','standard','LowerCingulum_1mm.nii.gz')
tbss_skeleton_input = os.path.join(ENIGMAHOME,'ENIGMA_DTI_FA.nii.gz')
tbss_skeleton_alt = os.path.join(ENIGMAHOME, 'ENIGMA_DTI_FA_skeleton_mask.nii.gz')
ROIoutdir = os.path.join(outputdir, 'ROI')
dm.utils.makedirs(ROIoutdir)
csvout1 = os.path.join(ROIoutdir, FAimage_noext + '_FA_to_target_FAskel_ROIout')
csvout2 = os.path.join(ROIoutdir, FAimage_noext + '_FA_to_target_FAskel_ROIout_avg')
FAskel = os.path.join(outputdir,'FA', FAimage_noext + '_FA_to_target_FAskel.nii.gz')
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
def run_non_FA(image,DTItag):
    """
    The Pipeline to run to extract non-FA values (ex. MD, L1)

    Inputs:
    image        the full path to the image in dti-fit
    DTI-tag      the string that identifies the type (i.e. 'MD', 'L1'...)
    """
    O_dir = os.path.join(outputdir,DTItag)
    dm.utils.makedirs(O_dir)
    Oimage = FAimage ## for this to work - FA and MD need to have the same names (in different folders)
    image_noext = FAimage_noext
    if os.path.isfile(os.path.join(O_dir,Oimage)) == False:
        docmd(['cp',image,os.path.join(O_dir,Oimage)])

    skel = os.path.join(outputdir,'FA', image_noext + '_' + DTItag +'skel.nii.gz')
    csvout1 = os.path.join(ROIoutdir, image_noext + '_' + DTItag + 'skel_ROIout')
    csvout2 = os.path.join(ROIoutdir, image_noext + '_' + DTItag + 'skel_ROIout_avg')

    ## run tbss_1_preproc on the MDimage to rescale it
    os.chdir(O_dir)
    docmd(['tbss_1_preproc', Oimage])

    ##move the output of tbss_1_preproc back up on level and rename it
    docmd(['mv', 'FA/' + image_noext + '_FA.nii.gz', Oimage])

    ##now run tbss_non_FA to Skeletonize it
    os.chdir(outputdir)
    docmd(['tbss_non_FA', DTItag])

    ## tbss_skeleton step
    docmd(['tbss_skeleton', \
          '-i', tbss_skeleton_input, \
          '-s', tbss_skeleton_alt, \
          '-p', str(skel_thresh), distancemap, search_rule_mask,
           'FA/' + FAimage_noext + '_to_target_' + DTItag + '.nii.gz',
           skel])

    ## ROI extract
    docmd([os.path.join(ENIGMAHOME,'singleSubjROI_exe'),
              os.path.join(ENIGMAHOME,'ENIGMA_look_up_table.txt'), \
              os.path.join(ENIGMAHOME, 'ENIGMA_DTI_FA_skeleton.nii.gz'), \
              os.path.join(ENIGMAHOME, 'JHU-WhiteMatter-labels-1mm.nii.gz'), \
              csvout1, skel])

    ## ROI average
    docmd([os.path.join(ENIGMAHOME, 'averageSubjectTracts_exe'), csvout1 + '.csv', csvout2 + '.csv'])

## run the pipeline for MD - if asked
if PROCESS_MD == True:
    run_non_FA(MDmap,'MD')

###############################################################################
os.putenv('SGE_ON','true')
print("Done !!")
