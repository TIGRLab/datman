#!/usr/bin/env python
"""
Symlink SPRL scans from Resources folder to nii folder

Usage:
    dm2-link-sprl.py [options] <study>
    dm2-link-sprl.py [options] <study> <session>

Arguments:
    <study>              Name of the study to process
    <session>            Name of a single session to process. Must include
                         timepoint and session number or the resources folder
                         will not be found.

Options:
    -v --verbose         Verbose logging
    -d --debug           Debug logging
    -q --quiet           Less debuggering
    --dry-run            Dry run

Details:
Searches a session data/RESOURCES folder for *.nii files matching the Regex
defined in project settings. Creates a softlink in the data/nii folder.
Multiple SPRL tags can be defined with different regexs so long as the
key contains SPRL
"""

from datman.docopt import docopt
import sys
import os
import re
import datman.config
import datman.utils
import datman.dashboard
import logging
import errno
from datman.exceptions import DashboardException

logger = logging.getLogger(__name__)


def main():
    arguments = docopt(__doc__)
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    quiet = arguments['--quiet']
    study = arguments['<study>']
    session = arguments['<session>']

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

    dir_nii = cfg.get_path('nii')
    dir_res = cfg.get_path('resources')

    # setup the dashboard object
    db = datman.dashboard.dashboard(study=study)

    if session:
        # single session defined on command line
        sessions = [session]
    else:
        # session not defined find all sessions in a project
        sessions = os.listdir(dir_res)

    logger.info('Processing {} sessions'.format(len(sessions)))
    for session in sessions:
        try:
            logger.info('Processing session {}'.format(session))
            process_session(cfg, db, dir_nii, dir_res, session)
        except:
            logger.error('Failed processing session:{}'.format(session))


def process_session(cfg, db, dir_nii, dir_res, session):
    # check everything is setup correctly
    try:
        ident = datman.scanid.parse(session)
    except datman.scanid.ParseException:
        logger.error('Invalid session:{}'.format(session))
        return

    subject_res = os.path.join(dir_res, str(ident))
    logger.info('Subject {} resource folder will : {}'.format(str(ident), subject_res))
    dir_nii = os.path.join(dir_nii,
                           ident.get_full_subjectid_with_timepoint())
    logger.info('Subject {} nii folder will be: {}'.format(str(ident), dir_nii))

    if not os.path.isdir(subject_res):
        logger.info("{} does not exist. Will be adding session number to try and find it.".format(subject_res))
        # Resources folders now require timepoint and session number. If user only
        # gives the first, check with a default session number before giving up.
        if not ident.session:
            ident.session = '01'
            session_res = os.path.join(dir_res, str(ident))
        if os.path.isdir(session_res):
            subject_res = session_res
        else:
            logger.error('Could not find session {} resources at expected '
                    'location {}'.format(session, subject_res))
            return

    if not os.path.isdir(dir_nii):
        logger.warning('nii dir doesnt exist for session:{}, creating.'
                       .format(session))
        try:
            os.makedirs(dir_nii)
        except OSError:
            logger.error('Failed creating nii dir for session:{}'
                         .format(session))
            return
    # end of Checks

    # get the regex expressions from the config file
    tags = cfg.get_tags(site=ident.site)
    export_info = tags.series_map
    # Doing it this way will enable matching multiple types of SPRL with
    # different regexs
    sprls = [(i, v) for i, v in export_info.iteritems() if 'SPRL' in v]

    # find matching files in the resources folder
    sprl_files = []
    for sprl in sprls:
        p = re.compile(sprl[0], re.IGNORECASE)
        logger.info("Search for sprl nii file")
        for root, dirs, files in os.walk(subject_res):
            # exclude the backup resources directory
            if 'BACKUPS' in root:
                continue

            for f in files:
                # limit only to nifti files
                if not f.endswith('nii'):
                    continue
                src_file = os.path.join(root, f)
                logger.info("sprl file path: {}".format(src_file))
                if p.search(src_file):
                    # get a mangled name for the link target
                    target_name = _get_link_name(src_file,
                                                 subject_res,
                                                 ident,
                                                 sprl[1])
                    sprl_files.append((src_file, target_name))

    for sprl_file in sprl_files:
        logger.info("Currently working on {}".format(sprl_file))
        _create_symlink(sprl_file[0], sprl_file[1], dir_nii)
        _add_sprl_to_dashboard(db, sprl_file[1])


def _add_sprl_to_dashboard(db, filename):
    try:
        logger.info("Adding {} to dashboard".format(filename))
        db.get_add_scan(filename, create=True)
    except DashboardException as e:
        logger.error('Failed adding scan:{} to dashboard.'
                     .format(filename))
        logger.debug('Failed adding scan:{} to dashboard with error:{}'
                     .format(filename, str(e)))


def _create_symlink(src, target_name, dir_nii):
    """Check to see if this file has been blacklisted,
    if not create the symlink if it doesnt exist"""
    if datman.utils.check_blacklist(target_name):
        return

    target_path = os.path.join(dir_nii, target_name)
    rel_src = datman.utils.get_relative_source(src, target_path)

    if not os.path.islink(target_path):
        logger.info('Linking:{} to {}'.format(rel_src, target_name))
        try:
            os.symlink(rel_src, target_path)
        except OSError as e:
            if e.errno == errno.EEXIST:
                logger.warning('Failed creating symlink:{} --> {} with reason:{}'
                             .format(rel_src, target_path, e.strerror))
            else:
                logger.error('Failed creating symlink:{} --> {} with reason:{}'
                             .format(rel_src, target_path, e.strerror))


def _get_link_name(path, basepath, ident, tag):
    """ Take the path to the file, and mangle it so that we have a unique
    "description" to use in the final name.

    For instance, the path:
        data/RESOURCES/DTI_CMH_H001_01_01/A/B/C/sprl.nii

        will get mangled like so:

        1. Strip off 'data/RESOURCES/DTI_CMH_H001_01_01/'
        2. Convert all / to dashes -
        3. Convert all _ to dashes -

        the result is the string:

            A-B-C-sprl.nii

    Example:
    >>> _get_link_name(data/RESOURCES/DTI_CMH_H001_01_01/A/B/C/sprl.nii,
                       'data/RESOURCES/DTI_CMH_H001_01_01/',
                       datman.scanid.parse('DTI_CMH_H001_01_01'),
                       'SPRL')
    DTI_CMH_H001_01_01_SPRL_A-B-C-sprl.nii

    """
    path = os.path.relpath(path, basepath)
    path = path.replace('/', '-')
    path = path.replace('_', '-')
    # try to see if we can extract the series number
    p = re.compile('Se(\d+)-')
    m = p.findall(path)
    series = '00'
    if m:
        try:
            series = '{0:02d}'.format(int(m[0]))
        except ValueError:
            pass

    filename = '{exam}_{tag}_{series}_{tail}'.format(exam=str(ident),
                                                     tag=tag,
                                                     series=series,
                                                     tail=path)
    return(filename)


if __name__ == '__main__':
    main()
