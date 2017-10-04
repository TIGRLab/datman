#!/usr/bin/env python
"""
This aligns some .mnc files with bestlinreg.pl then mean's them with mincaverage

Usage:
  dm-proc-mncmean.py [options] <outputmnc> <inputmnc>...

Arguments:
    <inputmnc>...   Paths to directory containing .mnc images to align and mean
    <outputmnc>     Filename (ending in *)

Options:
  --tmpdir <tmpdir>        Place to put the intermediate files (should build a default for this)
  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run

DETAILS
Requires minc tools these can be loaded as modules with:
module load minc-toolkit/1.0.01 minc-toolkit-extras/1.0
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
inputs          = arguments['<inputmnc>']
output          = arguments['<outputmnc>']
tmpdir          = arguments['--tmpdir']
VERBOSE         = arguments['--verbose']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']

if tmpdir == None:
    tmpdir = os.path.join(os.path.dirname(output),'tmp')

# if in DEBUG mode than print all the important arguments to the screen
if DEBUG:
    for i in range(0,len(inputs)):
        print "input {}: {}".format(i,inputs[i])
    print "output is {}".format(output)
    print "tmpdir is: {}".format(tmpdir)

## make the tmpdir
dm.utils.makedirs(tmpdir)

#align the others to the first input
# start of list of the files that will be in the mincaverage command
MEANcmd = ['mincaverage',inputs[0]]

# start resampling the other files and adding them to the final command
for i in range(1,len(inputs)):
    thistmpmnc = os.path.join(tmpdir,'tmp' + str(i) + '.mnc')
    #runs bestlinreg.pl for each image
    dm.utils.run(['bestlinreg.pl', inputs[i], inputs[0],
        os.path.join(tmpdir,'tmp' + str(i) + '.xfm'), thistmpmnc])
    MEANcmd.append(thistmpmnc) #add the resampled output to the list of stuff to mean

#add an output file to the MEANcmd
MEANcmd.append(output)

#now run the mincmean command
dm.utils.run(MEANcmd)

#remove the tmpdir if not for debugging
dm.utils.run(['rm', '-rf', tmpdir])
