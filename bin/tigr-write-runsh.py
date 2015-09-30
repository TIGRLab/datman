#!/usr/bin/env python
"""
Reads from yml config file and export info to determine what to put in run.sh for this project.
Then writes run.sh file.

Usage:
    tigr-write-runsh.py [options] <config.yml>

Arguments:
    <config.yml>             Configuration file in yml format

Options:
    --outputfile FILE        Full path to outputfile (default is ${PROJECTDIR}/bin/run.sh)
    --quiet                  Don't print warnings
    --verbose                Print warnings
    --help                   Print help


DETAILS

Reads from yml config file and export info to determine what to put in run.sh for this project.
Then writes run.sh file.

Expecting to find exportinfo file in ${PROJECTDIR}/metadata/exportinfo.csv

"""
from docopt import docopt
import pandas as pd
import datman as dm
import datman.utils
import datman.scanid
import yaml
import os
import sys


import filecmp
import difflib

arguments       = docopt(__doc__)
config_yml      = arguments['<config.yml>']
outputfile      = arguments['--outputfile']
VERBOSE         = arguments['--verbose']
QUIET           = arguments['--quiet']

## Read in the configuration yaml file
if not os.path.isfile(config_yml):
    sys.exit("configuration file not found. Try again.")

## load the yml file
with open(config_yml, 'r') as stream:
    config = yaml.load(stream)

## check that the expected keys are there
ExpectedKeys = ['MRUSER','StudyName','PROJECTDIR','Sites','ExportInfo']
diffs = set(ExpectedKeys) - set(config.keys())
if len(diffs) > 0:
    sys.exit("configuration file missing {}".format(diffs))

## check that the projectdir exists
projectdir =  os.path.normpath(config['PROJECTDIR'])
if not os.path.exists(projectdir):
    print("WARNING: PROJECTDIR {} does not exist".format(projectdir))

## read in the site names as a list
SiteNames = []
for site in config['Sites']:
    SiteNames.append(site.keys()[0])

## sets some variables using defaults if not given
if 'XNAT_PROJECT' in config.keys():
    XNAT_PROJECT = config['XNAT_PROJECT']
else:
    XNAT_PROJECT = config['StudyName']

if 'PREFIX' in config.keys():
    PREFIX = config['PREFIX']
else:
    PREFIX = config['StudyName']

## read export info
ScanTypes = config['ExportInfo'].keys()

## unless an outputfile is specified, set the output to ${PROJECTDIR}/bin/run.sh
if outputfile == None:
    ouputfile = os.path.join(projectdir,'bin','run.sh')

#open file for writing
runsh = open(outputfile,'w')

runsh.write('#!/bin/bash\n')
runsh.write('#!/# Runs pipelines like a bro\n#!/#\n')

runsh.write('#!/# Usage:\n')
runsh.write('#!/#   run.sh [options]\n')
runsh.write('#!/#\n')
runsh.write('#!/# Options:\n')
runsh.write('#!/#   --quiet     Do not be chatty (does nnt apply to pipeline stages)\n')
runsh.write('#!/#\n#!/#\n')

## write the top bit
runsh.write('export STUDYNAME=' + config['StudyName'] + '     # Data archive study name\n')
runsh.write('export XNAT_PROJECT=' + XNAT_PROJECT + '  # XNAT project name\n')
runsh.write('export MRUSER=' + config['MRUSER'] +'         # MR Unit FTP user\n')
runsh.write('export PROJECTDIR='+ projectdir +'\n')

## write the export from XNAT
for siteinfo in config['Sites']:
    site = siteinfo.keys()[0]
    xnat = siteinfo[site]['XNAT_Archive']
    runsh.write('export XNAT_ARCHIVE_' + site + '=' + xnat + '\n')

## write the gold standard info
if len(SiteNames) == 1:
    runsh.write('export ' + site + '_STANDARD=')
    runsh.write(projectdir + '/metadata/gold_standards/\n')
else:
    for site in SiteNames:
        runsh.write('export ' + site + '_STANDARD=')
        runsh.write(projectdir + '/metadata/gold_standards/' + site + '\n')

## set some settings and load datman module
runsh.write('args="$@"                           # commence ugly opt handling\n')
runsh.write('DATESTAMP=$(date +%Y%m%d)\n\n')
runsh.write('source /etc/profile\n')
runsh.write('module load /archive/data-2.0/code/datman.module\n')
runsh.write('export PATH=$PATH:${PROJECTDIR}/bin\n')

## define the message function
runsh.write('function message () { [[ "$args" =~ "--quiet" ]] || echo "$(date): $1"; }\n')

## start running stuff
runsh.write('{\n')
runsh.write('  message "Running pipelines for study: $STUDYNAME"\n\n')

## get the scans from the camh server
runsh.write('  message "Get new scans..."\n')
runsh.write('  dm-sftp-sync.sh ${MRUSER}@mrftp.camhpet.ca "${MRUSER}*/*" ${PROJECTDIR}/data/zips\n\n')

## link.py part
runsh.write('  message "Link scans..."\n')
runsh.write('  link.py \\\n')
runsh.write('    --lookup=${PROJECTDIR}/metadata/scans.csv \\\n')
runsh.write('    ${PROJECTDIR}/data/dicom/ \\\n')
runsh.write('    ${PROJECTDIR}/data/zips/*.zip\n\n')

## XNAT uploading from our server
runsh.write('  message "Uploading new scans to XNAT..."\n')
runsh.write('  dm-xnat-upload.sh \\\n')
runsh.write('    ${XNAT_PROJECT} \\\n')
runsh.write('    ${XNAT_ARCHIVE_CMH} \\\n')
runsh.write('    ${PROJECTDIR}/data/dicom \\\n')
runsh.write('    ${PROJECTDIR}/metadata/xnat-credentials\n\n')


## Extracting the scans from XNAT
runsh.write('  message "Extract new scans from XNAT..."\n')
## load modules for file conversion
runsh.write('  module load slicer/4.4.0 mricron/0.20140804 minc-toolkit/1.0.01\n')
for site in SiteNames:
    runsh.write('  xnat-extract.py ' + \
        '--blacklist ${PROJECTDIR}/metadata/blacklist.csv ' + \
        '--datadir ${PROJECTDIR}/data '\
        '--exportinfo ${PROJECTDIR}/metadata/exportinfo.csv '+ \
        '${XNAT_ARCHIVE_' + site + '}/*\n')
## load modules for file conversion
runsh.write('  module unload slicer/4.4.0 mricron/0.20140804 minc-toolkit/1.0.01\n')

## do the dicom header check
runsh.write('\n  message "Checking DICOM headers... "\n')
for sitedict in config['Sites']:
    site = config['Sites'][0].keys()[0]
    runsh.write('  dm-check-headers.py ')
    if 'Ingnore_Headers' in sitedict[site].keys():
        runsh.write('--ignore-headers '+ ','.join(sitedict[site]['Ingnore_Headers']) + ' ')
    runsh.write('${' + site + '_STANDARD} ' + \
        '${PROJECTDIR}/dcm/' + PREFIX + '_' + site + '_*\n')

## do the gradient directions check
runsh.write('\n  message "Checking gradient directions..."\n')
if len(SiteNames) == 1:
    runsh.write('  dm-check-bvecs.py ${PROJECTDIR} ${' + site + '_STANDARD}\n')
else:
    for site in SiteNames:
        runsh.write('  dm-check-bvecs.py ${PROJECTDIR} ${' + site + '_STANDARD} ' + site + '\n')

### if specified - link the sprial scans
if config['PipelineSettings'] != None:
    if 'dm-link-sprl.sh' in config['PipelineSettings'].keys():
        runsh.write('\n  message "Link spiral scans..."')
        runsh.write('\n  dm-link-sprl.sh ${PROJECTDIR}/data\n')

## load all the pipeline tools
runsh.write('\n  module load AFNI/2014.12.16 FSL/5.0.7 matlab/R2013b_concurrent \n\n')

## generate qc ness
runsh.write('  message "Generating QC documents..."\n')
runsh.write('  qc.py --datadir ${PROJECTDIR}/data/ --qcdir ${PROJECTDIR}/qc --dbdir ${PROJECTDIR}/qc\n')
runsh.write('  qc-report.py ${PROJECTDIR}\n\n')

if config['PipelineSettings'] != None:
    if 'qc-phantom.py' in config['PipelineSettings'].keys():
        runsh.write('  message "Updating phantom plots..."\n')
        runsh.write('  qc-phantom.py ${PROJECTDIR} ' + \
            str(config['PipelineSettings']['qc-phantom.py']['NTP']) + ' ' + \
            config['PipelineSettings']['qc-phantom.py']['Sites'] + '\n')
        runsh.write('  web-build.py ${PROJECTDIR} \n\n')

runsh.write('\n  module unload AFNI/2014.12.16 FSL/5.0.7 matlab/R2013b_concurrent \n\n')

## pushing stuff to git hub
runsh.write('  message "Pushing QC documents to github..."\n')
runsh.write('  ( # subshell invoked to handle directory change\n')
runsh.write('    cd ${PROJECTDIR}\n')
runsh.write('    git add qc/\n')
runsh.write('    git add metadata/checklist.csv\n')
runsh.write('    git diff --quiet HEAD || git commit -m "Autoupdating QC documents"\n')
runsh.write('    git push --quiet\n')
runsh.write('  )\n\n')

## pushing website ness
if config['PipelineSettings'] != None:
    if 'qc-phantom.py' in config['PipelineSettings'].keys():
        runsh.write('  message "Pushing website data to github..."\n')
        runsh.write('  (  \n')
        runsh.write('    cd ${PROJECTDIR}/website\n')
        runsh.write('    git add .\n')
        runsh.write('    git commit -m "Updating QC plots"\n')
        runsh.write('    git push --quiet\n')
        runsh.write('  )\n\n')

if 'PDT2' in ScanTypes:
    runsh.write('  message "Split the PDT2 images..."\n')
    runsh.write('  (\n  module load FSL/5.0.7 \n')
    runsh.write('  dm-proc-split-pdt2.py ${PROJECTDIR}/data/nii/*/*_PDT2_*.nii.gz\n')
    runsh.write('  module unload FSL/5.0.7\n  )\n\n')

if 'DTI60-1000' in ScanTypes:
    runsh.write('  message "Running dtifit..."\n')
    runsh.write('  module load FSL/5.0.7 \n')
    runsh.write('  dm-proc-dtifit.py --datadir ${PROJECTDIR}/data/ --outputdir ${PROJECTDIR}/data/dtifit\n\n')

    runsh.write('  message "Running ditfit qc..."\n')
    runsh.write('  dtifit-qc.py --tag DTI60 ${PROJECTDIR}/data/dtifit/\n\n')

    runsh.write('  message "Running enignmaDTI..."\n')
    runsh.write('  dm-proc-enigmadti.py --calc-all --tag2 "DTI60" --QC-transfer ${PROJECTDIR}/metadata/checklist.csv ${PROJECTDIR}/data/dtifit ${PROJECTDIR}/data/enigmaDTI\n\n')
    runsh.write('  module unload FSL/5.0.7 \n\n')

if 'T1' in ScanTypes:
    runsh.write('  message "Running freesurfer..."\n')
    runsh.write('  dm-proc-freesurfer.py ' + \
        '--FS-option \'-notal-check -cw256\' ' + \
        '--QC-transfer ${PROJECTDIR}/metadata/checklist.csv ' + \
        '${PROJECTDIR}/data/nii/ ${PROJECTDIR}/data/freesurfer/ \n\n')

if len(set(['EMP','OBS','IMI','RST']).intersection(ScanTypes)) > 0:
    # load modules for epitome
    runsh.write('  module load freesurfer/5.3.0\n')
    runsh.write('  module load AFNI/2014.12.16 FSL/5.0.7 matlab/R2013b_concurrent \n')
    runsh.write('  export SUBJECTS_DIR=${PROJECTDIR}/data/freesurfer\n\n')

    if 'EMP' in ScanTypes:
        runsh.write('  message "Analyzing empathic accuracy data..."\n')
        runsh.write('  dm-proc-ea.py ${PROJECTDIR} /scratch/clevis /archive/data-2.0/code/datman/assets/150409-compcor-nonlin-8fwhm.sh ${PROJECTDIR}/metadata/design\n\n')

    if ('IMI' in ScanTypes) & ('OBS' in ScanTypes):
        runsh.write('  message "Analyzing imitate observe data..."\n')
        runsh.write('  dm-proc-imob.py ${PROJECTDIR} /scratch/clevis /archive/data-2.0/code/datman/assets/150409-compcor-nonlin-8fwhm.sh ${PROJECTDIR}/metadata/design\n\n')

    if 'RST' in ScanTypes:
        runsh.write('  message "Analyzing resting state data..."\n')
        runsh.write('  dm-proc-rest.py ${PROJECTDIR} /scratch/clevis /archive/data-2.0/code/datman/assets/150409-compcor-nonlin-8fwhm.sh ${PROJECTDIR}/metadata/design\n\n')
    # unload modules for epitome
    runsh.write('  module unload freesurfer/5.3.0\n')
    runsh.write('  module unload AFNI/2014.12.16 FSL/5.0.7 matlab/R2013b_concurrent \n\n')

### tee out a log
runsh.write('  message "Done."\n')
runsh.write('} | tee -a ${PROJECTDIR}/logs/run-all-${DATESTAMP}.log\n')

## close the file
runsh.close()

### change anything that needs to be changed with Find and Replace
if config['FindandReplace'] != None :
    with open (outputfile,'r') as runsh:
        allrun = runsh.read()
    for block in config['FindandReplace']:
        toFind = block['Find']
        toReplace = block['Replace']
        if block['Find'] in allrun:
            allrun = allrun.replace(block['Find'],block['Replace'])
        else:
            print('WARNING: could not find {} in run.sh file'.format(block['Find']))
    with open (outputfile,'w') as runsh:
        runsh.write(allrun)
