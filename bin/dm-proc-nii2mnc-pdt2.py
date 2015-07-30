#!/usr/bin/env python
"""
Converts the PD and T2 images from nifty to minc.

Usage:
    dm-proc-nii2mnc-pdt2.py <projectdir>

Options:
  --T2-tag	STR			   Tag in filename that indicates it's a T2 (default = "_T2_")
  --PD-tag	STR			   Tag in filename that indicates it's a PD (default = "_PD_")
  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run

Take the T2 and PD images from the nii/ and covertes them to minc in mnc/.

It is expected that the input images is named according to the Scan ID filename
format, and has the tag 'PDT2'. The output PD file has the tag "PD" and the
output T2 file has the tag "PD".
"""
from docopt import docopt
import datman as dm
import datman.utils
import datman.scanid
import glob
import os.path
import shutil
import sys
import subprocess
import datetime

arguments       = docopt(__doc__)
projectdir      = arguments['<projectdir>']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']
T2_TAG          = arguments['--T2-tag']
PD_TAG          = arguments['--PD-tag']

if DEBUG: print arguments
#set default tag values
if T2_TAG == None: T2_TAG = '_T2_'
if PD_TAG == None: PD_TAG = '_PD_'

### Erin's little function for running things in the shell
def docmd(cmdlist):
    "sends a command (inputed as a list) to the shell"
    if DEBUG: print ' '.join(cmdlist)
    if not DRYRUN: subprocess.call(cmdlist)

#mkdir a tmpdir for the
tempdir = tempfile.mkdtemp()

##
projectdir = os.path.normpath(projectdir)
mncdir = os.path.join(projectdir,'data','mnc')
niidir = os.path.join(projectdir,'data','nii')
for tag in [T2_TAG, PD_TAG]:
    images = glob.glob('{}/*/*{}*.nii.gz'.format(niidir,tag))
    for image in images:
        # if target exists - then skip
        targetmnc = image.replace('nii','mnc').replace('gz','')
        if os.path.isfile(targetmnc)==False:
            # get the basename without extension
            imageb = os.path.basename(image).os.path.splitext[0]
            docmd(['cp',image,tmpdir]) #copying to tmpdir so I can gunzip it
            docmd(['gunzip',os.path.join(tmpdir,os.path.basename(image))]) #gunzip it
            # convert gunzipped nifty to mnc
            docmd(['nii2mnc', os.path.join(tmpdir,imageb+'.nii'),targetmnc])

#get rid of the tmpdir
shutil.rmtree(tempdir)
