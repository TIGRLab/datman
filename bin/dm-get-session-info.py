#!/usr/bin/env python
"""Read all scans in data/nii extract the subject Id and scan date info

Usage:
    dm-get-session-info.py [options] <study>
    dm-get-session-info.py [options] <study> <csv_file>

Arguments:
    <study>   Path to the project config file
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

from docopt import docopt
import datman.config
import datman.utils
import datman.scanid

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARN)

def process_scan(dirname, headers):

    is_phantom = False
    is_repeat = False
    scan_date = None
    subject_id = None

    is_phantom = datman.scanid.is_phantom(dirname)

    try:
        i = datman.scanid.parse(dirname)
    except datman.scanid.ParseException:
        logger.warning('Failed to parse:{}, adding session'.format(dirname))
        try:
            i = datman.scanid.parse(dirname + '_01')
        except datman.scanid.ParseException:
            logger.error('Failed to parse:{}'.format(dirname))
            return

    if i.subject.startswith('R'):
        is_repeat = True
        subject_id = i.subject[1:]
    else:
        subject_id = i.subject

    scan_date = datetime.strptime(headers.SeriesDate, '%Y%m%d')

    return(subject_id, i.session, i.site, scan_date, is_phantom, is_repeat)


def main():
    arguments = docopt(__doc__)
    study = arguments['<study>']
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

    cfg = datman.config.config(study=study)
    #
    # ## Read in the configuration yaml file
    # if not os.path.isfile(config_yaml):
    #     raise ValueError("configuration file {} not found. Try again."
    #                      .format(config_yaml))
    #
    # ## load the yml file
    # with open(config_yaml, 'r') as stream:
    #     CONFIG = yaml.load(stream)
    #
    # ## check that the required keys are there
    # ExpectedKeys = ['paths']
    # diffs = set(ExpectedKeys) - set(CONFIG.keys())
    # if len(diffs) > 0:
    #     raise ImportError("configuration file missing {}".format(diffs))

    #dcm_dir = CONFIG['paths']['dcm']
    dcm_dir = cfg.get_path('dcm')

    logger.debug('Getting scan list for {}'.format(dcm_dir))
    scans = datman.utils.get_folder_headers(dcm_dir)
    logger.info('Found {} scans'.format(len(scans)))

    headers = ["FOLDER", "SUBJECT", "SESSION", "SCANDATE", "SITE", "SUBJECT/REPEAT/PHANTOM"]

    results = []
    for key, val in scans.iteritems():
        res = process_scan(key, val)
        if res:
            result = [key, res[0], res[1], datetime.strftime(res[3], '%Y-%m-%d'), res[2]]
            if res[4]:
                result.append('PHANTOM')
            elif res[5]:
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
