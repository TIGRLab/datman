#!/usr/bin/env python
"""
Run QC -stuff for enigma dti pipeline.

Usage:
  dm-qc-enigma.py [options] <outputdir>

Arguments:
    <outputdir>        Top directory for the output file structure

Options:
  --calc-MD                Also run QC for MD values,
  --calc-all               Also run QC for for MD, AD, and RD values.
  --checklist <FILE>       Filename of the engima checklist (defalt: <outputdir>/ENIGMA-DTI-checklist.csv')
  --results <FILE>...      Filenames for the results csv outputs (for outliers checks - still coming)
  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run
  --help                   Print help

DETAILS
This creates some QC outputs from of enigmaDTI pipeline stuff.
QC outputs are placed within <outputdir>/QC.
Right now QC constist of pictures of the skeleton on the registered image, for every subject.
Pictures are assembled in html pages for quick viewing.
This is configured to work for outputs of the enigma dti pipeline (dm-proc-enigmadti.py).

The inspiration for these QC practices come from engigma DTI
http://enigma.ini.usc.edu/wp-content/uploads/DTI_Protocols/ENIGMA_FA_Skel_QC_protocol_USC.pdf

Future plan: add section that checks results for normality and identifies outliers..

Requires datman python enviroment, FSL and imagemagick.

Written by Erin W Dickie, August 14 2015
"""
from docopt import docopt
import pandas as pd
import datman as dm
import datman.utils
import datman.scanid
import os
import tempfile
import shutil

arguments       = docopt(__doc__)
outputdir       = arguments['<outputdir>']
resultsfiles    = arguments['--results']
checklistfile   = arguments['--checklist']
CALC_MD         = arguments['--calc-MD']
CALC_ALL        = arguments['--calc-all']
VERBOSE         = arguments['--verbose']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']

if DEBUG: print arguments

## if no result file is given use the default name
outputdir = os.path.normpath(outputdir)
if checklistfile == None:
    checklistfile = os.path.join(outputdir,'ENIGMA-DTI-checklist.csv')

def overlay_skel(background_nii, skel_nii,overlay_gif):
    '''
    create an overlay image montage of
    skel_nii image in magenta on top of the background_nii
    Uses FSL slicer and imagemagick tools

    backgroud_nii   the background image in nifty format (i.e. "FA_to_target.nii.gz")
    skel_nii        the nifty image to be overlayed in magenta (i.e. "FAskel.nii.gz")
    overlay_gif     the name of the output (output.gif)
    '''
    dm.utils.run(['slices',background_nii,'-o',os.path.join(tmpdir,subid + "to_target.gif")])
    dm.utils.run(['slices',skel_nii,'-o',os.path.join(tmpdir,subid + "skel.gif")])
    dm.utils.run(['convert', '-negate', os.path.join(tmpdir,subid + "skel.gif"), \
        '+level-colors', 'magenta,', \
        '-fuzz', '10%', '-transparent', 'white', \
        os.path.join(tmpdir,subid + 'skel_mag.gif')])
    dm.utils.run(['composite', os.path.join(tmpdir,subid + 'skel_mag.gif'),
        os.path.join(tmpdir,subid + 'to_target.gif'),
        os.path.join(tmpdir,subid + 'cskel.gif')])
    dm.utils.run(['convert', os.path.join(tmpdir,subid + 'cskel.gif'),\
        '-crop', '100x33%+0+0', os.path.join(tmpdir,subid + '_sag.gif')])
    dm.utils.run(['convert', os.path.join(tmpdir,subid + 'cskel.gif'),\
        '-crop', '82x33%+0+218', os.path.join(tmpdir,subid + '_cor.gif')])
    dm.utils.run(['convert', os.path.join(tmpdir,subid + 'cskel.gif'),\
        '-crop', '82x33%+0+438', os.path.join(tmpdir,subid + '_ax.gif')])
    dm.utils.run(['montage', '-mode', 'concatenate', '-tile', '3x1', \
        os.path.join(tmpdir,subid + '_sag.gif'),\
        os.path.join(tmpdir,subid + '_cor.gif'),\
        os.path.join(tmpdir,subid + '_ax.gif'),\
        os.path.join(overlay_gif)])

## find the files that match the resutls tag...first using the place it should be from doInd-enigma-dti.py
checklist = pd.read_csv(checklistfile, sep=',', dtype=str, comment='#')
QCdir = os.path.join(outputdir,'QC')

#mkdir a tmpdir for the
tmpdir = tempfile.mkdtemp()

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
