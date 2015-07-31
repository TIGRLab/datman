#!/usr/bin/env python
"""
This run ENIGMA DTI pipeline on FA maps

Usage:
  dm-proc-CIVET.py [options] <outputdir> <FAmap.nii.gz>

Arguments:
    <outputdir>        Top directory for the output file structure
    <FAmap.nii.gz>     Fractional Anisotropy Image in nifti format to start from

Options:
  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run

DETAILS
Requires ENIGMA dti enviroment to be set (for example):
module load FSL/5.0.7 R/3.1.1 ENIGMA-DTI/2015.01

Note: to force this to work only for one participant - we can just make sure only one participants is in the outputdir

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
## TBSS step 1
print("TBSS STEP 1")
docmd(['tbss_1_preproc', FAimage])

###############################################################################
print("TBSS STEP 2")
docmd(['tbss_2_reg', '-t', os.path.join(ENIGMAHOME,'ENIGMA_DTI_FA.nii.gz')])

#echo "Waiting for TBSS stage 2 to complete..."
## || true needed to work around having "set -e" turned on, since grep
## exits with 1 if nothing is matched
#pause_crit=$(qstat | grep tbss_2_reg || true)
#
#while [ -n "$pause_crit" ]; do
#    pause_crit=$(qstat | grep tbss_2_reg || true)
#    sleep 20
#done

###############################################################################
print("TBSS STEP 3")
docmd(['tbss_3_postreg','-S'])
docmd(['cp', FA/*FA_to_target.nii.gz, FA_to_target_dir])


###############################################################################
print("Skeletonize...")
skel_thresh = 0.049
distancemap = os.path.join(ENIGMAHOME,'ENIGMA_DTI_FA_skeleton_mask_dst.nii.gz')
search_rule_mask = os.path.join(FSLDIR,'data','standard','LowerCingulum_1mm.nii.gz')

if [ ! -e .done_tbss_skel ]; then
  for a in FA_to_target/*; do
    sub=$(basename ${a} .nii.gz)
docmd('tbss_skeleton', \
      '-i', os.path.join(ENIGMAHOME,'ENIGMA_DTI_FA.nii.gz'), \
      '-s', os.path.join(ENIGMAHOME, 'ENIGMA_DTI_FA_skeleton_mask.nii.gz'), \
      '-p', str(skel_thresh), distancemap, search_rule_mask,
       ${a}, os.path.join(FA_skels/${sub}_FAskel


###############################################################################
echo "Convert skeleton datatype to 'float'..."
if [ ! -e .done_fslmaths ]; then
	for sub in FA_skels/* ;do
		fslmaths $sub -mul 1 $sub -odt float
	done
  touch .done_fslmaths
fi

###############################################################################
echo "ROI part 1..."

# make directory for ROI_out.csv files
dir01=ROI_part1
mkdir -p $dir01

if [ ! -e .done_ROI_part1 ]; then
  for subject in FA_skels/*.nii.gz; do
    base=$(basename $subject .nii.gz);
    ${ENIGMAHOME}/singleSubjROI_exe \
      ${ENIGMAHOME}/ENIGMA_look_up_table.txt \
      ${ENIGMAHOME}/ENIGMA_DTI_FA_skeleton.nii.gz \
      ${ENIGMAHOME}/JHU-WhiteMatter-labels-1mm.nii.gz \
      ${dir01}/${base}_ROIout ${subject}
  done
  touch .done_ROI_part1
fi


###############################################################################
## part 2 - loop through all subjects to create ROI file
##			removing ROIs not of interest and averaging others
echo "ROI part 2..."

# make an output directory for all files
dir02=ROI_part2
mkdir -p $dir02

if [ ! -e .done_ROI_part2 ]; then
  rm -f subjectList.csv
  for subject in FA_skels/*.nii.gz; do
    base=$(basename $subject .nii.gz);

    ${ENIGMAHOME}/averageSubjectTracts_exe \
      ${dir01}/${base}_ROIout.csv \
      ${dir02}/${base}_ROIout_avg.csv

    # create subject list for part 3
    # subjectID, location of ROIout_avg.csv file for subject
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
