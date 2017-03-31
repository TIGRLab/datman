#!/usr/bin/env python
"""
Purge data and folders for a specified session from a study directory structure.
In normal use a backup folder is created containing the purged data which can
easily be removed with rm -r <session>.


Usage:
purge_session.py [options] <study> <session>

Arguments:
    <study>             Study/Project name
    <session>           Session ID

Options:
    --backupdir=DIR     Directory to create the backup [default: ./]
    --purgedb           Also purge records from the dashboard database

Details:
    Uses rsync with --remove-source-files to copy and delete files and
    directory strucure matching <session>. Then finds matching empty
    directories and deletes them.
"""

import logging
from docopt import docopt
import datman.config
import datman.dashboard
import subprocess
import os


logger = logging.getLogger(__file__)
CFG = datman.config.config()


def main():
    arguments = docopt(__doc__)
    study = arguments['<study>']
    session = arguments['<session>']
    backupdir = arguments['--backupdir']
    purgedb = arguments['--purgedb']

    CFG.set_study(study)
    base_dir = CFG.get_study_base()
    logger.info('Searching folders:{}'.format(base_dir))
    # Create the backup folder
    outdir = os.path.realpath(os.path.join(backupdir, session))

    try:
        os.makedirs(outdir)
    except OSError:
        logger.error('Failed making backup directory:{}'.format(outdir))
        return

    if not purge_filesystem(session, base_dir, outdir):
        # somethings gone wrong. End processing here.
        return

    if purgedb:
        try:
            db = datman.dashboard.dashboard(study)
            db.delete_session(session)
        except:
            return

def purge_filesystem(session, base_dir, out_dir):
    """session - session name to remove
       base_dir - root of the filesystem to search from
       out_dir  - directory to create the backup
       """
    cmd_rsync = ['rsync',
                 '-rmz',
                 '--include={}*/**'.format(session),
                 '--include=*/',
                 '--exclude=*',
                 base_dir,
                 out_dir]

    if not run_cmd(cmd_rsync):
        logger.error('Backup of session:{} failed'.format(session))
        return

    #os.chdir(cur_dir)

    cmd_find = ['find',
                base_dir,
                '-depth',
                '-type',
                'd',
                '-empty',
                '-name',
                '{}*'.format(session),
                '-delete']

    if not run_cmd(cmd_find):
        logger.error('Cleanup of session:{} failed'.format(session))
        return

    return True


def run_cmd(cmd):
    """Runs a command, logs stuff if fails,
    returns True on success"""
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
        logger.info('Cmd:{}'.format(e.cmd))
        logger.info('Status:{}'.format(e.returncode))
        if(e.output):
            logger.info('Output:{}'.format(e.output))
        return
    return True

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    main()
