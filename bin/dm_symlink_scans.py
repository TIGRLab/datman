#!/usr/bin/env python
"""
Searches a session data/RESOURCES folder for *.nii.gz files matching the
series numbers for scans in data/dcm. Creates a softlink in the data/nii
folder. Also, optionally creates json sidecars with -j flag.

Usage:
    dm_symlink_scans.py [options] <study> (--site=<site_code> | --session=<id>...)

Arguments:
    <study>             Name of the study to process
    --site=<site_code>  Name of the site within study to process
    --session=<id>      Names of specific sessions to process (must include
                        timepoint and session number)

Options:
    -j --json           Create json files
    -q --quiet          Less logging
    -v --verbose        Verbose logging
    -d --debug          Debug logging

"""  # noqa: E501

import os
import sys
from glob import glob
import fnmatch
import logging

from docopt import docopt

import datman.config
import datman.utils
import datman.scanid

# set up logging
logger = logging.getLogger(__name__)

formatter = logging.Formatter('%(asctime)s - %(name)s - '
                              '%(levelname)s - %(message)s')

log_handler = logging.StreamHandler(sys.stdout)
log_handler.setFormatter(formatter)

logger.addHandler(log_handler)


def find_files(directory):
    for root, dirs, files in os.walk(directory):
        for extension in ['*.nii.gz', '*.bvec', '*.bval']:
            for basename in files:
                if fnmatch.fnmatch(basename, extension):
                    filename = os.path.join(root, basename)
                    yield filename


def create_symlink(src, target_name, dest):
    datman.utils.define_folder(dest)
    target_path = os.path.join(dest, target_name)
    if os.path.isfile(target_path):
        logger.warn('{} already exists. Not linking.'.format(target_path))
        return
    with datman.utils.cd(dest):
        rel_path = os.path.relpath(src, dest)
        logger.info('Linking {} -> {}'.format(rel_path, target_path))
        try:
            os.symlink(rel_path, target_path)
        except OSError:
            logger.error('Unable to link to {}'.format(rel_path))


def force_json_name(json_filename, sub_dir):
    '''
    dcm2niix adds a suffix if a nifti file already exists even though you
    just want the .json sidecar. Force name to match what is expected
    '''

    json_base = json_filename.split('.')[0]
    candidate = [f for f in os.listdir(sub_dir)
                 if (json_base in f) and ('.json' in f)][0]

    if candidate != json_base:
        logger.warning('dcm2niix added suffix!\nShould be {}\n'
                       'Found {}'.format(json_filename, candidate))
        src = os.path.join(sub_dir, candidate)
        dst = os.path.join(sub_dir, json_filename)
        os.rename(src, dst)


def create_json_sidecar(scan_filename, session_nii_dir, session_dcm_dir):
    json_filename = os.path.splitext(scan_filename)[0] + '.json'
    if os.path.isfile(os.path.join(session_nii_dir, json_filename)):
        logger.warn('JSON sidecar {} already exists. '
                    'Not creating.'.format(json_filename))
        return
    logger.info('Creating JSON sidecar {}'.format(json_filename))
    try:
        # dcm2niix creates json using single dicom in dcm directory
        datman.utils.run('dcm2niix -b o -s y -f {} -o {} {}'
                         .format(os.path.splitext(scan_filename)[0],
                                 session_nii_dir,
                                 os.path.join(session_dcm_dir, scan_filename)))
        force_json_name(json_filename, session_nii_dir)
    except Exception:
        logger.error('Unable to create JSON sidecar {}'.format(json_filename))


def get_series(file_name):
    # need better way to get series number from nifti
    return int(os.path.basename(file_name).split("_")[1][1:])


def is_blacklisted(resource_file, session):
    blacklist = datman.utils.read_blacklist(subject=session)
    if not blacklist:
        return False
    series = get_series(resource_file)
    for entry in blacklist:
        bl_series = int(datman.scanid.parse_filename(entry)[2])
        if series == bl_series:
            return True
    return False


def main():
    arguments = docopt(__doc__)
    study = arguments['<study>']
    site = arguments['--site']
    session = arguments['--session']
    create_json = arguments['--json']
    quiet = arguments['--quiet']
    verbose = arguments['--verbose']
    debug = arguments['--debug']

    # setup log levels
    log_level = logging.WARN

    if quiet:
        log_level = logging.ERROR
    if verbose:
        log_level = logging.INFO
    if debug:
        log_level = logging.DEBUG

    logger.setLevel(log_level)
    log_handler.setLevel(log_level)

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
    elif session:
        sessions = session
    else:
        sessions = os.listdir(dir_res)

    logger.info('Processing {} sessions'.format(len(sessions)))
    for session in sessions:
        try:
            ident = datman.scanid.parse(session)
        except datman.scanid.ParseException:
            logger.error('Invalid session: {}'.format(session))
            continue

        # get all files of interest stored in the session directory within
        # RESOURCES
        session_res_dir = os.path.join(dir_res, session)
        # extensions = ('**/*.nii.gz', '**/*.bvec', '**/*.bval')
        session_res_files = []
        # temporarily commment out since glob in python 2 can't recurse
        # for extension in extensions:
        #     session_res_files.extend(
        #         glob(os.path.join(session_res_dir, extension),
        #              recursive=True)
        #     )

        for filename in find_files(session_res_dir):
            session_res_files.append(filename)

        session_name = ident.get_full_subjectid_with_timepoint()
        session_nii_dir = os.path.join(dir_nii, session_name)
        session_dcm_dir = os.path.join(dir_dcm, session_name)

        if session_res_files:
            # check whether nifti directory exists, otherwise create it
            datman.utils.define_folder(session_nii_dir)

            # create dictionary with DICOM series numbers as keys and
            # filenames as values
            session_dcm_files = os.listdir(session_dcm_dir)
            dcm_dict = {int(datman.scanid.parse_filename(dcm)[2]):
                        dcm for dcm in session_dcm_files}
            for f in session_res_files:
                series_num = get_series(f)
                # try to get new nifti filename by matching series number
                # in dictionary
                try:
                    scan_filename = os.path.splitext(dcm_dict[series_num])[0]
                except (IndexError, KeyError):
                    if is_blacklisted(f, session_name):
                        logger.info('Ignored blacklisted series {}'.format(f))
                        continue
                    logger.error('Corresponding dcm file not found for {}'
                                 .format(f))
                    continue
                ext = datman.utils.get_extension(f)
                nii_name = scan_filename + ext

                if create_json and nii_name.endswith('.nii.gz'):
                    create_json_sidecar(dcm_dict[series_num],
                                        session_nii_dir,
                                        session_dcm_dir)

                create_symlink(f, nii_name, session_nii_dir)


if __name__ == '__main__':
    main()
