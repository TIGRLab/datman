#!/usr/bin/env python
"""
Reads from yml config file and export info to determine what to put in run.sh for this project.
Then writes run.sh file.

Usage:
    tigr-write-runsh.py <config.yml>

Arguments:
    <config.yml>             Configuration file in yml format

Options:
    --outputfile             Full path to outputfile (default is ${PROJECTDIR}/bin/run.sh)
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
outputfile      = arguments['<outputfile>']
VERBOSE         = arguments['--verbose']
QUIET           = arguments['--quiet']

## Read in the configuration yaml file
if not os.path.isfile(config_yml):
    sys.exit("configuration file not found. Try again.")

with open(config_yml, 'r') as stream:
    config = yaml.load(stream)

ExpectedKeys = ['MRUSER','StudyName','PROJECTDIR','Sites','XNAT_PROJECT']
diffs = set(ExpectedKeys) - set(config.keys())
if len(diffs) > 0:
    sys.exit("configuration file missing {}".format(diffs))

projectdir =  os.path.normpath(config['PROJECTDIR'])
if not os.path.exists(projectdir):
    print("WARNING: PROJECTDIR {} does not exist".format(projectdir))

ExpectedKeys = ['MRUSER','StudyName','PROJECTDIR','Sites','XNAT_PROJECT']


## unless an outputfile is specified, set the output to ${PROJECTDIR}/bin/run.sh
if outputfile == None:
    ouputfile = os.path.join(projectdir,'bin','run.sh')

#open file for writing
runsh = open(filename,'w')

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
runsh.write('export XNAT_PROJECT=' config['XNAT_PROJECT'] + '  # XNAT project name\n')
runsh.write('export MRUSER=' + config['MRUSER'] +'         # MR Unit FTP user\n')
runsh.write('export PROJECTDIR='+ projectdir +'\n')

## write the export info
for site in config['Sites']:
    runsh.write('export XNAT_ARCHIVE_' + site + '=')
    runsh.write(config['Sites'][site]['XNAT_Archive'] + '\n')

## write the gold standard info
for site in config['Sites']:
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
runsh.write('  message "Running pipelines for study: $STUDYNAME"\n')

## get the scans from the camh server
runsh.write('  message "Get new scans..."\n')
runsh.write('  dm-sftp-sync.sh ${MRUSER}@mrftp.camhpet.ca "${MRUSER}*/*" ${PROJECTDIR}/data/zips\n')

## link.py part
runsh.write('  message "Link scans..."\n')
runsh.write('  link.py \\n')
runsh.write('    --lookup=${PROJECTDIR}/metadata/scans.csv \\n')
runsh.write('    ${PROJECTDIR}/data/dicom/ \\n')
runsh.write('    ${PROJECTDIR}/data/zips/*.zip\n\n')

## XNAT uploading from our server
runsh.write('  message "Uploading new scans to XNAT..."\n')
runsh.write('  dm-xnat-upload.sh \\n')
runsh.write('    ${XNAT_PROJECT} \\n')
runsh.write('    ${XNAT_ARCHIVE_CMH} \\n')
runsh.write('    ${PROJECTDIR}/data/dicom \\n')
runsh.write('    ${PROJECTDIR}/metadata/xnat-credentials\n\n')

## load modules for file conversion
runsh.write('  module load slicer/4.4.0 \n')
runsh.write('  module load mricron/0.20140804 \n')
runsh.write('  module load minc-toolkit/1.0.01\n\n')

## Extracting the scans from XNAT
runsh.write('  message "Extract new scans from XNAT..."\n')
for site in config['Sites']:
    runsh.write('  xnat-extract.py ' + \
        '--blacklist ${PROJECTDIR}/metadata/blacklist.csv ' + \
        '--datadir ${PROJECTDIR}/data '\
        '--exportinfo ${PROJECTDIR}/metadata/exportinfo-' + site + \
        site + '.csv ${XNAT_ARCHIVE_' + site + '}/*\n')

## unload the modules for file conversion
runsh.write('\n\n  module unload slicer/4.4.0\n')
runsh.write('  module unload mricron/0.20140804\n')
runsh.write('  module unload minc-toolkit/1.0.01\n\n')

## do the dicom header check
runsh.write('\n  message "Checking DICOM headers... "\n')
for site in config['Sites']:
    runsh.write('  dm-check-headers.py ${' + site + '_STANDARD} ' + \
        '${PROJECTDIR}/dcm/SPN01_' + site + '_*\n')

## do the gradient directions check
runsh.write('\n  message "Checking gradient directions..."\n')
for site in config['Sites']:
    runsh.write('  dm-check-bvecs.py ${PROJECTDIR} ${' + site + '_STANDARD} ' + site + '\n')

## load all the pipeline tools
runsh.write('\n  module load AFNI/2014.12.16 \n')
runsh.write('  module load FSL/5.0.7 \n')
runsh.write('  module load matlab/R2013b_concurrent\n')
runsh.write('  module load freesurfer/5.3.0 \n')
runsh.write('  module load python/2.7.9-anaconda-2.1.0-150119 \n')
runsh.write('  module load python-extras/2.7.9\n')
runsh.write('  export SUBJECTS_DIR=${PROJECTDIR}/data/freesurfer\n\n')

## generate qc ness
runsh.write('  message "Generating QC documents..."\n')
runsh.write('  qc.py --datadir ${PROJECTDIR}/data/ --qcdir ${PROJECTDIR}/qc --dbdir ${PROJECTDIR}/qc\n')
runsh.write('  qc-report.py ${PROJECTDIR}\n\n')

runsh.write('  message "Updating phantom plots..."\n')
runsh.write('  qc-phantom.py ${PROJECTDIR} 20 ' + ' '.join(config['Sites']) + '\n')
runsh.write('  web-build.py ${PROJECTDIR} \n\n')

runsh.write('  message "Pushing QC documents to github..."\n')
runsh.write('  ( # subshell invoked to handle directory change\n')
runsh.write('    cd ${PROJECTDIR}\n')
runsh.write('    git add qc/\n')
runsh.write('    git add metadata/checklist.csv\n')
runsh.write('    git diff --quiet HEAD || git commit -m "Autoupdating QC documents"\n')
runsh.write('    git push --quiet\n')
runsh.write('  )\n')
runsh.write('\n')
runsh.write('  message "Pushing website data to github..."\n')
runsh.write('  (  \n')
runsh.write('    cd ${PROJECTDIR}/website\n')
runsh.write('    git add .\n')
runsh.write('    git commit -m "Updating QC plots"\n')
runsh.write('    git push --quiet\n')
runsh.write('  )\n')
runsh.write('\n')
runsh.write('  message "Split the PDT2 images..."\n')
runsh.write('  (\n   dm-proc-split-pdt2.py ${PROJECTDIR}/data/nii/*/*_PDT2_*.nii.gz\n  )\n\n')

runsh.write('  message "Running freesurfer..."\n')
runsh.write('  dm-proc-freesurfer.py ${PROJECTDIR}\n\n')

runsh.write('  message "Analyzing empathic accuracy data..."\n')
runsh.write('  dm-proc-ea.py ${PROJECTDIR} /scratch/clevis /archive/data-2.0/code/datman/assets/150409-compcor-nonlin-8fwhm.sh ${PROJECTDIR}/metadata/design\n\n')

runsh.write('  message "Analyzing imitate observe data..."\n')
runsh.write('  dm-proc-imob.py ${PROJECTDIR} /scratch/clevis /archive/data-2.0/code/datman/assets/150409-compcor-nonlin-8fwhm.sh ${PROJECTDIR}/metadata/design\n\n')

runsh.write('  message "Analyzing resting state data..."\n')
runsh.write('  dm-proc-rest.py ${PROJECTDIR} /scratch/clevis /archive/data-2.0/code/datman/assets/150409-compcor-nonlin-8fwhm.sh ${PROJECTDIR}/metadata/design\n\n')

runsh.write('  message "Running dtifit..."\n')
runsh.write('  module load FSL/5.0.7\n')
runsh.write('  dm-proc-dtifit.py --tag "MRC" --fa_thresh "0.15" --datadir ${PROJECTDIR}/data/ --outputdir ${PROJECTDIR}/data/dtifit\n')
runsh.write('  dm-proc-dtifit.py --tag "ZHH" --datadir ${PROJECTDIR}/data/ --outputdir ${PROJECTDIR}/data/dtifit\n')
runsh.write('  dm-proc-dtifit.py --tag "CMH" --datadir ${PROJECTDIR}/data/ --outputdir ${PROJECTDIR}/data/dtifit\n\n')

runsh.write('  message "Running ditfit qc..."\n')
runsh.write('  dtifit-qc.py --tag DTI60 ${PROJECTDIR}/data/dtifit/\n\n')

runsh.write('  message "Running enignmaDTI..."\n')
runsh.write('  dm-proc-enigmadti.py --calc-all --QC-transfer ${PROJECTDIR}/metadata/checklist.csv ${PROJECTDIR}/data/dtifit ${PROJECTDIR}/data/enigmaDTI\n\n')

runsh.write('  module unload AFNI/2014.12.16 \n')
runsh.write('  module unload FSL/5.0.7\n')
runsh.write('  module unload matlab/R2013b_concurrent\n')
runsh.write('  module unload freesurfer/5.3.0 \n')
runsh.write('  module unload python/2.7.9-anaconda-2.1.0-150119 \n')
runsh.write('  module unload python-extras/2.7.9\n\n')

runsh.write('  message "Done."\n')
runsh.write('} | tee -a ${PROJECTDIR}/logs/run-all-${DATESTAMP}.log\n')
