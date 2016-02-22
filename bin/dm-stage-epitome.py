#!/usr/bin/env python
"""
This copies files from the archive into the epitome folder structure.

Usage:
  dm-stage-epitome.py [options] <input-nii-dir> <outputdir>

Arguments:
    <input-nii-dir>          Top directory for dti-fit output
    <outputdir>              Top directory for the output of enigma DTI


Options:
    --func-tags LIST         List of expected tags for functional data
    --func-counts LIST       List of expected files matching length of func-tags
    --QC-transfer QCFILE     QC checklist file - if this option is given than only QCed participants will be processed.
    --sym-link               Create symbolik link to the files in data-2.0 (default is to copy file)
    --debug                  Debug logging in Erin's very verbose style
    -n,--dry-run             Dry run
    -h, --help               Show help

DETAILS
This copies files from the archive into the epitome folder structure.
It's meant to be run before transfering data onto a cluster where it will be processed.

Example: To set up Imitate and Observe Task Runs from COBDY for analysis:
dm-stage-epitome.py --sym-link \
    --func-tags "IMI,OBS" \
    --func-counts "1,1" \
    --QC-transfer /archive/data-2.0/COGBDY/metadata/checklist.csv \
    /archive/data-2.0/COGBDY/data/nii/ \
    /scratch/edickie/COGBDY_imob/

Written by Erin W. Dickie, November 17, 2015
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
import tempfile
import shutil
import filecmp
import difflib

arguments       = docopt(__doc__)
inputdir        = arguments['<input-nii-dir>']
outputdir       = arguments['<outputdir>']
rawQCfile       = arguments['--QC-transfer']
functagsarg     = arguments['--func-tags']
funccountsarg   = arguments['--func-counts']
SYMLINK         = arguments['--sym-link']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']

if DEBUG: print arguments
#set default tag values
QCedTranfer = False if rawQCfile == None else True


### Erin's little function for running things in the shell
def docmd(cmdlist):
    "sends a command (inputed as a list) to the shell"
    if DEBUG: print ' '.join(cmdlist)
    if not DRYRUN: subprocess.call(cmdlist)

# need to find the t1 weighted scan and update the checklist
def find_and_copy_tagnii(colname, archive_tag, expected_count):
    """
    for a particular scan type, will look for new files in the inputdir
    and copy them to the output structure
    """
    for i in range(0,len(checklist)):
    	#if link doesn't exist
    	targetdir = os.path.join(outputdir, checklist['id'][i],archive_tag, 'SESS01', 'RUN01')
    	if os.path.exists(targetdir)==False:
            niidir = os.path.join(inputdir,checklist['id'][i])
    	    #if mnc name not in checklist
            if pd.isnull(checklist[colname][i]):
                niifiles = []
                for fname in os.listdir(niidir):
                    if archive_tag in fname:
                        niifiles.append(fname)
                if DEBUG: print "Found {} {} in {}".format(len(niifiles),archive_tag,niidir)
                if len(niifiles) == expected_count:
                    checklist[colname][i] = ';'.join(niifiles)
                elif len(niifiles) > expected_count:
                    checklist['notes'][i] = "> {} {} found".format(expected_count,archive_tag)
                elif len(niifiles) < expected_count:
                    checklist['notes'][i] = "Not enough {} found.".format(archive_tag)
            # make the link
            if pd.isnull(checklist[colname][i])==False:
                niifiles = checklist[colname][i].split(';')
                for niifile in niifiles:
                    niipath = os.path.abspath(os.path.join(niidir,niifile))
                    targetpath = os.path.abspath(os.path.join(targetdir,niifile))
                    docmd(['mkdir','-p',targetdir])
                    if SYMLINK:
                        os.symlink(niipath, targetpath)
                    else:
                        docmd(['cp', niipath, targetdir])


####set checklist dataframe structure here
#because even if we do not create it - it will be needed for newsubs_df (line 80)
def loadchecklist(checklistfile,subjectlist):
    """
    Reads the checklistfile (normally called ENIGMA-DTI-checklist.csv)
    if the checklist csv file does not exit, it will be created.

    This also checks if any subjects in the subjectlist are missing from the checklist,
    (checklist.id column)
    If so, they are appended to the bottom of the dataframe.
    """

    cols = ['id', 'T1', 'date_ran','qc_rator', 'qc_rating', 'notes']
    for i in range(len(func_tags)): cols.insert((i + 2),func_tags[i])


    if DEBUG: print("cols: {}".format(cols))

    # if the checklist exists - open it, if not - create the dataframe
    if os.path.isfile(checklistfile):
    	checklist = pd.read_csv(checklistfile, sep=',', dtype=str, comment='#')
    else:
    	checklist = pd.DataFrame(columns = cols)

    # new subjects are those of the subject list that are not in checklist.id
    newsubs = list(set(subjectlist) - set(checklist.id))

    # add the new subjects to the bottom of the dataframe
    newsubs_df = pd.DataFrame(columns = cols, index = range(len(checklist),len(checklist)+len(newsubs)))
    newsubs_df.id = newsubs
    checklist = checklist.append(newsubs_df)

    # return the checklist as a pandas dataframe
    return(checklist)

def get_qced_subjectlist(qcchecklist):
    """
    reads the QC checklist and returns a list of all subjects who have passed QC
    """
    qcedlist = []
    if os.path.isfile(rawQCfile):
        with open(rawQCfile) as f:
            for line in f:
                line = line.strip()
                if len(line.split(' ')) > 1:
                    pdf = line.split(' ')[0]
                    subid = pdf.replace('.pdf','')[3:]
                    qcedlist.append(subid)
    else:
        sys.exit("QC file for transfer not found. Try again.")
    ## return the qcedlist (as a list)
    return qcedlist


######## NOW START the 'main' part of the script ##################
## make the putput directory if it doesn't exist
outputdir = os.path.abspath(outputdir)
func_tags = functagsarg.split(",")
func_counts = map(int, funccountsarg.split(","))


## find those subjects in input who have not been processed yet
subids_in_inputdir = dm.utils.get_subjects(inputdir)
subids_in_inputdir = [ v for v in subids_in_inputdir if "PHA" not in v ] ## remove the phantoms from the list
if QCedTranfer:
    # if a QC checklist exists, than read it and only process those participants who passed QC
    qcedlist = get_qced_subjectlist(rawQCfile)
    subids_in_inputdir = list(set(subids_in_inputdir) & set(qcedlist)) ##now only add it to the filelist if it has been QCed

## create an checklist for the FA maps
checklistfile = os.path.normpath(outputdir+'/epitome-checklist.csv')
checklist = loadchecklist(checklistfile,subids_in_inputdir)

## look for new subs using FA_tag and tag2
find_and_copy_tagnii('T1', 'T1', 1)
for i in range(len(func_tags)):
    find_and_copy_tagnii(func_tags[i], func_tags[i], func_counts[i])


## write the checklist out to a file
checklist.to_csv(checklistfile, sep=',', index = False)
