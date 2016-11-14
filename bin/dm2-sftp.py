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

logger = logging.getLogger(__name__)


def main():
    arguments = docopt(__doc__)
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    dryrun = arguments['--dry-run']
    quiet = arguments['--quiet']
    study = arguments['<study>']

    # setup logging
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

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)

    logger.addHandler(ch)

    # setup the config object
    cfg = datman.config.config(study=study)
    mruser = cfg.get_key(['MRUSER'])
    mrfolders = cfg.get_key(['MRFOLDER'])
    mrserver = cfg.get_key(['FTPSERVER'])

    zips_path = cfg.get_path('zips')
    meta_path = cfg.get_path('meta')

    if not os.path.isdir(zips_path):
        logger.warning('Zips directory: {} not found; creating.'
                       .format(zips_path))
        if not dryrun:
            os.mkdir(zips_path)

    if isinstance(mrfolders, basestring):
        mrfolders = [mrfolders]

    # load the password
    pass_file = os.path.join(meta_path, 'mrftppass.txt')
    if not os.path.isfile(pass_file):
        logger.error('Password file: {} not found'. format(pass_file))
        raise IOError

    with open(pass_file, 'r') as pass_file:
        password = pass_file.read()
    password = password.strip()
    # actually do the copyinhg

    with pysftp.Connection(mrserver,
                           username=mruser,
                           password=password) as sftp:
        remote_dirs = sftp.listdir()

        for mr_folder in mrfolders:
            #  allow for wildcards in mrfolders definitions
            valid_dirs = [d for d in remote_dirs
                          if fnmatch.fnmatch(d, mr_folder)]
            for valid_dir in valid_dirs:
                logger.debug('Copying from:{}  to:{}'
                             .format(valid_dir, zips_path))
                with sftp.cd(valid_dir):
                    files = sftp.listdir()
                    for file_name in files:
                        target = os.path.join(zips_path, file_name)
                        if not os.path.isfile(target):
                            logger.info('Copying new remote file:{}'
                                        .format(file_name))
                            sftp.get(file_name, target, preserve_mtime=True)
                        elif os.path.getmtime(target) < sftp.stat(file_name).st_mtime:
                            # remote is newer than local
                            logger.info('Remote file:{} is newer than local file'
                                        .format(file_name))
                            sftp.get(file_name, target, preserve_mtime=True)
                        else:
                            logger.debug("File:{} already exists, skipping"
                                         .format(file_name))


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    main()
