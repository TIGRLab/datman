#!/usr/bin/env python
"""Get new files using sftp from a project server

Usage:
    dm-sftp.py [options] <study>

Arguments:
    <study>:    Short name of the study to process

Options:
    -h --help                   Show this screen.
    -q --quiet                  Suppress output.
    -v --verbose                Show more output.
    -d --debug                  Show lots of output.
    --dry-run

"""
import logging
import sys
import os
import shutil

import pysftp
import fnmatch
import paramiko

from docopt import docopt
import datman.config
from datman.utils import make_temp_directory

logging.basicConfig(level=logging.WARN,
        format="[%(asctime)s %(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

def main():
    arguments = docopt(__doc__)
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    dryrun = arguments['--dry-run']
    quiet = arguments['--quiet']
    study = arguments['<study>']

    # setup logging
    log_level = logging.WARN

    if quiet:
        log_level = logging.ERROR
    if verbose:
        log_level = logging.INFO
    if debug:
        log_level = logging.DEBUG

    logging.getLogger().setLevel(log_level)

    # setup the config object
    cfg = datman.config.config(study=study)

    zips_path = cfg.get_path('zips')
    meta_path = cfg.get_path('meta')
    # Check the local project zips dir exists, create if not
    if not os.path.isdir(zips_path):
        logger.warning('Zips directory: {} not found; creating.'
                       .format(zips_path))
        if not dryrun:
            os.mkdir(zips_path)

    server_config = get_server_config(cfg)

    for mrserver in server_config:
        mrusers, mrfolders, pass_file_name, port = server_config[mrserver]

        # MRfolders entry in config file should be a list, but could be a string
        if isinstance(mrfolders, basestring):
            mrfolders = [mrfolders]

        # MRUSER entry in config file should be a list, but could be a string
        if isinstance(mrusers, basestring):
            mrusers = [mrusers]

        pass_file = os.path.join(meta_path, pass_file_name)
        passwords = read_password(pass_file)

        # actually do the copying
        assert len(passwords) == len(mrusers), \
            'Each mruser in config should have and entry in the password file'

        for iloc in range(len(mrusers)):
            mruser = mrusers[iloc]
            password = passwords[iloc]
            with pysftp.Connection(mrserver,
                                   username=mruser,
                                   password=password,
                                   port=port) as sftp:

                valid_dirs = get_valid_remote_dirs(sftp, mrfolders)
                if len(valid_dirs) < 1:
                    logger.error('Source folders:{} not found'.format(mrfolders))

                for valid_dir in valid_dirs:
                    #  process each folder in turn
                    logger.debug('Copying from:{}  to:{}'
                                 .format(valid_dir, zips_path))
                    process_dir(sftp, valid_dir, zips_path)


def get_server_config(cfg):
    server_config = {}

    default_mrserver = cfg.get_key('FTPSERVER')
    try:
    	server_config[default_mrserver] = read_config(cfg)
    except datman.config.UndefinedSetting as e:
        # No default config :(
        logger.debug(e.message)

    # Sites may override the study defaults. If they dont, the defaults will
    # be returned and should NOT be re-added to the config
    for site in cfg.get_sites():
        site_server = cfg.get_key('FTPSERVER', site=site)

        if site_server in server_config:
            continue

        try:
            server_config[site_server] = read_config(cfg, site=site)
        except datman.config.UndefinedSetting as e:
            logger.debug(e.message)
    return server_config


def read_config(cfg, site=None):
    logger.debug("Getting MR sftp server config for site: {}".format(
            site if site else "default"))

    mrusers = cfg.get_key('MRUSER', site=site)
    mrfolders = cfg.get_key('MRFOLDER', site=site)

    try:
        pass_file = cfg.get_key('MRFTPPASS', site=site)
    except datman.config.UndefinedSetting:
        pass_file = 'mrftppass.txt'
    try:
        server_port = cfg.get_key('FTPPORT', site=site)
    except datman.config.UndefinedSetting:
        server_port = 22

    return (mrusers, mrfolders, pass_file, server_port)


def read_password(pass_file):
    if not os.path.isfile(pass_file):
        logger.error('Password file: {} not found'. format(pass_file))
        raise IOError

    passwords = []
    with open(pass_file, 'r') as pass_file:
        for password in pass_file:
            password = password.strip()
            if password:
                passwords.append(password)

    return passwords


def get_valid_remote_dirs(connection, mrfolders):
    """Process a list of remote_dirs, return those that match entries
    in mrfolders
    Allows for wildcard entries in the mrfolders definitions in
    config files.
    """
    remote_dirs = connection.listdir()
    valid_dirs = []
    # ToNI stores the data two folders deep, so the path doesnt work the old
    # algo (code in else statement). But some studies have Regexs in their
    # mrfolders which doesnt work with the new algo (code in if statement)
    # So this is an ugly compromise :( (If only pysftp had a sensible 'walk' function...)
    for mrfolder in mrfolders:
        if connection.exists(mrfolder):
            valid_dirs.append(mrfolder)
        else:
            [valid_dirs.append(d) for d in remote_dirs
                if fnmatch.fnmatch(d, mrfolder)]
    return valid_dirs


def process_dir(connection, directory, zips_path):
    """Process a directory on the ftp server,
    copy new files to zips_path
    """
    with connection.cd(directory):
        try:
            files = connection.listdir()
        except IOError:
            # can get this if user doesn't have permission to enter the folder
            logger.debug('Cant access remote folder:{}, skipping.'
                         .format(directory))
            return
        for file_name in files:
            if connection.isfile(file_name):
                get_file(connection, file_name, zips_path)
            else:
                get_folder(connection, file_name, zips_path)

def get_folder(connection, folder_name, dst_path):
    expected_file = os.path.join(dst_path, folder_name + ".zip")
    if not download_needed(connection, folder_name, expected_file):
        logger.debug("File: {} already exists, skipping".format(folder_name))
        return

    with make_temp_directory() as temp_dir:
        # Note 'get_r' is needed instead of 'get'
        connection.get_r(folder_name, temp_dir, preserve_mtime=True)
        source = os.path.join(temp_dir, folder_name)
        dest = os.path.join(dst_path, folder_name)
        new_zip = shutil.make_archive(dest, 'zip', source)
        logger.info("Copied remote file {} to: {}".format(folder_name, new_zip))

def get_file(connection, file_name, zips_path):
    target = os.path.join(zips_path, file_name)
    if download_needed(connection, file_name, target):
        logger.info('Copying new remote file: {}'.format(file_name))
        connection.get(file_name, target, preserve_mtime=True)
    else:
        logger.debug("File: {} already exists, skipping".format(file_name))

def download_needed(sftp, filename, target):
    """Check if a local copy of the file exists,
    If no local copy exists return True
    If local copy exists and is older than remote return True
    otherwise return false"""
    if not os.path.isfile(target):
        return True

    # check the file modification times
    local_mtime = os.path.getmtime(target)
    remote_mtime = sftp.stat(filename).st_mtime
    if local_mtime < remote_mtime:
        return True

    return False

if __name__ == '__main__':
    main()
