#!/usr/bin/env python
"""
This run ENIGMA DTI pipeline on one FA map.
This was made to be called from dm-proc-engimadti.py.

Usage:
  doInd-enigma-dti.py [options] <outputdir> <FAmap>

Arguments:
    <outputdir>        Top directory for the output file structure
    <FAmap>            Full path to input FA map to process

Options:
  --calc-MD                Option to process MD image as well
  --calc-all               Option to process MD, AD and RD
  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run
  -h,--help                Print this help

DETAILS
This run ENIGMA DTI pipeline on one FA map.
This was made to be called from dm-proc-engimadti.py - which runs enigma-dti protocol
for a group of subjects (or study) - then creates a group csv output and QC.

We recommend specifying an outputdir that doesn't yet exist (ex. enigmaDTI/<subjectID/).
This script will create the ouputdir and copy over the relevant inputs.
Why? Because this meant to work in directory with only ONE FA image!! (ex. enigmaDTI/<subjectID/).
Having more than one FA image in the outputdir would lead to crazyness during the TBSS steps.
So, the script will not run if more than one FA image (or the wrong FAimage) is present in the outputdir.

By default, this extracts FA values for each ROI in the atlas.
To extract MD as well, call with the "--calc-MD" option.
To extract FA, MD, RD and AD, call with the "--calc-all" option.

Requires ENIGMA dti enviroment to be set (for example):
module load FSL/5.0.7 R/3.1.1 ENIGMA-DTI/2015.01

also requires datman python enviroment.

Written by Erin W Dickie, July 30 2015
Adapted from ENIGMA_MASTER.sh - Generalized October 2nd David Rotenberg Updated Feb 2015 by JP+TB
Runs pipeline outlined by enigma-dti:
http://enigma.ini.usc.edu/protocols/dti-protocols/
"""
from docopt import docopt
import pandas as pd
import datman as dm
import datman.utils
import datman.scanid
import glob
import os
import sys

arguments       = docopt(__doc__)
outputdir       = arguments['<outputdir>']
FAmap           = arguments['<FAmap>']
CALC_MD         = arguments['--calc-MD']
CALC_ALL        = arguments['--calc-all']
VERBOSE         = arguments['--verbose']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']

if DEBUG:
    print arguments

# check that ENIGMAHOME environment variable exists
ENIGMAHOME = os.getenv('ENIGMAHOME')
if ENIGMAHOME==None:
    sys.exit("ENIGMAHOME environment variable is undefined. Try again.")
# check that FSLDIR environment variable exists
FSLDIR = os.getenv('FSLDIR')
if FSLDIR==None:
    sys.exit("FSLDIR environment variable is undefined. Try again.")
# check that the input FA map exists
if os.path.isfile(FAmap) == False:
    sys.exit("Input file {} doesn't exist.".format(FAmap))
# check that the input MD map exists - if MD CALC chosen
if CALC_MD | CALC_ALL:
    MDmap = FAmap.replace('FA.nii.gz','MD.nii.gz')
    if os.path.isfile(MDmap) == False:
      sys.exit("Input file {} doesn't exist.".format(MDmap))
# check that the input L1, L2, and L3 maps exists - if CALC_ALL chosen
if CALC_ALL:
    for L in ['L1.nii.gz','L2.nii.gz','L3.nii.gz']:
        Lmap = FAmap.replace('FA.nii.gz', L)
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
image_noext = os.path.basename(FAmap.replace('_FA.nii.gz',''))
FAimage = image_noext + '.nii.gz'
csvout1 = os.path.join(ROIoutdir, image_noext + '_FAskel_ROIout')
csvout2 = os.path.join(ROIoutdir, image_noext + '_FAskel_ROIout_avg')
FAskel = os.path.join(outputdir,'FA', image_noext + '_FAskel.nii.gz')
###############################################################################
## setting up
## if teh outputfile is not inside the outputdir than copy is there
outdir_niis = glob.glob(outputdir + '/*.nii.gz') + glob.glob(outputdir + '*.nii')
if len(outdir_niis) == 0:
    dm.utils.run(['cp',FAmap,os.path.join(outputdir,FAimage)])
else:
    # if more than one FA image is present in outputdir...we have a problem.
    sys.exit("Ouputdir already contains nii images..bad news..exiting")

## cd into the output directory
os.chdir(outputdir)
os.putenv('SGE_ON','false')
###############################################################################
print("TBSS STEP 1")

dm.utils.run(['tbss_1_preproc', FAimage])

###############################################################################
print("TBSS STEP 2")
dm.utils.run(['tbss_2_reg', '-t', os.path.join(ENIGMAHOME,'ENIGMA_DTI_FA.nii.gz')])

###############################################################################
print("TBSS STEP 3")
dm.utils.run(['tbss_3_postreg','-S'])

###############################################################################
print("Skeletonize...")
# Note many of the options for this are printed at the top of this script
dm.utils.run(['tbss_skeleton', \
      '-i', tbss_skeleton_input, \
      '-s', tbss_skeleton_alt, \
      '-p', str(skel_thresh), distancemap, search_rule_mask,
       'FA/' + image_noext + '_FA_to_target.nii.gz',
       FAskel])

###############################################################################
print("Convert skeleton datatype to 'float'...")
dm.utils.run(['fslmaths', FAskel, '-mul', '1', FAskel, '-odt', 'float'])

###############################################################################
print("ROI part 1...")
## note - right now this uses the _exe for ENIGMA - can probably rewrite this with nibabel
dm.utils.run([os.path.join(ENIGMAHOME,'singleSubjROI_exe'),
          os.path.join(ENIGMAHOME,'ENIGMA_look_up_table.txt'), \
          os.path.join(ENIGMAHOME, 'ENIGMA_DTI_FA_skeleton.nii.gz'), \
          os.path.join(ENIGMAHOME, 'JHU-WhiteMatter-labels-1mm.nii'), \
          csvout1, FAskel])

###############################################################################
## part 2 - loop through all subjects to create ROI file
##			removing ROIs not of interest and averaging others
##          note: also using the _exe files to do this at the moment
print("ROI part 2...")
dm.utils.run([os.path.join(ENIGMAHOME, 'averageSubjectTracts_exe'), csvout1 + '.csv', csvout2 + '.csv'])

##############################################################################
## Now process the MD if that option was asked for
## if processing MD also set up for MD-ness
def run_non_FA(DTItag):
    """
    The Pipeline to run to extract non-FA values (MD, AD or RD)
    """
    O_dir = os.path.join(outputdir,DTItag)
    O_dir_orig = os.path.join(O_dir, 'origdata')
    dm.utils.makedirs(O_dir_orig)

    if DTItag == 'MD':
        image_i = FAmap.replace('FA.nii.gz','MD.nii.gz')
        image_o = os.path.join(O_dir_orig,image_noext + '_' + DTItag + '.nii.gz')
        # copy over the MD image if not done already
        if os.path.isfile(image_o) == False:
            dm.utils.run(['cp',image_i,image_o])

    if DTItag == 'AD':
        image_i = FAmap.replace('FA.nii.gz','L1.nii.gz')
        image_o = os.path.join(O_dir_orig,image_noext + '_' + DTItag + '.nii.gz')
        # copy over the AD image - this is _L1 in dti-fit
        if os.path.isfile(image_o) == False:
            dm.utils.run(['cp',image_i,image_o])

    if DTItag == 'RD':
        imageL2 = FAmap.replace('FA.nii.gz','L2.nii.gz')
        imageL3 = FAmap.replace('FA.nii.gz','L3.nii.gz')
        image_o = os.path.join(O_dir_orig,image_noext + '_' + DTItag + '.nii.gz')
        # create the RD image as an average of '_L2' and '_L3' images from dti-fit
        if os.path.isfile(image_o) == False:
            dm.utils.run(['fslmaths', imageL2, '-add', imageL3, '-div', "2", image_o])

    masked =    os.path.join(O_dir,image_noext + '_' + DTItag + '.nii.gz')
    to_target = os.path.join(O_dir,image_noext + '_' + DTItag + '_to_target.nii.gz')
    skel =      os.path.join(O_dir, image_noext + '_' + DTItag +'skel.nii.gz')
    csvout1 =   os.path.join(ROIoutdir, image_noext + '_' + DTItag + 'skel_ROIout')
    csvout2 =   os.path.join(ROIoutdir, image_noext + '_' + DTItag + 'skel_ROIout_avg')

    ## mask with subjects FA mask
    dm.utils.run(['fslmaths', image_o, '-mas', \
      os.path.join(outputdir,'FA', image_noext + '_FA_mask.nii.gz'), \
      masked])

    # applywarp calculated for FA map
    dm.utils.run(['applywarp', '-i', masked, \
        '-o', to_target, \
        '-r', os.path.join(outputdir,'FA', 'target'),\
        '-w', os.path.join(outputdir,'FA', image_noext + '_FA_to_target_warp.nii.gz')])

    ## tbss_skeleton step
    dm.utils.run(['tbss_skeleton', \
          '-i', tbss_skeleton_input, \
          '-s', tbss_skeleton_alt, \
          '-p', str(skel_thresh), distancemap, search_rule_mask,
           to_target, skel])

    ## ROI extract
    dm.utils.run([os.path.join(ENIGMAHOME,'singleSubjROI_exe'),
              os.path.join(ENIGMAHOME,'ENIGMA_look_up_table.txt'), \
              os.path.join(ENIGMAHOME, 'ENIGMA_DTI_FA_skeleton.nii.gz'), \
              os.path.join(ENIGMAHOME, 'JHU-WhiteMatter-labels-1mm.nii.gz'), \
              csvout1, skel])

    ## ROI average
    dm.utils.run([os.path.join(ENIGMAHOME, 'averageSubjectTracts_exe'),
                  csvout1 + '.csv', csvout2 + '.csv'])

## run the pipeline for MD - if asked
if CALC_MD | CALC_ALL:
    run_non_FA('MD')

## run the pipeline for AD and RD - if asked
if CALC_ALL:
    run_non_FA('AD')
    run_non_FA('RD')

###############################################################################
os.putenv('SGE_ON','true')
print("Done !!")
