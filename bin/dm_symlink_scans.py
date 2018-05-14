#!/usr/bin/env python
"""
Searches a session data/RESOURCES folder for *.nii or *.nii.gz files matching
the series numbers for scans in data/dcm. Creates a softlink in the data/nii
folder. Also, optionally creates json sidecars with -j flag.

Usage:
    dm_symlink_scans.py [options] <study> [(--site=<site_code> | --session=<id>...)]

Arguments:
    <study>             Name of the study to process
    --site=<site_code>  Name of the site within study to process
    --session=<id>      Names of specific sessions to process (must include
                        timepoint and session number)

Options:
    -j --json           Create json files
    -v --verbose        Verbose logging
    -d --debug          Debug logging
    -q --quiet          Less debuggering

"""

import os
import sys
from glob import glob
import errno
import logging

from docopt import docopt

import datman.config
import datman.utils
import datman.scanid

logger = logging.getLogger(__name__)


def create_symlink(src, target_name, dest):
    datman.utils.define_folder(dest)
    target_path = os.path.join(dest, target_name)
    if os.path.islink(target_path):
        logger.warn('{} already exists. Not linking.'.format(target_path))
    else:
        with datman.utils.cd(dest):
            rel_path = os.path.relpath(src, dest)
            try:
                os.symlink(rel_path, target_path)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise
                continue


def create_json_sidecar(scan_filename, session_nii_dir, session_dcm_dir):
    json_filename = os.path.splitext(scan_filename)[0] + '.json'
    if os.path.isfile(
        os.path.join(session_nii_dir, json_filename)
    ):
        logger.warn('JSON sidecar {} already exists.'
                    ' Skipping.'.format(json_filename))
    else:
        logger.info('Creating JSON sidecar {}'.format(json_filename))
        # dcm2niix creates json without nifti using single dicom in dcm directory
        datman.utils.run('dcm2niix -b o -s y -f {} -o {} {}'
                         .format(os.path.splitext(scan_filename)[0],
                                 session_nii_dir,
                                 os.path.join(session_dcm_dir,
                                              scan_filename)
                                 )
                         )


def main():
    arguments = docopt(__doc__)
    study = arguments['<study>']
    site = arguments['--site']
    session = arguments['--session']
    create_json = arguments['--json']
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    quiet = arguments['--quiet']

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

    # setup the config object
    cfg = datman.config.config(study=study)

    # get paths
    dir_nii = cfg.get_path('nii')
    dir_res = cfg.get_path('resources')
    dir_dcm = cfg.get_path('dcm')

    # get sessions depending on which command line argument was specified
    if site:
        sessions = [subject for subject in os.listdir(dir_res)
                    if datman.scanid.parse(subject).site == site]
    if session:
        sessions = session
    else:
        sessions = os.listdir(dir_res)

    logger.info('Processing {} sessions'.format(len(sessions)))
    for session in sessions:
        try:
            ident = datman.scanid.parse(session)
        except datman.scanid.ParseException:
            logger.error('Invalid session:{}'.format(session))

        # get all files of interest stored in the session directory within
        # RESOURCES
        session_res_dir = os.path.join(dir_res, session)
        extensions = ('**/*.nii.gz', '**/*.bvec', '**/*.bval')
        session_res_files = []
        for extension in extensions:
            session_res_files.extend(
                glob(os.path.join(session_res_dir, extension), recursive=True)
            )

        session_name = ident.get_full_subjectid_with_timepoint()
        session_nii_dir = os.path.join(dir_nii, session_name)
        session_dcm_dir = os.path.join(dir_dcm, session_name)

        if session_res_files:
            # check whether nifti directory exists, otherwise create it
            datman.utils.define_folder(dir_nii)

            # create dictionary with DICOM series numbers as keys and
            # filenames as values
            session_dcm_files = os.listdir(session_dcm_dir)
            dcm_dict = {int(datman.scanid.parse_filename(dcm)[2]):
                        dcm for dcm in session_dcm_files}
            for f in session_res_files:
                # need better way to get series number from nifti
                series_num = int(os.path.basename(f).split("_")[1][1:])
                # try to get new nifti filename by matching series number
                # in dictionary
                try:
                    scan_filename = os.path.splitext(dcm_dict[series_num])[0]
                except:
                    logger.error('Corresponding dcm file not found for {}'
                                 .format(f))
                    continue
                ext = os.path.splitext(f)[1]
                nii_name = scan_filename + ext
                create_symlink(f, nii_name, session_nii_dir)
                if create_json and f.endswith('.nii.gz'):
                    create_json_sidecar(dcm_dict[series_num],
                                        session_nii_dir,
                                        session_dcm_dir)


if __name__ == '__main__':
    main()
