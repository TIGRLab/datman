#!/usr/bin/env python
"""
This run CIVET on stuff

Usage:
  dm-proc-CIVET.py [options] <inputpath> <targetpath> <prefix>

Arguments:
    <inputpath>      Path to input directory (usually a project directory inside /data-2.0)
    <targetpath>     Path to directory that will contain CIVET inputs (links) and outputs
    <prefix>         Prefix for CIVET input (see details)    `

Options:
  --multispectral          Use the T1W, T2W and PD images in pipeline (default = use only T1W)
  --1-Telsa                Use CIVET options for 1-Telsa data (default = 3T options)
  --CIVET-version-12       Use version 1.1.12 of CIVET (default  = 1.1.10)
  --T1-tag	STR			   Tag in filename that indicates it's a T1 (default = "_T1_")
  --T2-tag	STR			   Tag in filename that indicates it's a T2 (default = "_T2_")
  --PD-tag	STR			   Tag in filename that indicates it's a PD (default = "_PD_")
  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run

DETAILS
Runs CIVET in a rather organized way on all the participants within one project.
This script write a little script (runcivet.sh) within the output directory structure
that gets submitted to the queue for each subject. Subject's ID is passed into the qsub
command as a variable ('-v SUBJECT=<subid>').
The CIVET enviroment used (and all CIVET options) get's printed into the runcivet.sh script.
Also, this script creates and updates a checklist ('CIVETchecklist.csv') with what
participants have been run (on which .mnc file) and the date CIVET was ran.
The inputdir should be the project directory (inside data-2.0))
"""
from docopt import docopt
import pandas as pd
import datman as dm
import datman.utils
import datman.scanid
import os.path
import sys
import subprocess
import datetime

arguments       = docopt(__doc__)
inputpath       = arguments['<inputpath>']
targetpath      = arguments['<targetpath>']
prefix          = arguments['<prefix>']
MULTISPECTRAL   = arguments['--multispectral']
ONETESLA        = arguments['--1-Telsa']
CIVET12         = arguments['--CIVET-version-12']
VERBOSE         = arguments['--verbose']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']
T1_TAG          = arguments['--T1-tag']
T2_TAG          = arguments['--T2-tag']
PD_TAG          = arguments['--PD-tag']

if DEBUG: print arguments
#set default tag values
if T1_TAG == None: T1_TAG = '_T1_'
if T2_TAG == None: T2_TAG = '_T2_'
if PD_TAG == None: PD_TAG = '_PD_'

### Erin's little function for running things in the shell
def docmd(cmdlist):
    "sends a command (inputed as a list) to the shell"
    if DEBUG: print ' '.join(cmdlist)
    if not DRYRUN: subprocess.call(cmdlist)

# need to find the t1 weighted scan and update the checklist
def doCIVETlinking(colname, archive_tag, civet_ext):
    """
    for a particular scan type, will look for new files in the inputdir
    and link them inside civet_in using the CIVET convenstions
    Will also update the checklist will what files have been found
    (or notes is problems occur)

    colname -- the name of the column in the checklist to update ('mnc_t1', 'mnc_t2' or 'mnc_pd')
    archive_tag -- filename tag that can be used for search (i.e. '_T1_')
    civet_ext -- end of the link name (following CIVET guide) (i.e. '_t1.mnc')
    """
    for i in range(0,len(checklist)):
    	#if link doesn't exist
    	target = os.path.join(civet_in, prefix + '_' + checklist['id'][i] + civet_ext)
    	if os.path.exists(target)==False:
            mncdir = os.path.join(inputpath,'data','mnc',checklist['id'][i])
    	    #if mnc name not in checklist
            if pd.isnull(checklist[colname][i]):
                mncfiles = []
                for fname in os.listdir(mncdir):
                    if archive_tag in fname:
                        mncfiles.append(fname)
                if DEBUG: print "Found {} {} in {}".format(len(mncfiles),archive_tag,mncdir)
                if len(mncfiles) == 1:
                    checklist[colname][i] = mncfiles[0]
                elif len(mncfiles) > 1 & QCedTranfer:
                    meanmnc = [m for m in mncfiles if "mean" in m]
                    if len(meanmnc) == 1:
                        checklist[colname][i] = meanmnc[0]
                    else:
                        checklist['notes'][i] = "> 1 {} found".format(archive_tag)
                elif len(mncfiles) > 1 & QCedTranfer==False:
                    checklist['notes'][i] = "> 1 {} found".format(archive_tag)
                elif len(mncfiles) < 1:
                    checklist['notes'][i] = "No {} found.".format(archive_tag)
            # make the link
            if pd.isnull(checklist[colname][i])==False:
                mncpath = os.path.join(mncdir,checklist[colname][i])
                if DEBUG: print("linking {} to {}".format(mncpath, target))
                os.symlink(mncpath, target)

### build a template .sh file that gets submitted to the queue
def makeCIVETrunsh(filename):
    """
    builds a script in the CIVET directory (run.sh)
    that gets submitted to the queue for each participant
    """
    #open file for writing
    civetsh = open(filename,'w')
    civetsh.write('#!/bin/bash\n\n')
    civetsh.write('# SGE Options\n')
    civetsh.write('#$ -S /bin/bash\n')
    civetsh.write('#$ -q main.q\n')
    civetsh.write('#$ -l mem_free=6G,virtual_free=6G\n\n')
    civetsh.write('#source the module system\n')
    civetsh.write('source /etc/profile.d/modules.sh\n')
    civetsh.write('source /etc/profile.d/quarantine.sh\n\n')

    civetsh.write('## this script was created by dm-proc-CIVET.py\n\n')
    ## can add section here that loads chosen CIVET enviroment
    civetsh.write('##load the CIVET enviroment\n')
    if CIVET12:
        civetsh.write('module load CIVET/1.1.12 CIVET-extras/1.0\n\n')
    else:
        civetsh.write('module load CIVET/1.1.10+Ubuntu_12.04 CIVET-extras/1.0\n\n')

    ## add a line that will read in the subject id
    civetsh.write('SUBJECT=${1}\n\n')

    #add a line to cd to the CIVET directory
    civetsh.write('cd '+os.path.normpath(targetpath)+"\n\n")

    ## start building the CIVET command
    civetsh.write('CIVET_Processing_Pipeline' + \
        ' -sourcedir input' + \
        ' -targetdir output' + \
        ' -prefix ' + prefix + \
        ' -lobe_atlas -resample-surfaces -spawn -no-VBM' + \
        ' -thickness tlink 20')

    if MULTISPECTRAL: #if multispectral option is selected - add it to the command
         civetsh.write(' -multispectral')

    if ONETESLA:
        civetsh.write(' -N3-distance 200')
    else: # if not one-tesla (so 3T) using 3T options for N3
        if CIVET12==False:
            civetsh.write(' -3Tesla ')
        civetsh.write(' -N3-distance 75')

    civetsh.write( ' ${SUBJECT} -run \n\n')

    ## might as well run the QC script for this subject now too
    civetsh.write('CIVET_QC_Pipeline -sourcedir ' + civet_in + \
            ' -targetpath ' + civet_out + \
            ' -prefix ' + prefix +\
            ' ${SUBJECT} \n')

    #and...don't forget to close the file
    civetsh.close()

######## NOW START the 'main' part of the script ##################
## make the civety directory if it doesn't exist
targetpath = os.path.normpath(targetpath)
civet_in    = os.path.join(targetpath+'/input/')
civet_out   = os.path.join(targetpath+'/output/')
civet_logs  = os.path.join(targetpath+'/logs/')
dm.utils.makedirs(civet_in)
dm.utils.makedirs(civet_out)
dm.utils.makedirs(civet_logs)

## writes a standard CIVET running script for this project (if it doesn't exist)
## the script requires a $SUBJECT variable - that gets sent if by qsub (-v option)
runcivetsh = os.path.join(targetpath,'runcivet.sh')
if os.path.isfile(runcivetsh):
    ##should write something here to check that this file doesn't change over time
    if DEBUG: print("{} already written - using it".format(runcivetsh))
else:
    makeCIVETrunsh(runcivetsh)

####set checklist dataframe structure here
#because even if we do not create it - it will be needed for newsubs_df (line 80)
cols = ["id", "mnc_t1", "date_civetran", "civet_run", "qc_run", "qc_rator", "qc_rating", "notes"]
if MULTISPECTRAL:
	cols.insert(1,"mnc_t2")
	cols.insert(2,"mnc_pd")

# if the checklist exists - open it, if not - create the dataframe
checklistfile = os.path.normpath(targetpath+'/CIVETchecklist.csv')
if os.path.isfile(checklistfile):
	checklist = pd.read_csv(checklistfile, sep=',', dtype=str, comment='#')
else:
	checklist = pd.DataFrame(columns = cols)

## load the projects data export checklist so that we can check if the data has been QCed
QCedTranfer = True #open a flag to say that this is a project with a qc checklist
qcchecklist = os.path.join(inputpath,'metadata','checklist.csv')
qcedlist = []
if os.path.isfile(qcchecklist):
    with open(qcchecklist) as f:
        for line in f:
            line = line.strip()
            if len(line.split(' ')) > 1:
                pdf = line.split(' ')[0]
                subid = pdf.replace('.pdf','')[3:]
                qcedlist.append(subid)

else: QCedTranfer = False #set flag to False if a qc checklist does not exist

## find those subjects in input who have not been processed yet and append to checklist
subids_in_mnc = dm.utils.get_subjects(os.path.join(inputpath,'data','mnc'))
subids_in_mnc = [ v for v in subids_in_mnc if "PHA" not in v ] ## remove the phantoms from the list
if QCedTranfer: subids_in_mnc = list(set(subids_in_mnc) & set(qcedlist)) ##now only add it to the filelist if it has been QCed
newsubs = list(set(subids_in_mnc) - set(checklist.id))
newsubs_df = pd.DataFrame(columns = cols, index = range(len(checklist),len(checklist)+len(newsubs)))
newsubs_df.id = newsubs
checklist = checklist.append(newsubs_df)

# do linking for the T1
doCIVETlinking("mnc_t1",T1_TAG , '_t1.mnc')

#link more files if multimodal
if MULTISPECTRAL:
    doCIVETlinking("mnc_t2", T2_TAG, '_t2.mnc')
    doCIVETlinking("mnc_pd", PD_TAG, '_pd.mnc')

## now checkoutputs to see if any of them have been run
#if yes update spreadsheet
#if no submits that subject to the queue
for i in range(0,len(checklist)):
    if checklist['civet_run'][i] !="Y":
        subid = checklist['id'][i]
        subprefix = os.path.join(civet_in, prefix + '_' + subid)
        CIVETready = os.path.exists(subprefix + '_t1.mnc')
        if MULTISPECTRAL:
            CIVETready = CIVETready & os.path.exists(subprefix + '_t2.mnc')
            CIVETready = CIVETready & os.path.exists(subprefix + '_pd.mnc')
        if CIVETready:
            thicknessdir = os.path.join(civet_out,subid,'thickness')
            if os.path.exists(thicknessdir)== False:
                os.chdir(os.path.normpath(targetpath))
                docmd(['qsub','-o', 'logs', \
                         '-N', 'civet_' + subid,  \
                         os.path.basename(runcivetsh), subid])
                checklist['date_civetran'][i] = datetime.date.today()
            elif len(os.listdir(thicknessdir)) == 5:
                checklist['civet_run'][i] = "Y"
            else :
                checklist['notes'][i] = "something was bad with CIVET :("

## find those subjects who were run but who have no qc pages made
## note: this case should only exist if something went horribly wthe idea of to run the qc before CIVET because it's fast (just .html writing)
## in order to get a full CIVET + QC for one participants, call this script twice

toqctoday = []
for i in range(0,len(checklist)):
    if checklist['civet_run'][i] =="Y":
    	if checklist['qc_run'][i] !="Y":
        	subid = checklist['id'][i]
        	qchtml = os.path.join(civet_out,QC,subid + '.html')
        	if os.path.isfile(qchtml):
        		checklist['qc_run'][i] = "Y"


## write the checklist out to a file
checklist.to_csv(checklistfile, sep=',', columns = cols, index = False)
