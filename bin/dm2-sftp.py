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
from docopt import docopt
import datman.config
import pysftp
import logging
import sys
import os
import fnmatch
import paramiko

logger = logging.getLogger(os.path.basename(__file__))


def main():
    arguments = docopt(__doc__)
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    dryrun = arguments['--dry-run']
    quiet = arguments['--quiet']
    study = arguments['<study>']

    # setup logging
    ch = logging.StreamHandler(sys.stdout)
    log_level = logging.WARN

    if quiet:
        log_level = logging.ERROR
    if verbose:
        log_level = logging.INFO
    if debug:
        log_level = logging.DEBUG
    logger.setLevel(log_level)
    ch.setLevel(log_level)
    logging.getLogger("paramiko").setLevel(log_level)

    formatter = logging.Formatter('%(asctime)s - %(name)s - {study} - '\
            ' %(levelname)s - %(message)s'.format(study=study))
    ch.setFormatter(formatter)

    logger.addHandler(ch)

    # setup the config object
    cfg = datman.config.config(study=study)

    # get folder information from the config object
    mrusers = cfg.get_key(['MRUSER'])
    mrfolders = cfg.get_key(['MRFOLDER'])
    mrserver = cfg.get_key(['FTPSERVER'])

    zips_path = cfg.get_path('zips')
    meta_path = cfg.get_path('meta')

    # Check the local project zips dir exists, create if not
    if not os.path.isdir(zips_path):
        logger.warning('Zips directory: {} not found; creating.'
                       .format(zips_path))
        if not dryrun:
            os.mkdir(zips_path)

    # MRfolders entry in config file should be a list, but could be a string
    if isinstance(mrfolders, basestring):
        mrfolders = [mrfolders]

    # MRUSER entry in config file should be a list, but could be a string
    if isinstance(mrusers, basestring):
        mrusers = [mrusers]

    # load the password
    pass_file = os.path.join(meta_path, 'mrftppass.txt')
    if not os.path.isfile(pass_file):
        logger.error('Password file: {} not found'. format(pass_file))
        raise IOError

    passwords = []
    with open(pass_file, 'r') as pass_file:
        for password in pass_file:
            password = password.strip()
            if password:
                passwords.append(password)

    # actually do the copying
    assert len(passwords) == len(mrusers), \
        'Each mruser in config should have and entry in the password file'

    for iloc in range(len(mrusers)):
        mruser = mrusers[iloc]
        password = passwords[iloc]
        with pysftp.Connection(mrserver,
                               username=mruser,
                               password=password) as sftp:

            valid_dirs = get_valid_remote_dirs(sftp, mrfolders)
            if len(valid_dirs) < 1:
                logger.error('Source folders:{} not found'.format(mrfolders))

            for valid_dir in valid_dirs:
                #  process each folder in turn
                logger.debug('Copying from:{}  to:{}'
                             .format(valid_dir, zips_path))
                process_dir(sftp, valid_dir, zips_path)


def get_valid_remote_dirs(connection, mrfolders):
    """Process a list of remote_dirs, return those that match entries
    in mrfolders
    Allows for wildcard entries in the mrfolders definitions in
    config files.
    """
    remote_dirs = connection.listdir()
    valid_dirs = []
    for mr_folder in mrfolders:
        [valid_dirs.append(d) for d in remote_dirs
         if fnmatch.fnmatch(d, mr_folder)]
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
            target = os.path.join(zips_path, file_name)
            if check_exists_isnewer(connection, file_name, target):
                logger.info('Copying new remote file:{}'
                            .format(file_name))
                connection.get(file_name, target, preserve_mtime=True)
            else:
                logger.debug("File:{} already exists, skipping"
                             .format(file_name))

def check_exists_isnewer(sftp, filename, target):
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
    logging.basicConfig(level=logging.DEBUG)
    main()
