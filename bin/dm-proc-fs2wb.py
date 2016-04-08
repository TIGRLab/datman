#!/usr/bin/env python
"""
This will convert the all freesurfer outputs to hcp "space".

Usage:
  dm-proc-fs2wb.py [options] <fssubjectsdir> <hcpdir>

Arguments:
    <fssubjectsdir>      Path to input directory (freesurfer SUBJECTS_DIR)
    <hcpdir>             Path to top hcp directory (outputs)   `

Options:
  --prefix STR			   Tag for filtering subject directories
  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run
  -h,--help                Print help

DETAILS
Converts freesurfer outputs to a Human Connectome Project outputs in
a rather organized way on all the participants within one project.

This script writes a little script (bin/hcpconvert.sh) within the output directory structure
that gets submitted to the queue for each subject. Subject's ID is passed into the qsub
command as an argument.

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
inputpath       = arguments['<fssubjectsdir>']
targetpath      = arguments['<hcpdir>']
prefix          = arguments['--prefix']
VERBOSE         = arguments['--verbose']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']

if DEBUG: print arguments

### Erin's little function for running things in the shell
def docmd(cmdlist):
    "sends a command (inputed as a list) to the shell"
    if DEBUG: print ' '.join(cmdlist)
    if not DRYRUN: subprocess.call(cmdlist)

epiclone = '/archive/data-2.0/code/datman/assets/epitome/160404-ewd'

### build a template .sh file that gets submitted to the queue
def makerunsh(filename):
    """
    builds a script in the target directory (run.sh)
    that gets submitted to the queue for each participant
    """

    bname = os.path.basename(filename)
    if bname == runconvertsh:
        thisSTEP = 'Convert'
    if bname == runpostsh:
        thisSTEP = 'Post'

    #open file for writing
    runsh = open(filename,'w')
    runsh.write('#!/bin/bash\n\n')

    runsh.write('# SGE Options\n')
    runsh.write('#$ -S /bin/bash\n')
    runsh.write('#$ -q main.q\n')
    runsh.write('#$ -l mem_free=2G,virtual_free=2G\n\n')

    runsh.write('#source the module system\n')
    runsh.write('source /etc/profile\n')
    runsh.write('module load python/2.7.9-anaconda-2.1.0-150119\n')
    runsh.write('module load python-extras/2.7.9\n')
    runsh.write('module load freesurfer/5.3.0\n')
    runsh.write('module load FSL/5.0.7\n')
    runsh.write('module load AFNI/2014.12.16\n')
    runsh.write('module load matlab/R2014a\n')
    runsh.write('module load FIX/1.061\n')
    runsh.write('module load R/3.1.1 R-extras/3.1.1\n')
    runsh.write('module load connectome-workbench/1.1.1\n')
    runsh.write('module load hcp-pipelines/3.7.0\n\n')

    runsh.write('export  PATH=${{PATH}}:{}/bin\n'.format(epiclone))
    runsh.write('export  PYTHONPATH=${{PYTHONPATH}}:{}\n\n'.format(epiclone))

    runsh.write('## this script was created by dm-proc-fs2wb.py\n\n')
    runsh.write('export SUBJECTS_DIR=' + inputpath + '\n')
    runsh.write('export HCP_DATA=' + targetpath +'\n\n')

    if thisSTEP == 'Convert':
        ## add a line that will read in the subject id
        runsh.write('SUBJECT=${1}\n')

        #add a line to cd to the CIVET directory
        runsh.write('cd ${HCP_DATA}\n\n')

        ## start building the CIVET command
        runsh.write('fs2hcp '\
            ' --FSpath=${SUBJECTS_DIR} --HCPpath=${HCP_DATA} ' +\
            '--subject=${SUBJECT}')

    if thisSTEP == 'Post':
        if prefix:
            runsh.write('epi-hcp-qc --subjects-filter {} native\n'.format(prefix))
            runsh.write('epi-hcp-qc --subjects-filter {} MNIfsaverage32k\n'.format(prefix))
        else:
            runsh.write('epi-hcp-qc native\n')
            runsh.write('epi-hcp-qc MNIfsaverage32k\n')

    runsh.close()

### check the template .sh file that gets submitted to the queue to make sure option haven't changed
def checkrunsh(filename):
    """
    write a temporary (run.sh) file and than checks it againts the run.sh file already there
    This is used to double check that the pipeline is not being called with different options
    """
    tempdir = tempfile.mkdtemp()
    tmprunsh = os.path.join(tempdir,os.path.basename(filename))
    makerunsh(tmprunsh)
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
logs_dir  = os.path.join(targetpath+'/logs/')
bin_dir  = os.path.join(targetpath+'/bin/')
subprocess.call(['mkdir','-p',logs_dir])
subprocess.call(['mkdir','-p',bin_dir])

# writes a standard CIVET running script for this project (if it doesn't exist)
# the script requires a $SUBJECT variable - that gets sent if by qsub (-v option)
runconvertsh = 'fs2hcprun.sh'
runpostsh ='fs2hcpqc.sh'
for runfilename in [runconvertsh, runpostsh]:
    runsh = os.path.join(bin_dir,runfilename)
    if os.path.isfile(runsh):
        ## create temporary run file and test it against the original
        checkrunsh(runsh)
    else:
        ## if it doesn't exist, write it now
        makerunsh(runsh)

####set checklist dataframe structure here
#because even if we do not create it - it will be needed for newsubs_df (line 80)
cols = ["id", "date_converted", "qc_rator", "qc_rating", "notes"]

# if the checklist exists - open it, if not - create the dataframe
checklistfile = os.path.normpath(targetpath+'/checklist.csv')
if os.path.isfile(checklistfile):
	checklist = pd.read_csv(checklistfile, sep=',', dtype=str, comment='#')
else:
	checklist = pd.DataFrame(columns = cols)


## find those subjects in input who have not been processed yet and append to checklist
subids_fs = filter(os.path.isdir, glob.glob(os.path.join(inputpath, '*')))
for i, subj in enumerate(subids_fs):
    subids_fs[i] = os.path.basename(subj)
subids_fs = [ v for v in subids_fs if "PHA" not in v ] ## remove the phantoms from the list

not_a_subid = ['logs','bin','QA','fsaverage','rh.EC_average','lh.EC_average']
for not_subid in not_a_subid:
    subids_fs = filter(lambda x: not_subid != x, subids_fs)

if prefix != None:
    subids_fs = [ v for v in subids_fs if prefix in v ] ## remove the phantoms from the list
newsubs = list(set(subids_fs) - set(checklist.id))
newsubs_df = pd.DataFrame(columns = cols, index = range(len(checklist),len(checklist)+len(newsubs)))
newsubs_df.id = newsubs
checklist = checklist.append(newsubs_df)



## now checkoutputs to see if any of them have been run
#if yes update spreadsheet
#if no submits that subject to the queue
jobnames = []
for i in range(0,len(checklist)):
    subid = checklist['id'][i]
    freesurferdone = os.path.join(inputpath,subid,'scripts','recon-all.done')
    # checks that all the input files are there
    FSready = os.path.exists(freesurferdone)
    # if all input files are there - check if an output exists
    if FSready:
        FS32 = os.path.join(targetpath,subid,'MNINonLinear','fsaverage_LR32k',subid + '.aparc.32k_fs_LR.dlabel.nii')
        # if no output exists than run civet
        if os.path.exists(FS32)== False:
            jobname = 'fs2wb_' + subid
            os.chdir(bin_dir)
            docmd(['qsub','-j','y','-o', logs_dir,'-e', logs_dir, \
                     '-N', jobname,  \
                     runconvertsh, subid])
            jobnames.append(jobname)
            checklist['date_converted'][i] = datetime.date.today()


## if any subjects have been submitted,
## submit a final job that will consolidate the resutls after they are finished

if len(jobnames) > 30 : jobnames = jobnames[-30:]
## if any subjects have been submitted,
## submit a final job that will qc the resutls after they are finished
if len(jobnames) > 0:
    #if any subjects have been submitted - submit an extract consolidation job to run at the end
    os.chdir(bin_dir)
    docmd(['qsub','-j','y','-o', logs_dir, \
        '-N', 'hcp_qc_gen',  \
        '-hold_jid', ','.join(jobnames), \
        runpostsh ])

## write the checklist out to a file
checklist.to_csv(checklistfile, sep=',', columns = cols, index = False)
