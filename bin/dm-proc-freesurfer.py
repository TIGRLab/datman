#!/usr/bin/env python
"""
This run freesurfer pipeline on T1 images.
Also now extracts some volumes and converts some files to nifty for epitome

Usage:
  dm-proc-freesurfer.py [options]

Arguments:
    <inputdir>                Top directory for nii inputs normally (project/data/nii/)
    <FS_subjectsdir>          Top directory for the Freesurfer output

Options:
  --do-not-sink            Do not convert a data to nifty for epitome
  --T1-tag STR             Tag used to find the T1 files (default is 'T1')
  --tags STR               Optional tag used (as well as '--T1-tag') to filter for correct input
  --multiple-inputs        Allow multiple input T1 files to Freesurfersh
  --FS-option STR          A quoted string of an non-default freesurfer option to add.
  --run-version STR        A version string that is appended to 'run_freesurfer_<tag>.sh' for mutliple versions
  --QC-transfer QCFILE     QC checklist file - if this option is given than only QCed participants will be processed.
  --use-test-datman        Use the version of datman in Erin's test environment. (default is '/archive/data-2.0/code/datman.module')
  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run
  -h, --help               Show help

DETAILS
This run freesurfer pipeline on T1 images maps after conversion to nifty.
Also submits a dm-freesurfer-sink.py and some extraction scripts as a held job.

This script will look search inside the "inputdir" folder for T1 images to process.
If uses the '--T1-tag' string (which is '_T1_' by default) to do so.
If this optional argument (('--tag2') is given, this string will be used to refine
the search, if more than one T1 file is found inside the participants directory.

The T1 image found for each participant in printed in the 'T1_nii' column
of "freesurfer-checklist.csv". If no T1 image is found, or more than one T1 image
is found, a note to that effect is printed in the "notes" column of the same file.
You can manually overide this process by editing the "freesurfer-checklist.csv"
with the name of the T1 image you would like processed (esp. in the case of repeat scans).

The script then looks to see if any of the T1 images (listed in the
"freesurfer-checklist.csv" "T1_nii" column) have not been processed (i.e. have no outputs).
These images are then submitted to the queue.

If the "--QC-transfer" option is used, the QC checklist from data transfer
(i.e. metadata/checklist.csv) and only those participants who passed QC will be processed.

The '--run-version' option was added for situations when you might want to use
different freesurfer settings for a subgroup of your participants (for example,
all subjects from a site with an older scanner (but have all the
outputs show up in the same folder in the end). The run version string is appended
to the freesurfer_run.sh script name. Which allows for mutliple freesurfer_run.sh
scripts to exists in the bin folder.

Will load freesurfer in queue:
module load freesurfer/5.3.0
(also requires the datmat python enviroment)

Written by Erin W Dickie, Sep 30 2015
Adapted from old dm-proc-freesurfer.py
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
inputdir        = arguments['<inputdir>']
subjectsdir     = arguments['<FS_subjectsdir>']
rawQCfile       = arguments['--QC-transfer']
MULTI_T1        = arguments['--multiple-inputs']
NO_SINK         = arguments['--do-not-sink']
T1_tag          = arguments['--T1-tag']
TAG2            = arguments['--tag2']
RUN_TAG         = arguments['--run-version']
FS_option       = arguments['--FS-option']
TESTDATMAN      = arguments['--use-test-datman']
VERBOSE         = arguments['--verbose']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']

if DEBUG: print arguments
#set default tag values
if T1_tag == None: T1_tag = '_T1_'
QCedTranfer = False if rawQCfile == None else True

## set the basenames of the two run scripts
if RUN_TAG == None:
    runFSsh_name = 'run_freesurfer.sh'
else:
    runFSsh_name = 'run_freesurfer_' + RUN_TAG + '.sh'
runPostsh_name = 'postfreesurfer.sh'

## two silly little things to find for the run script

### Erin's little function for running things in the shell
def docmd(cmdlist):
    "sends a command (inputed as a list) to the shell"
    if DEBUG: print ' '.join(cmdlist)
    if not DRYRUN: subprocess.call(cmdlist)

# need to find the t1 weighted scan and update the checklist
def find_T1images(archive_tag,archive_tag2):
    """
    will look for new files in the inputdir
    and add them to a list for the processing

    archive_tag -- filename tag that can be used for search (i.e. '_T1_')
    archive_tag2 -- second tag that is also need (i.e. 'DTI-60')
    checklist -- the checklist pandas dataframe to update
    """
    for i in range(0,len(checklist)):
        sdir = os.path.join(dtifit_dir,checklist['id'][i])
	    #if T1 name not in checklist
        if pd.isnull(checklist['T1_nii'][i]):
            sfiles = []
            for fname in os.listdir(sdir):
                if archive_tag in fname:
                    if archive_tag2 != None:
                        if archive_tag2 in fname:
                            sfiles.append(fname)
                    else:
                        sfiles.append(fname)
            if DEBUG: print "Found {} {} in {}".format(len(sfiles),archive_tag,sdir)
            if len(sfiles) == 1:
                checklist['T1_nii'][i] = sfiles[0]
            elif len(sfiles) > 1:
                if MULTI_T1:
                    '''
                    if multiple T1s are allowed (as per --multiple-inputs flag) - add to T1 file
                    '''
                    checklist['T1_nii'][i] = ';'.join.sfiles
                else:
                    checklist['notes'][i] = "> 1 {} found".format(archive_tag)
            elif len(sfiles) < 1:
                checklist['notes'][i] = "No {} found.".format(archive_tag)


### build a template .sh file that gets submitted to the queue
def makeFreesurferrunsh(filename,prefix):
    """
    builds a script in the subjectsdir (run.sh)
    that gets submitted to the queue for each participant (in the case of 'doInd')
    or that gets held for all participants and submitted once they all end (the concatenating one)
    """
    bname = os.path.basename(filename)
    if bname == runFSsh_name:
        FS_STEP = 'FS'
    if bname == runPostsh_name:
        FS_STEP = 'Post'

    #open file for writing
    Freesurfersh = open(filename,'w')
    Freesurfersh.write('#!/bin/bash\n\n')

    Freesurfersh.write('# SGE Options\n')
    Freesurfersh.write('#$ -S /bin/bash\n')
    Freesurfersh.write('#$ -q main.q\n')
    Freesurfersh.write('#$ -j y \n')
    Freesurfersh.write('#$ -o '+ log_dir + ' \n')
    Freesurfersh.write('#$ -e '+ log_dir + ' \n')
    Freesurfersh.write('#$ -l mem_free=6G,virtual_free=6G\n\n')

    Freesurfersh.write('#source the module system\n')
    Freesurfersh.write('source /etc/profile\n\n')

    Freesurfersh.write('## this script was created by dm-proc-freesurfer.py\n\n')
    ## can add section here that loads chosen CIVET enviroment
    Freesurfersh.write('##load the Freesurfer enviroment\n')
    Freesurfersh.write('module load freesurfer/5.3.0\n\n')

    Freesurfersh.write('\nexport SUBJECTS_DIR=' + subjectsdir + '\n\n')
    ## write the freesurfer running bit
    if FS_STEP == 'FS':

        Freesurfersh.write('SUBJECT=${1}\n')
        Freesurfersh.write('T1MAPS=${2}\n')
        ## add the engima-dit command

        Freesurfersh.write('\nrecon-all -all -notal-check -cw256 ')
        if FS_option != None:
            Freesurfersh.write(FS_option + ' ')
        Freesurfersh.write('-subjid ${SUBJECT} ${T1MAPS}' + ' -qcache\n')

    ## write the post freesurfer bit
    if FS_STEP == 'Post':
        # The dm-freesurfer-sink.py bit requires datman
        if TESTDATMAN:
            Freesurfersh.write('module load /projects/edickie/privatemodules/datman/edickie\n\n')
        else:
            Freesurfersh.write('module load /archive/data-2.0/code/datman.module\n\n')

        ## to the sinking - unless told not to
        if not NO_SINK:
            PROJECTDIR = os.path.dirname(os.path.dirname(subjectsdir))
            Freesurfersh.write('module load AFNI/2014.12.161\n')
            Freesurfersh.write('PROJECTDIR=' + PROJECTDIR + ' \n\n')
            Freesurfersh.write('dm-freesurfer-sink.py ${PROJECTDIR} \n\n')

        ## add the engima-extract bits
        Freesurfersh.write('ENGIMA_ExtractCortical.sh ${SUBJECTS_DIR} '+ prefix + '\n')
        Freesurfersh.write('ENGIMA_ExtractSubcortical.sh ${SUBJECTS_DIR} '+ prefix + '\n')

    #and...don't forget to close the file
    Freesurfersh.close()

### check the template .sh file that gets submitted to the queue to make sure option haven't changed
def checkrunsh(filename):
    """
    write a temporary (run.sh) file and than checks it againts the run.sh file already there
    This is used to double check that the pipeline is not being called with different options
    """
    tempdir = tempfile.mkdtemp()
    tmprunsh = os.path.join(tempdir,os.path.basename(filename))
    makeFreesurferrunsh(tmprunsh)
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

####set checklist dataframe structure here
#because even if we do not create it - it will be needed for newsubs_df (line 80)
def loadchecklist(checklistfile,subjectlist):
    """
    Reads the checklistfile (normally called Freesurfer-DTI-checklist.csv)
    if the checklist csv file does not exit, it will be created.

    This also checks if any subjects in the subjectlist are missing from the checklist,
    (checklist.id column)
    If so, they are appended to the bottom of the dataframe.
    """

    cols = ['id', 'T1_nii', 'date_ran','qc_rator', 'qc_rating', 'notes']

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
subjectsdir = os.path.abspath(subjectsdir)
log_dir = os.path.join(subjectsdir,'logs')
run_dir = os.path.join(subjectsdir,'bin')
dm.utils.makedirs(log_dir)
dm.utils.makedirs(run_dir)

## find those subjects in input who have not been processed yet
subids_in_nii = dm.utils.get_subjects(inputdir)
subids_in_nii = [ v for v in subids_in_nii if "PHA" not in v ] ## remove the phantoms from the list
if QCedTranfer:
    # if a QC checklist exists, than read it and only process those participants who passed QC
    qcedlist = get_qced_subjectlist(rawQCfile)
    subids_in_nii = list(set(subids_in_nii) & set(qcedlist)) ##now only add it to the filelist if it has been QCed

## writes a standard Freesurfer-DTI running script for this project (if it doesn't exist)
## the script requires a OUTDIR and MAP_BASE variables - as arguments $1 and $2
## also write a standard script to concatenate the results at the end (script is held while subjects run)
prefix = subids_in_nii[0][0:4]
for runfilename in [runFSsh_name,runPostsh_name]:
    runsh = os.path.join(run_dir,runfilename)
    if os.path.isfile(runsh):
        ## create temporary run file and test it against the original
        checkrunsh(runsh,prefix)
    else:
        ## if it doesn't exist, write it now
        makeFreesurferrunsh(runsh,prefix)

## create an checklist for the T1 maps
checklistfile = os.path.normpath(subjectsdir+'/freesurfer-checklist.csv')
checklist = loadchecklist(checklistfile,subids_in_dtifit)

## look for new subs using T1_tag and tag2
find_T1images(T1_tag,TAG2)

## now checkoutputs to see if any of them have been run
#if yes update spreadsheet
#if no submits that subject to the queue
jobnames = []
## should be in the right run dir so that it submits without the full path
os.chdir(run_dir)
for i in range(0,len(checklist)):
    subid = checklist['id'][i]
    # if all input files are found - check if an output exists
    if pd.isnull(checklist['T1_nii'][i])==False:
        FScomplete = os.path.join(subjectsdir,subid,'scripts','recon-all.done')
        FSrunning = os.path.join(subjectsdir,subid,'scripts','recon-all.done')
        # if no output exists than run engima-dti
        if os.path.isfile(FScomplete)== False & os.path.isfile(FSrunning)==False:

            ##  set up params
            jobname = 'FS_' + subid
            smap = checklist['T1_nii'][i]

            ## if multiple inputs in smap - need to parse
            if ';' in smap:
                base_smaps = smap.split(';')
            else: base_smaps = smap
            T1s = []
            for basesmap in base_smaps:
                T1s.append(os.path.join(inputdir,subid,basemap))

            jobname = 'FS_' + subid
            docmd(['qsub','-N', jobname,  \
                     runFSsh_name, \
                     subid, \
                     "'" + ' '.join(T1s) + "'"])
            checklist['date_ran'][i] = datetime.date.today()
            jobnames.append(jobname)


### if more that 30 subjects have been submitted to the queue,
### use only the last 30 submitted as -hold_jid arguments
if len(jobnames) > 30 : jobnames = jobnames[-30:]
## if any subjects have been submitted,
## submit a final job that will consolidate the resutls after they are finished
if len(jobnames) > 0:
    #if any subjects have been submitted - submit an extract consolidation job to run at the end
    os.chdir(run_dir)
    docmd(['qsub', '-N', 'postFS',  \
        '-hold_jid', ','.join(jobnames), \
        runPostsh_name])

## write the checklist out to a file
checklist.to_csv(checklistfile, sep=',', index = False)
