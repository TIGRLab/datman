#!/usr/bin/env python
"""Read all scans in data/nii extract the subject Id and scan date info

Usage:
    dm-get-session-info.py [options] <config_file>
    dm-get-session-info.py [options] <config_file> <csv_file>

Arguments:
    <config_file>   Path to the project config file
    <csv_file>      Path to the csv file

Options:
    -h --help       Show this screen
    -q --quiet      Suppress output
    -v --verbose    Show more output
    -d --debug      Show lots of output
"""

import os
import logging
import yaml
import csv
from datetime import datetime
import datman as dm
from docopt import docopt

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARN)

def process_scan(dirname, headers):

    is_phantom = False
    is_repeat = False
    scan_date = None
    subject_id = None

    is_phantom = dm.scanid.is_phantom(dirname)

    try:
        i = dm.scanid.parse(dirname)
    except dm.scanid.ParseException:
        logger.warning('Failed to parse:{}, adding session'.format(dirname))
        try:
            i = dm.scanid.parse(dirname + '_01')
        except dm.scanid.ParseException:
            logger.error('Failed to parse:{}'.format(dirname))
            return

    if i.subject.startswith('R'):
        is_repeat = True
        subject_id = i.subject[1:]
    else:
        subject_id = i.subject

    scan_date = datetime.strptime(headers.SeriesDate, '%Y%m%d')

    return(subject_id, i.site, scan_date, is_phantom, is_repeat)


def main():
    arguments = docopt(__doc__)
    config_yaml = arguments['<config_file>']
    output_csv = arguments['<csv_file>']
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    quiet = arguments['--quiet']

    if quiet:
        logger.setLevel(logging.ERROR)

    if verbose:
        logger.setLevel(logging.INFO)

    if debug:
        logger.setLevel(logging.DEBUG)

    logging.info('Starting')

    # Check the yaml file can be read correctly
    logger.debug('Reading yaml file.')

    ## Read in the configuration yaml file
    if not os.path.isfile(config_yaml):
        raise ValueError("configuration file {} not found. Try again."
                         .format(config_yaml))

    ## load the yml file
    with open(config_yaml, 'r') as stream:
        CONFIG = yaml.load(stream)

    ## check that the required keys are there
    ExpectedKeys = ['paths']
    diffs = set(ExpectedKeys) - set(CONFIG.keys())
    if len(diffs) > 0:
        raise ImportError("configuration file missing {}".format(diffs))

    dcm_dir = CONFIG['paths']['dcm']

    logger.debug('Getting scan list for {}'.format(dcm_dir))
    scans = dm.utils.get_folder_headers(dcm_dir)
    logger.info('Found {} scans'.format(len(scans)))

    headers = ["SUBJECT", "SCANDATE", "SITE", "SUBJECT/REPEAT/PHANTOM"]

    results = []
    for key, val in scans.iteritems():
        res = process_scan(key, val)
        if res:
            result = [res[0], datetime.strftime(res[2], '%Y-%m-%d'), res[1]]
            if res[3]:
                result.append('PHANTOM')
            elif res[4]:
                result.append('REPEAT')
            else:
                result.append("SUBJECT")
            results.append(result)

    if output_csv:
        with open(output_csv, 'wb') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(headers)
            for row in results:
                csv_writer.writerow(row)
    else:
        print(','.join(headers))
        for row in results:
            print(','.join(row))

if __name__ == '__main__':
    main()
