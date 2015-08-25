#!/usr/bin/env python
"""
Run QC -stuff for dtifit outputs.

Usage:
  dtifit-qc.py [options] <dtifitdir>

Arguments:
    <dtifitdir>        Top directory for the output file structure

Options:
  --QCdir <FILE>           Full path to location of QC outputs (defalt: <outputdir>/QC')
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

arguments       = docopt(__doc__)
dtifitdir       = arguments['<dtifitdir>']
QCdir           = arguments['--QCdir']
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
        '-crop', '82x33%+0+218', os.path.join(tmpdir,'cor.gif')])
    docmd(['convert', input_gif,\
        '-crop', '82x33%+0+438', os.path.join(tmpdir,'ax.gif')])
    docmd(['montage', '-mode', 'concatenate', '-tile', '3x1', \
        os.path.join(tmpdir,'sag.gif'),\
        os.path.join(tmpdir,'cor.gif'),\
        os.path.join(tmpdir,'ax.gif'),\
        os.path.join(output_gif)])

def mask_overlay(backgound_nii,mask_nii, overlay_gif):
    '''
    use slices from fsl to overlay the mask on the background (both nii)
    then make the grid to a line for easier scrolling during QC
    '''
    docmd(['slices', backgound_nii, mask_nii, '-o', os.path.join(tmpdir,'BOmasked.gif')])
    gif_gridtoline(os.path.join(tmpdir,'BOmasked.gif'),overlay_gif)

def V1_overlay(backgound_nii,V1_nii, overlay_gif):
    '''
    use fslsplit to split the V1 image and take pictures of each direction
    use slices from fsl to get the background and V1 picks (both nii)
    recolor the V1 image using imagemagick
    then make the grid to a line for easier scrolling during QC
    '''
    docmd(['slices',background_nii,'-o',os.path.join(tmpdir,"background.gif")])
    docmd(['fslsplit', V1_nii, os.path.join(tmpdir,"V1")])
    for axis in ['0000','0001','0002']
        docmd(['fslmaths',os.path.join(tmpdir,'V1'+axis+'.nii.gz'), '-abs', \
            '-mul', background_nii, os.path.join(tmpdir,'V1'+axis+'abs.nii.gz')])
        docmd(['slices',os.path.join(tmpdir,'V1'+axis+'abs.nii.gz'),'-o',os.path.join(tmpdir,'V1'+axis+'abs.gif')])
        docmd(['convert', os.path.join(tmpdir,'V1'+axis+'abs.gif'),\
                '-fuzz', '15%', '-transparent', 'black', os.path.join(tmpdir,'V1'+axis+'set.gif')])
        docmd(['convert', os.path.join(tmpdir,'V10000set.gif'),\
            os.path.join(tmpdir,'V10001set.gif'), os.path.join(tmpdir,'V10002set.gif'),\
            '-set', 'colorspace', 'RGB', '-combine', '-set', 'colorspace', 'sRGB',\
            os.path.join(tmpdir,'dirmap.gif')])
        gif_gridtoline(os.path.join(tmpdir,'dirmap.gif'),overlay_gif)


## find the files that match the resutls tag...first using the place it should be from doInd-enigma-dti.py
## find those subjects in input who have not been processed yet and append to checklist
subids_to_qc = dm.utils.get_subjects(dtifitdir)

#mkdir a tmpdir for the
tmpdirbase = tempfile.mkdtemp()
QC_bet_dir = os.path.join(QCdir,'BET')
QC_V1 = os.path.join(QCdir, 'directions')
dm.utils.makedirs(QC_bet_dir)
dm.utils.makedirs(QC_V1)

maskpics = []
V1pics = []
for subid in subids_to_qc:
    s_dtifitdir = os.path.join(dtifitdir,subid)


    mask_overlay(backgound_nii,mask_nii, overlay_gif)
    V1_overlay(backgound_nii,V1_nii, overlay_gif)

tags = ['FA']
if CALC_MD: tags = tags + ['MD']
if CALC_ALL: tags = tags + ['MD','RD','AD']
for tag in tags:

    QCskeldir = os.path.join(QCdir, tag + 'skel')
    dm.utils.makedirs(QCskeldir)

    pics = []
    for i in range(len(checklist)):
        ## if an FA has been chosen (i.e. doInd-enigma-dti.py was run...)
        if pd.isnull(checklist['FA_nii'][i]) == False:
            ## read the subject vars from the checklist
            subid = str(checklist['id'][i])
            FA_nii = str(checklist['FA_nii'][i])
            base_nii = FA_nii.replace('FA.nii.gz','')

            ### find inputs based on tag
            to_target = os.path.join(outputdir,subid,tag,base_nii + tag + '_to_target.nii.gz')
            skel = os.path.join(outputdir,subid,tag,base_nii +  tag + 'skel.nii.gz')
            output_gif = os.path.join(QCskeldir,base_nii +  tag + 'skel.gif')

            ## bet mask on top of B0 map
            slices <BOmap> <betmask> -o maskedBO.gif

            ## V1 directions on top of stuff

            ## fa map on top of T1 (for L-R)

            # run the overlay function
            if os.path.isfile(output_gif) == False:
                overlay_skel(to_target,skel,output_gif)

            ## append it to the list for the QC file
            pics.append(output_gif)

    ## write an html page that shows all the pics
    qchtml = open(os.path.join(QCdir,tag + '_qcskel.html'),'w')
    qchtml.write('<HTML><TITLE>' + tag + 'skeleton QC page</TITLE>')
    qchtml.write('<BODY BGCOLOR=#333333>\n')
    qchtml.write('<h1><font color="white">' + tag + ' skeleton QC page</font></h1>')
    for pic in pics:
        relpath = os.path.relpath(pic,QCdir)
        qchtml.write('<a href="'+ relpath + '" style="color: #99CCFF" >')
        qchtml.write('<img src="' + relpath + '" "WIDTH=800" > ')
        qchtml.write(relpath + '</a><br>\n')
    qchtml.write('</BODY></HTML>\n')
    qchtml.close() # you can omit in most cases as the destructor will call it

#get rid of the tmpdir
shutil.rmtree(tmpdir)
