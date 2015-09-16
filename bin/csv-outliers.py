#!/usr/bin/env python
"""
This uses pandas to identify outliers for any csv. It adds outlier notes as a new column

Usage:
  csv-outliers.py [options] <input.csv>

Arguments:
    <input.csv>                Inputfile (.csv format)

Options:
  --do-not-modify              Do not write the Outlier results out to the csv
  --write-summarystats FILE    Write the Means and Std out to a file
  -v,--verbose                 Verbose logging
  --debug                      Debug logging in Erin's very verbose style
  -n,--dry-run                 Dry run
  -h,--help                    Print help

DETAILS
Requires python enviroment with pandas and docopt:
module load use.own datman/edickie

Work in progress
"""
from docopt import docopt
import numpy as np
import os
import subprocess
import pandas as pd

arguments       = docopt(__doc__)
inputfile       = arguments['<input.csv>']
DONOTMODIFY     = arguments['--do-not-modify']
summaryout      = arguments['--write-summarystats']
VERBOSE         = arguments['--verbose']
DEBUG           = arguments['--debug']
DRYRUN          = arguments['--dry-run']

###
### Erin's little function for running things in the shell
def docmd(cmdlist):
    "sends a command (inputed as a list) to the shell"
    if DEBUG: print ' '.join(cmdlist)
    if not DRYRUN: subprocess.call(cmdlist)

inputdata = pd.read_csv(inputfile, sep=',', dtype=str, comment='#')
cols_to_test = inputdata.columns[1:].tolist()

for col in cols_to_test:
    inputdata[[col]] = inputdata[[col]].astype(float)

SummaryStats = inputdata.describe()

inputdata['AnyOutliers'] = pd.Series('',index=inputdata.index)

for idx in inputdata.index.tolist():
    for col in cols_to_test:
        value = inputdata.loc[idx,col]
        lower = SummaryStats.loc['mean',col] - 2.698*SummaryStats.loc['std',col]
        upper = SummaryStats.loc['mean',col] + 2.698*SummaryStats.loc['std',col]
        if value < lower:
            message = inputdata.loc[idx,'AnyOutliers'] + col + " is low;"
            inputdata.loc[idx,'AnyOutliers'] = message
        if value > upper:
            message = inputdata.loc[idx,'AnyOutliers'] + col + " is high;"
            inputdata.loc[idx,'AnyOutliers'] = message

    if VERBOSE: 
        if len(inputdata.loc[idx,'AnyOutliers']) > 1:
            print("{} {}".format(inputdata.ix[idx,0],inputdata.loc[idx,'AnyOutliers']))

## write the results out to a file
if DONOTMODIFY == False:
    inputdata.to_csv(inputfile, sep=',', index = False)

## if asked - write out the csv of SummaryStats
if summaryout != None:
    SummaryStats.to_csv(summaryout,sep=',')
