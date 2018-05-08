#!/usr/bin/env python
"""
Searches a session data/RESOURCES folder for *.nii.gz files matching the
series numbers for scans in data/dcm. Creates a softlink in the data/nii
folder.

To do:
    json files need to be created
    integrate with dm_link_sprl.py

Usage:
    opt_cu1_link.py [options] <study> <site>

Arguments:
    <study>              Name of the study to process
    <site>               Name of site to process

Options:
    -v --verbose         Verbose logging
    -d --debug           Debug logging
    -q --quiet           Less debuggering
    --dry-run            Dry run

"""

import os
import sys
from glob import glob
import errno
import logging

from docopt import docopt

import datman.config
import datman.scanid

logger = logging.getLogger(__name__)


def create_dir(dir_path):
    if not os.path.isdir(dir_path):
        logger.info('Creating: {}'.format(dir_path))
        try:
            os.mkdir(dir_path)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
                logger.error('Failed creating: {}'.format(dir_path))
            pass


def create_symlink(src, target_name, dest):
    create_dir(dest)
    target_path = os.path.join(dest, target_name)
    if not os.path.islink(target_path):
        logger.info('Linking {} --> {}'.format(src, target_path))
        try:
            orig_dir = os.getcwd()
            os.chdir(dest)
            rel_path = os.path.relpath(src, dest)
            os.symlink(rel_path, target_path)
            os.chdir(orig_dir)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
                logger.error('Failed creating symlink {} --> {}'.format(src, target_path))
            pass


def main():
    arguments = docopt(__doc__)
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    quiet = arguments['--quiet']
    study = arguments['<study>']
    site = arguments['<site>']

    # setup logging
    logging.basicConfig()
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.WARN)
    logger.setLevel(logging.WARN)
    if quiet:
        logger.setLevel(logging.ERROR)
        ch.setLevel(logging.ERROR)
    if verbose:
        logger.setLevel(logging.INFO)
        ch.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)
        ch.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s - %(name)s - '
                                  '%(levelname)s - %(message)s')
    ch.setFormatter(formatter)

    logger.addHandler(ch)

    cfg = datman.config.config(study=study)

    # get paths
    dir_nii = cfg.get_path('nii')
    dir_res = cfg.get_path('resources')
    dir_dcm = cfg.get_path('dcm')

    # filter subjects from CU1
    subjects = [subject for subject in os.listdir(dir_res)
                   if datman.scanid.parse(subject).site == site]
    logger.info('{} subjects in the RESOURCES folder are: {}'.format(site, str(cu_subjects)))

    for subject in subjects:
        ident = datman.scanid.parse(subject)
        session_name = ident.get_full_subjectid_with_timepoint()
        sub_res_dirs = list(set([os.path.dirname(i) for i in glob(
            os.path.join(dir_res, subject, "**/*.nii.gz"), recursive=True)]))
        sub_dcm_dir = os.path.join(dir_dcm, session_name)
        sub_nii_dir = os.path.join(dir_nii, session_name)
        if sub_res_dirs:
            for sub_res_dir in sub_res_dirs:
                sub_res_files = list(filter(lambda x: x.lower().endswith(
                    ('.nii.gz', '.bvec', '.bval')), os.listdir(sub_res_dir)))
                sub_dcm_files = os.listdir(sub_dcm_dir)
                dcm_dict = {int(datman.scanid.parse_filename(dcm)[2]):
                            os.path.splitext(dcm)[0] for dcm in sub_dcm_files}
                for f in sub_res_files:
                    series_num = int(f.split("_")[1][1:])
                    sub_filename = dcm_dict[series_num]
                    ext = f[f.find("."):]
                    nii_name = sub_filename + ext
                    src = os.path.join(sub_res_dir, f)
                    create_symlink(src, nii_name, sub_nii_dir)


if __name__ == '__main__':
    main()
