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
  --FA-tag STR             String used to identify FA maps within DTI-fit input (default = '_FA'))
  --FA-tag2 STR            Optional second used to identify FA maps within DTI-fit input (on top of '--FA-tag', ex. 'DTI-60'))
  --QC-transfer QCFILE     QC checklist file - if this option is given than only QCed participants will be processed.
  --no-newsubs             Do not link or submit new subjects - used when this script is recursively called from the concat script
  --use-test-datman        Use the version of datman in Erin's test environment. (default is '/archive/data-2.0/code/datman.module')
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
import os
import sys
import subprocess
import datetime
import tempfile
import shutil
import filecmp
import difflib

arguments       = docopt(__doc__)
dtifit_dir      = arguments['<input-dtifit-dir>']
outputdir       = arguments['<outputdir>']
rawQCfile       = arguments['--QC-transfer']
FA_tag          = arguments['--FA-tag']
FA_tag2         = arguments['--FA-tag2']
NO_NEWSUBS      = arguments['--no-newsubs']
TESTDATMAN      = arguments['--use-test-datman']
VERBOSE         = arguments['--verbose']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']

if DEBUG: print arguments
#set default tag values
if FA_tag == None: FA_tag = '_FA.nii'
QCedTranfer = False if rawQCfile == None else True

## set the basenames of the two run scripts
runenigmash_name = 'run_engimadti.sh'
runconcatsh_name = 'concatresults.sh'

### Erin's little function for running things in the shell
def docmd(cmdlist):
    "sends a command (inputed as a list) to the shell"
    if DEBUG: print ' '.join(cmdlist)
    if not DRYRUN: subprocess.call(cmdlist)

# need to find the t1 weighted scan and update the checklist
def findFAmaps(archive_tag,archive_tag2):
    """
    will look for new files in the inputdir
    and add them to a list for the processing

    archive_tag -- filename tag that can be used for search (i.e. '_T1_')
    """
    for i in range(0,len(checklist)):
        FAdir = os.path.join(dtifit_dir,checklist['id'][i])
	    #if FA name not in checklist
        if pd.isnull(checklist['FA_nii'][i]):
            FAfiles = []
            for fname in os.listdir(FAdir):
                if archive_tag in fname:
                    if archive_tag2 != None:
                        if archive_tag2 in fname:
                            FAfiles.append(fname)
                    else:
                        FAfiles.append(fname)
            if DEBUG: print "Found {} {} in {}".format(len(FAfiles),archive_tag,FAdir)
            if len(FAfiles) == 1:
                checklist['FA_nii'][i] = FAfiles[0]
            elif len(FAfiles) > 1:
                checklist['notes'][i] = "> 1 {} found".format(archive_tag)
            elif len(FAfiles) < 1:
                checklist['notes'][i] = "No {} found.".format(archive_tag)


### build a template .sh file that gets submitted to the queue
def makeENIGMArunsh(filename):
    """
    builds a script in the outputdir (run.sh)
    that gets submitted to the queue for each participant (in the case of 'doInd')
    or that gets held for all participants and submitted once they all end (the concatenating one)
    """
    bname = os.path.basename(filename)
    if bname == runenigmash_name:
        ENGIMASTEP = 'doInd'
    if bname == runconcatsh_name:
        ENGIMASTEP = 'concat'

    #open file for writing
    enigmash = open(filename,'w')
    enigmash.write('#!/bin/bash\n\n')

    enigmash.write('# SGE Options\n')
    enigmash.write('#$ -S /bin/bash\n')
    enigmash.write('#$ -q main.q\n')
    enigmash.write('#$ -l mem_free=6G,virtual_free=6G\n\n')

    enigmash.write('#source the module system\n')
    enigmash.write('source /etc/profile\n\n')

    enigmash.write('## this script was created by dm-proc-engimadti.py\n\n')
    ## can add section here that loads chosen CIVET enviroment
    enigmash.write('##load the ENIGMA DTI enviroment\n')
    enigmash.write('module load FSL/5.0.7 R/3.1.1 ENIGMA-DTI/2015.01\n\n')
    if TESTDATMAN:
        enigmash.write('module load /projects/edickie/privatemodules/datman/edickie\n\n')
    else:
        enigmash.write('module load /archive/data-2.0/code/datman.module\n\n')

    ## add a line that will read in the subject id
    enigmash.write('OUTDIR=${1}\n')

    if ENGIMASTEP == 'doInd':
        enigmash.write('FAMAP=${2}\n')
        ## add the engima-dit command
        enigmash.write('\ndoInd-enigma-dti.py ${OUTDIR} ${FAMAP}')

    if ENGIMASTEP == 'concat':
        enigmash.write('DTIFITDIR=${2}\n')
        ## call this script to update the results spreadsheet
        enigmash.write('\ndm-proc-engimadti.py --no-newsubs ')
        if TESTDATMAN: enigmash.write('--use-test-datman ')
        enigmash.write('${DTIFITDIR} ${OUTDIR}')
        ## add the engima-concat command
        enigmash.write('\nconcatcsv-enigmadti.py ${OUTDIR}')

    #and...don't forget to close the file
    enigmash.close()

### check the template .sh file that gets submitted to the queue to make sure option haven't changed
def checkrunsh(filename):
    """
    write a temporary (run.sh) file and than checks it againts the run.sh file already there
    This is used to double check that the pipeline is not being called with different options
    """
    tempdir = tempfile.mkdtemp()
    tmprunsh = os.path.join(tempdir,os.path.basename(filename))
    makeENIGMArunsh(tmprunsh)
    if filecmp.cmp(filename, tmprunsh):
        if DEBUG: print("{} already written - using it".format(filename))
    else:
        # If the two files differ - then we use difflib package to print differences to screen
        print('#############################################################\n')
        print('# Found differences in {} these are marked with (+) '.format(filename))
        print('#############################################################')
        with open(filename) as f1, open(tmprunsh) as f2:
            differ = difflib.Differ()
            print(''.join(differ.compare(f1.readlines(), f2.readlines())))
        sys.exit("\nOld {} doesn't match parameters of this run....Exiting".format(filename))
    shutil.rmtree(tempdir)


######## NOW START the 'main' part of the script ##################
## make the putput directory if it doesn't exist
outputdir = os.path.abspath(outputdir)
log_dir = os.path.join(outputdir,'logs')
run_dir = os.path.join(outputdir,'bin')
dm.utils.makedirs(log_dir)
dm.utils.makedirs(run_dir)

## writes a standard ENIGMA-DTI running script for this project (if it doesn't exist)
## the script requires a OUTDIR and FAMAP variables - as arguments $1 and $2
## also write a standard script to concatenate the results at the end (script is held while subjects run)
for runfilename in [runenigmash_name,runconcatsh_name]:
    runsh = os.path.join(run_dir,runfilename)
    if os.path.isfile(runsh):
        ## create temporary run file and test it against the original
        checkrunsh(runsh)
    else:
        ## if it doesn't exist, write it now
        makeENIGMArunsh(runsh)

####set checklist dataframe structure here
#because even if we do not create it - it will be needed for newsubs_df (line 80)
cols = ['id', 'FA_nii', 'date_ran', 'run',\
    'ACR', 'ACR-L', 'ACR-R', 'ALIC', 'ALIC-L', 'ALIC-R', 'AverageFA', \
    'BCC', 'CC', 'CGC', 'CGC-L', 'CGC-R', 'CGH', 'CGH-L', 'CGH-R', 'CR', \
    'CR-L', 'CR-R', 'CST', 'CST-L', 'CST-R', 'EC', 'EC-L', 'EC-R', 'FX', \
    'FX/ST-L', 'FX/ST-R', 'FXST', 'GCC', 'IC', 'IC-L', 'IC-R', 'IFO', \
    'IFO-L', 'IFO-R', 'PCR', 'PCR-L', 'PCR-R', 'PLIC', 'PLIC-L', 'PLIC-R', \
    'PTR', 'PTR-L', 'PTR-R', 'RLIC', 'RLIC-L', 'RLIC-R', 'SCC', 'SCR', \
    'SCR-L', 'SCR-R', 'SFO', 'SFO-L', 'SFO-R', 'SLF', 'SLF-L', 'SLF-R', \
    'SS', 'SS-L', 'SS-R', 'UNC', 'UNC-L', 'UNC-R', \
    'qc_rator', 'qc_rating', 'notes']

# if the checklist exists - open it, if not - create the dataframe
checklistfile = os.path.normpath(outputdir+'/ENIGMA-DTI-results.csv')
if os.path.isfile(checklistfile):
	checklist = pd.read_csv(checklistfile, sep=',', dtype=str, comment='#')
else:
	checklist = pd.DataFrame(columns = cols)

## load the projects data export checklist so that we can check if the data has been QCed
 #open a flag to say that this is a project with a qc checklist
if QCedTranfer ==  True:
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


## find those subjects in input who have not been processed yet and append to checklist
subids_in_dtifit = dm.utils.get_subjects(dtifit_dir)
subids_in_dtifit = [ v for v in subids_in_dtifit if "PHA" not in v ] ## remove the phantoms from the list
if QCedTranfer: subids_in_dtifit = list(set(subids_in_dtifit) & set(qcedlist)) ##now only add it to the filelist if it has been QCed
newsubs = list(set(subids_in_dtifit) - set(checklist.id))
newsubs_df = pd.DataFrame(columns = cols, index = range(len(checklist),len(checklist)+len(newsubs)))
newsubs_df.id = newsubs
checklist = checklist.append(newsubs_df)

# find the FA maps for each subject
if NO_NEWSUBS == False: findFAmaps(FA_tag,FA_tag2)

## now checkoutputs to see if any of them have been run
#if yes update spreadsheet
#if no submits that subject to the queue
jobnames = []
for i in range(0,len(checklist)):
    if checklist['run'][i] !="Y":
        subid = checklist['id'][i]
        # if all input files are found - check if an output exists
        if pd.isnull(checklist['FA_nii'][i])==False:
            ROIout = os.path.join(outputdir,subid,'ROI')
            # if no output exists than run engima-dti
            if os.path.exists(ROIout)== False:
                if NO_NEWSUBS == False:
                    os.chdir(run_dir)
                    soutput = os.path.join(outputdir,subid)
                    sFAmap = checklist['FA_nii'][i]
                    jobname = 'edti_' + subid
                    docmd(['qsub','-o', log_dir, \
                             '-N', jobname,  \
                             runenigmash_name, \
                             soutput, \
                             os.path.join(dtifit_dir,subid,sFAmap)])
                    checklist['date_ran'][i] = datetime.date.today()
                    jobnames.append(jobname)
            # if an full output exists - uptdate the CIVETchecklist
            elif len(os.listdir(ROIout)) == 2:
                    checklist['run'][i] = "Y"

### currently working on a consilidation script that gets run...
if len(jobnames) > 0:
    #if any subjects have been submitted - submit an extract consolidation job to run at the end
    os.chdir(run_dir)
    docmd(['qsub','-o', log_dir, \
        '-N', 'edti_results',  \
        '-hold_jid', ','.join(jobnames), \
        runconcatsh_name, \
        outputdir, dtifit_dir ])

## write the checklist out to a file
checklist.to_csv(checklistfile, sep=',', columns = cols, index = False)
