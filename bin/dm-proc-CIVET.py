#!/usr/bin/env python
"""
This run CIVET on stuff

Usage:
  dm-proc-CIVET.py [options] <inputpath> <targetpath> <prefix>

Arguments:
    <inputpath>      Path to input directory (expecting subject directories inside)
    <targetpath>     Path to directory that will contain CIVET inputs (links) and outputs
    <prefix>         Prefix for CIVET input (see details)    `

Options:
  --multispectral          Use the T1W, T2W and PD images in pipeline (default = use only T1W)
  --1-Telsa                Use CIVET options for 1-Telsa data (default = 3T options)
  --CIVET-version-12       Use version 1.1.12 of CIVET (default  = 1.1.10)
  --QCed-transfer FILE     Read the QC transfer checklist and only run those participants who pass QC
  --T1-tag	STR			   Tag in filename that indicates it's a T1 (default = "_T1_")
  --T2-tag	STR			   Tag in filename that indicates it's a T2 (default = "_T2_")
  --PD-tag	STR			   Tag in filename that indicates it's a PD (default = "_PD_")
  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run
  -h,--help                Print help

DETAILS
Runs CIVET in a rather organized way on all the participants within one project.
This script is built to work within the folder structure of the kimel lab (data-2.0).
If a the project folder contains a QC checklist for raw data (i.e. "metadata/checklist.csv"),
you can point this script to that document with the option "--QCed-transfer <filename>".
The pipeline with then only run on participants who have been QCed already.

This script writes a little script (bin/runcivet.sh) within the output directory structure
that gets submitted to the queue for each subject. Subject's ID is passed into the qsub
command as an argument.

It also writes a second script that will run the CIVET_QC_Pipeline once all jobs
have been completed.

The CIVET enviroment used (and all CIVET options) get's printed into the runcivet.sh script.
Also, this script creates and updates a checklist ('CIVETchecklist.csv') with what
participants have been run (on which .mnc file) and the date CIVET was ran.
The inputdir should be the project directory (inside data-2.0))

This script checks that. for each subject, one scan of each type needed
(T1, or T1, T2 & PD) exist in the data/mnc/ folder within the project.
If it finds multiple files, it will either:
search for a file with the tag "_mean" (i.e. output of dm-proc-mncmean.py) or exit
You can choose to either update CIVETchecklist.csv with the name of the best scan
OR run dm-proc-mncmean.py to average the scans.
After doing either just run this script again, and they will be submtted to the queue.

For T2 and PD scans - if not already in minc format, but are in nifty.
You may need to run dm-proc-nii2mnc.py to convert those images from nifty format.
"""
from docopt import docopt
import pandas as pd
import datman as dm
import datman.utils
import datman.scanid
import glob
import os.path
import sys
import subprocess
import datetime
import tempfile
import shutil
import filecmp
import difflib

arguments       = docopt(__doc__)
inputpath       = arguments['<inputpath>']
targetpath      = arguments['<targetpath>']
prefix          = arguments['<prefix>']
MULTISPECTRAL   = arguments['--multispectral']
ONETESLA        = arguments['--1-Telsa']
CIVET12         = arguments['--CIVET-version-12']
rawQCfile       = arguments['--QCed-transfer']
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
QCedTranfer = False if rawQCfile == None else True

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
            mncdir = os.path.join(inputpath,checklist['id'][i])
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
    bname = os.path.basename(filename)
    if bname == runcivetsh:
        CIVETSTEP = 'runcivet'
    if bname == runqcsh:
        CIVETSTEP = 'qc'
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
    if CIVETSTEP == 'runcivet':
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
            civetsh.write(' -N3-distance 50')

        civetsh.write( ' ${SUBJECT} -run \n\n')

    if CIVETSTEP == 'qc':
        #add a line to cd to the CIVET directory
        civetsh.write('cd '+civet_out+"\n")
        civetsh.write('SUBJECTS=`ls | grep -v QC | grep -v References.txt`\n\n')

        #add a line to cd to the CIVET directory
        civetsh.write('cd '+os.path.normpath(targetpath)+"\n\n")

        #run the CIVET qc pipeline on all subs who are processed
        civetsh.write('CIVET_QC_Pipeline -sourcedir ' + civet_in + \
                    ' -targetdir ' + civet_out + \
                    ' -prefix ' + prefix +\
                    ' ${SUBJECTS} \n')
    #and...don't forget to close the file
    civetsh.close()

### check the template .sh file that gets submitted to the queue to make sure option haven't changed
def checkrunsh(filename):
    """
    write a temporary (run.sh) file and than checks it againts the run.sh file already there
    This is used to double check that the pipeline is not being called with different options
    """
    tempdir = tempfile.mkdtemp()
    tmprunsh = os.path.join(tempdir,os.path.basename(filename))
    makeCIVETrunsh(tmprunsh)
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
## make the civety directory if it doesn't exist
targetpath = os.path.normpath(targetpath)
civet_in    = os.path.join(targetpath+'/input/')
civet_out   = os.path.join(targetpath+'/output/')
civet_logs  = os.path.join(targetpath+'/logs/')
civet_bin   = os.path.join(targetpath+'/bin/')
dm.utils.makedirs(civet_in)
dm.utils.makedirs(civet_out)
dm.utils.makedirs(civet_logs)
dm.utils.makedirs(civet_bin)

## writes a standard CIVET running script for this project (if it doesn't exist)
## the script requires a $SUBJECT variable - that gets sent if by qsub (-v option)
runcivetsh = 'runcivet.sh'
runqcsh    = 'runqc.sh'
for runfilename in [runcivetsh,runqcsh]:
    runsh = os.path.join(civet_bin,runfilename)
    if os.path.isfile(runsh):
        ## create temporary run file and test it against the original
        checkrunsh(runsh)
    else:
        ## if it doesn't exist, write it now
        makeCIVETrunsh(runsh)

####set checklist dataframe structure here
#because even if we do not create it - it will be needed for newsubs_df (line 80)
cols = ["id", "mnc_t1", "date_civetran", "qc_rator", "qc_rating", "notes"]
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
qcedlist = []
if QCedTranfer == True:
    if os.path.isfile(rawQCfile):
        with open(rawQCfile) as f:
            for line in f:
                line = line.strip()
                if len(line.split(' ')) > 1:
                    pdf = line.split(' ')[0]
                    subid = pdf.replace('.pdf','').replace('.html','')[3:]
                    qcedlist.append(subid)
    else:
        sys.exit("Cannot find QC file {}".format(rawQCfile))

## find those subjects in input who have not been processed yet and append to checklist
subids_in_mnc = dm.utils.get_subjects(inputpath)
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
jobnames = []
for i in range(0,len(checklist)):
    subid = checklist['id'][i]
    subprefix = os.path.join(civet_in, prefix + '_' + subid)
    # checks that all the input files are there
    CIVETready = os.path.exists(subprefix + '_t1.mnc')
    if MULTISPECTRAL:
        CIVETready = CIVETready & os.path.exists(subprefix + '_t2.mnc')
        CIVETready = CIVETready & os.path.exists(subprefix + '_pd.mnc')
    # if all input files are there - check if an output exists
    if CIVETready:
        thicknessdir = os.path.join(civet_out,subid,'thickness')
        # if no output exists than run civet
        if os.path.exists(thicknessdir)== False:
            os.chdir(civet_bin)
            jobname = 'civet_' + subid
            docmd(['qsub','-j','y','-o', civet_logs, \
                     '-N', jobname,  \
                     os.path.basename(runcivetsh), subid])
            jobnames.append(jobname)
            checklist['date_civetran'][i] = datetime.date.today()
        # if failed logs exist - update the CIVETchecklist
        else :
            civetlogs = os.path.join(civet_out,subid,'logs')
            faillogs = glob.glob(civetlogs + '/*.failed')
            if DEBUG: print "Found {} fails for {}: {}".format(len(faillogs),subid,faillogs)
            if len(faillogs) > 0:
                checklist['notes'][i] = "CIVET failed :("

##subit a qc pipeline job (kinda silly as a job, but it needs to be dependant, and have right enviroment)
### if more that 30 subjects have been submitted to the queue,
### use only the last 30 submitted as -hold_jid arguments
if len(jobnames) > 30 : jobnames = jobnames[-30:]
## if any subjects have been submitted,
## submit a final job that will qc the resutls after they are finished
if len(jobnames) > 0:
    #if any subjects have been submitted - submit an extract consolidation job to run at the end
    os.chdir(civet_bin)
    docmd(['qsub','-j','y','-o', civet_logs, \
        '-N', 'civet_qc',  \
        '-hold_jid', ','.join(jobnames), \
        runqcsh ])

## write the checklist out to a file
checklist.to_csv(checklistfile, sep=',', columns = cols, index = False)
