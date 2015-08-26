#!/usr/bin/env python
"""
Run QC -stuff for dtifit outputs.

Usage:
  dtifit-qc.py [options] <dtifitdir>

Arguments:
    <dtifitdir>        Top directory for the output file structure

Options:
  --QCdir <path>           Full path to location of QC outputs (defalt: <outputdir>/QC')
  --tag <tag>              Only QC files with this string in their filename (ex.'DTI60')
  --subject <subid>        Only process the subjects given (good for debugging, default is to do all subs in folder)
  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run
  --help                   Print help

DETAILS
This creates some QC outputs from of ditfit pipeline stuff.
QC outputs are placed within <outputdir>/QC unless specified otherwise ("--QCdir <path").
Right now QC constist of pictures for every subject.
Pictures are assembled in html pages for quick viewing.

The inspiration for these QC practices come from engigma DTI
http://enigma.ini.usc.edu/wp-content/uploads/DTI_Protocols/ENIGMA_FA_Skel_QC_protocol_USC.pdf

Future plan: add section that checks results for normality and identifies outliers..

Requires datman python enviroment, FSL and imagemagick.

Written by Erin W Dickie, August 25 2015
"""
from docopt import docopt
import pandas as pd
import datman as dm
import datman.utils
import datman.scanid
import os
import subprocess
import tempfile
import shutil
import glob

arguments       = docopt(__doc__)
dtifitdir       = arguments['<dtifitdir>']
QCdir           = arguments['--QCdir']
TAG             = arguments['--tag']
SUBID           = arguments['--subject']
VERBOSE         = arguments['--verbose']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']

if DEBUG: print arguments
if QCdir == None: QCdir = os.path.join(dtifitdir,'QC')

### Erin's little function for running things in the shell
def docmd(cmdlist):
    "sends a command (inputed as a list) to the shell"
    if DEBUG: print ' '.join(cmdlist)
    if not DRYRUN: subprocess.call(cmdlist)

def gif_gridtoline(input_gif,output_gif):
    '''
    uses imagemagick to take a grid from fsl slices and convert to one line (like in slicesdir)
    '''
    docmd(['convert', input_gif,\
        '-crop', '100x33%+0+0', os.path.join(tmpdir,'sag.gif')])
    docmd(['convert', input_gif,\
        '-crop', '100x33%+0+128', os.path.join(tmpdir,'cor.gif')])
    docmd(['convert', input_gif,\
        '-crop', '100x33%+0+256', os.path.join(tmpdir,'ax.gif')])
    docmd(['montage', '-mode', 'concatenate', '-tile', '3x1', \
        os.path.join(tmpdir,'sag.gif'),\
        os.path.join(tmpdir,'cor.gif'),\
        os.path.join(tmpdir,'ax.gif'),\
        os.path.join(output_gif)])

def mask_overlay(background_nii,mask_nii, overlay_gif):
    '''
    use slices from fsl to overlay the mask on the background (both nii)
    then make the grid to a line for easier scrolling during QC
    '''
    docmd(['slices', background_nii, mask_nii, '-o', os.path.join(tmpdir,'BOmasked.gif')])
    gif_gridtoline(os.path.join(tmpdir,'BOmasked.gif'),overlay_gif)

def V1_overlay(background_nii,V1_nii, overlay_gif):
    '''
    use fslsplit to split the V1 image and take pictures of each direction
    use slices from fsl to get the background and V1 picks (both nii)
    recolor the V1 image using imagemagick
    then make the grid to a line for easier scrolling during QC
    '''
    docmd(['slices',background_nii,'-o',os.path.join(tmpdir,"background.gif")])
    docmd(['fslmaths',background_nii,'-thr','0.15','-bin',os.path.join(tmpdir,'FAmask.nii.gz')])
    docmd(['fslsplit', V1_nii, os.path.join(tmpdir,"V1")])
    for axis in ['0000','0001','0002']:
        docmd(['fslmaths',os.path.join(tmpdir,'V1'+axis+'.nii.gz'), '-abs', \
            '-mul', os.path.join(tmpdir,'FAmask.nii.gz'), os.path.join(tmpdir,'V1'+axis+'abs.nii.gz')])
        docmd(['slices',os.path.join(tmpdir,'V1'+axis+'abs.nii.gz'),'-o',os.path.join(tmpdir,'V1'+axis+'abs.gif')])
        # docmd(['convert', os.path.join(tmpdir,'V1'+axis+'abs.gif'),\
        #         '-fuzz', '15%', '-transparent', 'black', os.path.join(tmpdir,'V1'+axis+'set.gif')])
    docmd(['convert', os.path.join(tmpdir,'V10000abs.gif'),\
        os.path.join(tmpdir,'V10001abs.gif'), os.path.join(tmpdir,'V10002abs.gif'),\
        '-set', 'colorspace', 'RGB', '-combine', '-set', 'colorspace', 'sRGB',\
        os.path.join(tmpdir,'dirmap.gif')])
    gif_gridtoline(os.path.join(tmpdir,'dirmap.gif'),overlay_gif)


## find the files that match the resutls tag...first using the place it should be from doInd-enigma-dti.py
## find those subjects in input who have not been processed yet and append to checklist
## glob the dtifitdir for FA files to get strings
if SUBID != None:
    allFAmaps = glob.glob(dtifitdir + '/' + SUBID + '/*dtifit_FA*')
else:
    # if no subids given - just glob the whole DTI fit ouput
    allFAmaps = glob.glob(dtifitdir + '/*/*dtifit_FA*')
if DEBUG : print("FAmaps before filtering: {}".format(allFAmaps))

# if filering tag is given...filter for it
if TAG != None:
    allFAmaps = [ v for v in allFAmaps if TAG in v ]
if DEBUG : print("FAmaps after filtering: {}".format(allFAmaps))

#mkdir a tmpdir for the
tmpdirbase = tempfile.mkdtemp()
# tmpdirbase = os.path.join(QCdir,'tmp')
# dm.utils.makedirs(tmpdirbase)

# make the output directories
QC_bet_dir = os.path.join(QCdir,'BET')
QC_V1_dir = os.path.join(QCdir, 'directions')
dm.utils.makedirs(QC_bet_dir)
dm.utils.makedirs(QC_V1_dir)

maskpics = []
V1pics = []
for FAmap in allFAmaps:
    ## manipulate the full path to the FA map to get the other stuff
    subid = os.path.basename(os.path.dirname(FAmap))
    tmpdir = os.path.join(tmpdirbase,subid)
    dm.utils.makedirs(tmpdir)
    basename = os.path.basename(FAmap).replace('dtifit_FA.nii.gz','')
    pathbase = FAmap.replace('dtifit_FA.nii.gz','')

    maskpic = os.path.join(QC_bet_dir,basename + 'b0_bet_mask.gif')
    maskpics.append(maskpic)
    if os.path.exists(maskpic) == False:
        mask_overlay(pathbase + 'b0.nii.gz',pathbase + 'b0_bet_mask.nii.gz', maskpic)

    V1pic = os.path.join(QC_V1_dir,basename + 'dtifit_V1.gif')
    V1pics.append(V1pic)
    if os.path.exists(V1pic) == False:
        V1_overlay(FAmap,pathbase + 'dtifit_V1.nii.gz', V1pic)


## write an html page that shows all the BET mask pics
qchtml = open(os.path.join(QCdir,'qc_BET.html'),'w')
qchtml.write('<HTML><TITLE>DTIFIT BET QC page</TITLE>')
qchtml.write('<BODY BGCOLOR=#333333>\n')
qchtml.write('<h1><font color="white">DTIFIT BET QC page</font></h1>')
for pic in maskpics:
    relpath = os.path.relpath(pic,QCdir)
    qchtml.write('<a href="'+ relpath + '" style="color: #99CCFF" >')
    qchtml.write('<img src="' + relpath + '" "WIDTH=800" > ')
    qchtml.write(relpath + '</a><br>\n')
qchtml.write('</BODY></HTML>\n')
qchtml.close() # you can omit in most cases as the destructor will call it

## write an html page that shows all the V1 pics
qchtml = open(os.path.join(QCdir,'qc_directions.html'),'w')
qchtml.write('<HTML><TITLE>DTIFIT directions QC page</TITLE>')
qchtml.write('<BODY BGCOLOR=#333333>\n')
qchtml.write('<h1><font color="white">DTIFIT directions QC page</font></h1>')
for pic in V1pics:
    relpath = os.path.relpath(pic,QCdir)
    qchtml.write('<a href="'+ relpath + '" style="color: #99CCFF" >')
    qchtml.write('<img src="' + relpath + '" "WIDTH=800" > ')
    qchtml.write(relpath + '</a><br>\n')
qchtml.write('</BODY></HTML>\n')
qchtml.close() # you can omit in most cases as the destructor will call it


#get rid of the tmpdir
shutil.rmtree(tmpdirbase)
