#!/usr/bin/env python
"""
This run CIVET on stuff

Usage:
  run-proc-CIVET.py [options] <inputpath> <targetpath> <prefix>

Arguments:
    <inputpath>      Path to input directory (usually a project directory inside /data-2.0)
    <targetpath>     Path to directory that will contain CIVET inputs (links) and outputs
    <prefix>         Prefix for CIVET input (see details)    `

Options:
  --multispectral          Use the T1W, T2W and PD images in pipeline (default = use only T1W)
  --1-Telsa                Use CIVET options for 1-Telsa data (default = 3T options)
  --T1-tag	STR			   Tag in filename that indicates it's a T1 (default = "_T1_")
  --T2-tag	STR			   Tag in filename that indicates it's a T2 (default = "_T2_")
  --PD-tag	STR			   Tag in filename that indicates it's a PD (default = "_PD_")
  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run

DETAILS
Requires that CIVET module has been loaded.
Before running this set enviroment as:
module load CIVET/1.1.10+Ubuntu_12.04 CIVET-extras/1.0
module load datman
unset module

The inputdir should be the project directory (inside data-2.0))
"""
from docopt import docopt
import pandas as pd
import datman as dm
import datman.utils
import datman.scanid
import os.path
import sys
import datetime

arguments       = docopt(__doc__)
inputpath       = arguments['<inputpath>']
targetpath      = arguments['<targetpath>']
prefix          = arguments['<prefix>']
MULTISPECTRAL   = arguments['--multispectral']
ONETESLA        = arguments['--1-Telsa']
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

## make the civety directory if it doesn't exist
civet_in    = os.path.normpath(targetpath+'/input/')
civet_out   = os.path.normpath(targetpath+'/output/')
civet_logs  = os.path.normpath(targetpath+'/logs/')
dm.utils.makedirs(civet_in)
dm.utils.makedirs(civet_out)
dm.utils.makedirs(civet_logs)

#set checklist dataframe structure here
#because even if we do not create it - it will be needed for newsubs_df (line 80)
cols = ["id", "mnc_t1", "civetid", "date_civetran", "civet_run", "qc_run", "qc_rator", "qc_rating", "notes"]
if MULTISPECTRAL:
	cols.insert(2,"mnc_t2")
	cols.insert(3,"mnc_pd")

## if the checklist exists - open it, if not - create the dataframe
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
    	#if civet name not in checklist add link to checklist
    	if pd.isnull(checklist['civetid'][i]):
    		checklist['civetid'][i] = checklist.id[i].replace(prefix,'').replace('_',"")
    	#if link doesn't exist
    	target = os.path.join(civet_in, prefix + '_' + checklist['civetid'][i] + civet_ext)
    	if os.path.exists(target)==False:
            if checklist['id'][i] in qcchecklist or QCedTranfer==False:
        		mncdir = os.path.join(inputpath,data,mnc,checklist['id'][i])
        		#if mnc name not in checklist
        		if pd.isnull(checklist[colname][i]):
        			mncfiles = []
        			for fname in os.listdir(mncdir):
        				if archive_tag in fname:
        					mncfiles.append(fname)
        			if len(mncfiles) == 1:
        				checklist[colname][i] = mncfiles[0]
        			elif len(mncfiles) > 1:
                        #add something here that runs a script to merge the T1s
                        if QCedTranfer==True:
                            ## if mean file exists - thats you file
                            meanmnc = [m for m in mncfiles if "mean" in m]
                            if len(meanmnc) == 1:
                                checklist[colname][i] = meanmnc[0]
                        else:
                            checklist['notes'][i] = "> 1 {} found".format(archive_tag)
        			elif len(mncfiles) < 1:
        				checklist['notes'][i] = "No {} found.".format(archive_tag)
        		# make the link
        		if pd.isnull(checklist[colname][i])==False:
        			mncpath = os.path.join(mncdir,checklist[colname][i])
        			relpath = os.path.relpath(mncpath,os.path.dirname(target))
        			if VERBOSE: print("linking {} to {}".format(relpath, target))
        			if not DRYRUN:
        				os.symlink(relpath, target)

# do linking for the T1
doCIVETlinking('mnc_t1',T1_TAG , '_t1.mnc')

#link more files if multimodal
if MULTISPECTRAL:
    doCIVETlinking('mnc_t2', T2_TAG, '_t2.mnc')
    doCIVETlinking('mnc_pd', PD_TAG, '_pd.mnc')

## now checkoutputs to see if any of them have been run
#if yes update spreadsheet
#if no add to subjectlist to run
toruntoday = []
for i in range(0,len(checklist)):
    if checklist['civet_run'][i] !="Y":
        subid = checklist['civetid'][i]
        subprefix = os.path.join(civet_in, prefix + '_' + subid)
        CIVETready = os.path.exists(subprefix + '_t1.mnc')
        if MULTISPECTRAL:
            CIVETready = CIVETready & os.path.exists(subprefix + '_t2.mnc')
            CIVETready = CIVETready & os.path.exists(subprefix + '_pd.mnc')
        if CIVETready:
            thicknessdir = os.path.join(civet_out,subid,'thickness')
            if os.path.exists(thicknessdir)== False:
                toruntoday.append(subid)
                checklist['date_civetran'][i] = datetime.date.today()
            elif len(os.listdir(thicknessdir)) == 5:
                checklist['civet_run'][i] = "Y"
            else :
                checklist['notes'][i] = "something was bad with CIVET :("

## find those subjects who were run but who have no qc pages made
## note: the idea of to run the qc before CIVET because it's fast (just .html writing)
## in order to get a full CIVET + QC for one participants, call this script twice

toqctoday = []
for i in range(0,len(checklist)):
    if checklist['civet_run'][i] =="Y":
    	if checklist['qc_run'][i] !="Y":
        	subid = checklist['civetid'][i]
        	qchtml = os.path.join(civet_out,QC,subid + '.html')
        	if os.path.isfile(qchtml):
        		checklist['qc_run'][i] = "Y"
        	else:
        		toqctoday.append(subid)

## write the checklist out to a file
checklist.to_csv(checklistfile, sep=',', columns = cols, index = False)

# Run the QC if there are any new peeps to QC, this is fast, so might as well do it now
if len(toqctoday) > 0:
    QCcmd = 'CIVET_QC_Pipeline -sourcedir ' + civet_in + \
        ' -targetpath ' + civet_out + \
        ' -prefix ' + prefix +\
        ' ' + " ".join(toqctoday)
    ## the part that actually runs teh qc command
    if DEBUG: print(QCcmd)
    datman.utils.run(QCcmd,dryrun = DRYRUN)
    ## probably should write something here that updates the QC index.html

## write the subids to a file if there are more than ten
if len(toruntoday) > 0:
    idfile = os.path.join(civet_logs,'id-file-'+str(datetime.date.today())+'.txt')
    filelist = open(idfile, 'w')
    filelist.write("\n".join(toruntoday))
    filelist.close()

    ## start building the CIVET command
    CIVETcmd = 'CIVET_Processing_Pipeline' + \
        ' -sourcedir ' + civet_in + \
        ' -targetdir ' + civet_out + \
        ' -prefix ' + prefix + \
        ' -animal -lobe_atlas -resample-surfaces -granular -VBM' + \
        ' -thickness tlink 20 -queue main.q'

    if MULTISPECTRAL: #if multispectral option is selected - add it to the command
         CIVETcmd = CIVETcmd +  ' -multispectral'

    if ONETESLA:
        CIVETcmd = CIVETcmd + ' -N3-distance 200'
    else: # if not one-tesla (so 3T) using 3T options for N3
        CIVETcmd = CIVETcmd + ' -3Tesla -N3-distance 75'

    CIVETcmd = CIVETcmd + ' -id-file ' + idfile + ' -run'
    # the part that actually calls CIVET
    if DEBUG: print CIVETcmd
    datman.utils.run(CIVETcmd, dryrun=DRYRUN)
