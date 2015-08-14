#!/usr/bin/env python
"""
Run QC -stuff for enigma dti pipeline.
By default the resutls are put in <outputdir>/ENIGMA-DTI-results.csv

Usage:
  enigmadti-qc.py [options] <outputdir>

Arguments:
    <outputdir>        Top directory for the output file structure

Options:
  --calc-MD                Also calculate values for MD,
  --calc-all               Also calculate values for MD, AD, and RD
  --gen-results            Genereate a new resutls file from the available data
  --ROItxt-tag STR         String within the individual participants results that identifies their data (default = 'ROIout_avg')
  --results FILE           Filename for the results csv output

  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run

DETAILS
This creates some QC outputs from of enigmaDTI pipeline stuff.
This is configured to work for file of the enigma dti pipeline.

Write now if pastes together a lot of info in pdfs like
http://enigma.ini.usc.edu/wp-content/uploads/DTI_Protocols/ENIGMA_FA_Skel_QC_protocol_USC.pdf

Requires matlab
module load matlab/R2014b_concurrent

Written by Erin W Dickie, July 30 2015
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

arguments       = docopt(__doc__)
outputdir       = arguments['<outputdir>']
resultsfile     = arguments['--results']
GENresults      = arguments['--gen-results']
ROItxt_tag      = arguments['--ROItxt-tag']
CALC_MD         = arguments['--calc-MD']
CALC_ALL        = arguments['--calc-all']
VERBOSE         = arguments['--verbose']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']

if DEBUG: print arguments

## if no result file is given use the default name
outputdir = os.path.normpath(outputdir)
if resultsfile == None:
    resultsfile = os.path.join(outputdir,'ENIGMA-DTI-checklist.csv')
if ROItxt_tag == None: ROItxt_tag = '_ROIout_avg'

SUBFOLDERS = True ## assume that the file is inside a heirarchy that contains folders with subject names
ENIGMAQCPATH = '/home/edickie/code/ENIGMA_QC/enigmaDTI_QC/'
### Erin's little function for running things in the shell
def docmd(cmdlist):
    "sends a command (inputed as a list) to the shell"
    if DEBUG: print ' '.join(cmdlist)
    if not DRYRUN: subprocess.call(cmdlist)

def overlay_skel(background_nii, skel_nii,overlay_gif):
    '''
    create an overlay image montage of
    skel_nii image in magenta on top of the background_nii
    Uses FSL slicer and imagemagick tools

    backgroud_nii   the background image in nifty format (i.e. "FA_to_target.nii.gz")
    skel_nii        the nifty image to be overlayed in magenta (i.e. "FAskel.nii.gz")
    overlay_gif     the name of the output (output.gif)
    '''
    docmd(['slices',background_nii,'-o',os.path.join(tmpdir,subid + "to_target.gif")])
    docmd(['slices',skel_nii,'-o',os.path.join(tmpdir,subid + "skel.gif")])
    docmd(['convert', '-negate', os.path.join(tmpdir,subid + "skel.gif"), \
        '+level-colors', 'magenta,', \
        '-fuzz', '10%', '-transparent', 'white', \
        os.path.join(tmpdir,subid + 'skel_mag.gif')])
    docmd(['composite', os.path.join(tmpdir,subid + 'skel_mag.gif'),
        os.path.join(tmpdir,subid + 'to_target.gif'),
        os.path.join(tmpdir,subid + 'cskel.gif')])
    docmd(['convert', os.path.join(tmpdir,subid + 'cskel.gif'),\
        '-crop', '100x33%+0+0', os.path.join(tmpdir,subid + '_sag.gif')])
    docmd(['convert', os.path.join(tmpdir,subid + 'cskel.gif'),\
        '-crop', '82x33%+0+218', os.path.join(tmpdir,subid + '_cor.gif')])
    docmd(['convert', os.path.join(tmpdir,subid + 'cskel.gif'),\
        '-crop', '82x33%+0+438', os.path.join(tmpdir,subid + '_ax.gif')])
    docmd(['montage', '-mode', 'concatenate', '-tile', '3x1', \
        os.path.join(tmpdir,subid + '_sag.gif'),\
        os.path.join(tmpdir,subid + '_cor.gif'),\
        os.path.join(tmpdir,subid + '_ax.gif'),\
        os.path.join(overlay_gif)])

## find the files that match the resutls tag...first using the place it should be from doInd-enigma-dti.py
results = pd.read_csv(resultsfile, sep=',', dtype=str, comment='#')
QCdir = os.path.join(outputdir,'QC')

#mkdir a tmpdir for the
tmpdir = tempfile.mkdtemp()

for tag in ['FA','MD','RD','AD']:

    QCskeldir = os.path.join(QCdir, tag + 'skel')
    dm.utils.makedirs(QCskeldir)

    pics = []
    for i in range(len(results)):
        ## read the subject vars from the checklist
        subid = str(results['id'][i])
        FA_nii = str(results['FA_nii'][i])
        base_nii = FA_nii.replace('FA.nii.gz','')

        ### find inputs based on tag
        if tag == 'FA':
            to_target = os.path.join(outputdir,subid,tag,base_nii + 'FA_to_target.nii.gz')
            skel = os.path.join(outputdir,subid,tag,base_nii + 'FA_to_target_FAskel.nii.gz')
            output_gif = os.path.join(QCskeldir,base_nii + 'FA_to_target_FAskel.gif')
        else:
            to_target = os.path.join(outputdir,subid,tag,base_nii + tag + '_to_target.nii.gz')
            skel = os.path.join(outputdir,subid,tag,base_nii +  tag + 'skel.nii.gz')
            output_gif = os.path.join(QCskeldir,base_nii +  tag + 'skel.gif')

        # run the overlay function
        if os.path.isfile(output_gif) == False:
            overlay_skel(to_target, skel,output_gif)

        ## append it to the list for the QC file
        pics.append(output_gif)

    qchtml = open(os.path.join(QCdir,tag + '_qcskel.html'),'w')
    qchtml.write('<HTML><TITLE>' + tag + 'skeleton QC page</TITLE><BODY BGCOLOR="#aaaaff">\n') # python will convert \n to os.linesep
    for pic in pics:
        relpath = os.path.relpath(pic,QCdir)
        qchtml.write('<a href="'+ relpath + '"><img src="' + relpath + '""')
        qchtml.write('WIDTH=800 > ' + relpath + '</a><br>\n')
    qchtml.write('</BODY></HTML>\n')
    qchtml.close() # you can omit in most cases as the destructor will call it

#get rid of the tmpdir
shutil.rmtree(tmpdir)
