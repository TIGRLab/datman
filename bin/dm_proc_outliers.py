#!/usr/bin/env python
"""
This uses pandas to identify outliers for any csv. It adds outlier notes as a
new column

Usage:
  dm_proc_outliers.py [options] <input.csv>

Arguments:
    <input.csv>                Inputfile (.csv format)

Options:
  --do-not-modify              Do not write the Outlier results out to the
                               inputfile.csv

  --read-stats FILE            Read the summary stats from an external file
                               instead of calculating them

  --write-stats FILE           Write the summary stats (including Means and
                               Stds) out to a file

  -v,--verbose                 Verbose logging
  --debug                      Debug logging in Erin's very verbose style
  -n,--dry-run                 Dry run
  -h,--help                    Print help

DETAILS
Requires python enviroment with pandas and docopt packages:
For example:
module load use.own datman/edickie

This reads in a csv file of data. It's assumed that the csv is formatted
in such a way that rows represent individual subjects (or scans) and columns
represent some numeric data that should (theortically) bo normally distributed
in the population (ex.volumes, FA values from DTI, cortical thickness etc.).
It is also assumed that the first column of the data is a subject id and
the data has headers.

This will test each value to see if I falls greater than 2.698 standand
deviations outside the mean. By default, a new column is appended to the
original csv with the message "<column_name> is high;" or "<column_name> is
low;" if this is the case. If you do not want this new column to appear in
your csv, use the option "--do-not-modify". If the "-v" or "--verbose" option
is given, this information is also printed to the screen where it can be
captured in a log file.

The sample means and standard deviations for each column are calculated
from the inputfile by default. However, using the option "--read-stats
<filename>", an external file can be specified with the summary statistics
(i.e. known values from a similar project with a larger sample..). If the
"--write-stats <filename>" option is chosen, the summary statistics calculated
from this csv are written out to the specified filename.
"""
import os
import sys

from docopt import docopt
import pandas as pd

arguments = docopt(__doc__)
inputfile = arguments['<input.csv>']
DONOTMODIFY = arguments['--do-not-modify']
summaryin = arguments['--read-stats']
summaryout = arguments['--write-stats']
VERBOSE = arguments['--verbose']
DEBUG = arguments['--debug']
DRYRUN = arguments['--dry-run']

if not os.path.isfile(inputfile):
    sys.exit("Input file {} doesn't exist.".format(inputfile))

# read the inputdata into a pandas dataframe
inputdata = pd.read_csv(inputfile, sep=',', dtype=str, comment='#')

# define columns to test as the second column to the end (excluding
# 'AnyOutliers or QC')
cols_to_test = inputdata.columns[1:].tolist()
cols_to_test = set(cols_to_test) - set(['AnyOutliers', 'QC'])

for col in cols_to_test:
    inputdata[[col]] = inputdata[[col]].astype(float)

# Get the summary stats for the calc
if not summaryin:
    '''
    if no stats file is specified, calculate them from the inputdata
    '''
    SummaryStats = inputdata.describe()
else:
    '''
    if a file is specified, check that it exists and load it
    '''
    if not os.path.isfile(summaryin):
        sys.exit("Summary Statistics file {} doesn't exist.".format(summaryin))
    SummaryStats = pd.read_csv(summaryin, sep=',', index_col=0)

if 'AnyOutliers' not in inputdata.columns:
    inputdata['AnyOutliers'] = pd.Series('', index=inputdata.index)

for idx in inputdata.index.tolist():
    message = ''
    for col in cols_to_test:
        '''
        for every cell, check if it is an outlier
        '''
        value = inputdata.loc[idx, col]
        lower = SummaryStats.loc['mean', col] - 2.698 * SummaryStats.loc['std',
                                                                         col]
        upper = SummaryStats.loc['mean', col] + 2.698 * SummaryStats.loc['std',
                                                                         col]
        if value < lower:
            message = message + col + " is low;"
        if value > upper:
            message = message + col + " is high;"
        inputdata.loc[idx, 'AnyOutliers'] = message

    if VERBOSE:
        if len(inputdata.loc[idx, 'AnyOutliers']) > 1:
            print("{} {}".format(inputdata.ix[idx, 0], message))

# write the results out to a file
if not DONOTMODIFY:
    inputdata.to_csv(inputfile, sep=',', index=False)

# if asked - write out the csv of SummaryStats
if not summaryout:
    SummaryStats.to_csv(summaryout, sep=',')
