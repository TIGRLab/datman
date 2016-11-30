#!/usr/bin/env python
"""
Uploads a scan archive to XNAT

Usage:
    xnat-upload.py [options] <study>
    xnat-upload.py [options] <study> <archive>

Arguments:
    <study>             Study/Project name
    <archive>             Properly named zip file

Options:
    --server URL          XNAT server to connect to,
                            overrides the server defined
                            in the site config file.

    -c --credfile FILE    File containing XNAT username and password. The
                          username should be on the first line, and password
                          on the next. Overrides the credfile in the project
                          metadata

    -u --username USER    XNAT username. If specified then the credentials
                          file is ignored and you are prompted for password.


    -v --verbose          Be chatty
    -d --debug            Be very chatty
    -q --quiet            Be quiet
"""

import logging
import sys
from docopt import docopt
import datman.config
import datman.utils
import datman.scanid
import datman.xnat
import datman.exceptions
import os
import getpass
import requests
import time
import zipfile
import io
import dicom

logger = logging.getLogger(__file__)

username = None
password = None
server = None
XNAT = None

def main():
    global username
    global server
    global password
    global XNAT

    arguments = docopt(__doc__)
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    quiet = arguments['--quiet']
    study = arguments['<study>']
    server = arguments['--server']
    credfile = arguments['--credfile']
    username = arguments['--username']
    archive = arguments['<archive>']

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
    logger.info('Loading config')

    cfg = datman.config.config(study=study)

    if not server:
        server = 'https://{}:{}'.format(cfg.get_key(['XNATSERVER']),
                                        cfg.get_key(['XNATPORT']))
    # setup the XNAT object
    if username:
        password = getpass.getpass()
    else:
        if not credfile:
            credfile = os.path.join(cfg.get_path('meta', study),
                                    'xnat-credentials')
        with open(credfile) as cf:
            lines = cf.readlines()
            username = lines[0].strip()
            password = lines[1].strip()

    XNAT = datman.xnat.xnat(server, username, password)

    dicom_dir = cfg.get_path('dicom', study)
    # deal with a single archive specified on the command line,
    # otherwise process all files in dicom_dir
    if archive:
        ext = datman.utils.splitext(archive)[1]
        if not ext:
            archive = archive + '.zip'

        basedir = os.path.dirname(os.path.normpath(archive))
        archives = [os.path.basename(os.path.normpath(archive))]
        if os.path.isfile(os.path.join(basedir, archives[0])):
            # file doesn't exist on the current path,
            # lets see if its in zips_dir
            dicom_dir = basedir
        else:
            if not os.path.isfile(os.path.join(dicom_dir, archives[0])):
                # die horribly
                msg = 'Cant find archive:{}'.format(archives[0])
                logger.error(msg)
                raise IOError(msg)
    else:
        archives = os.listdir(dicom_dir)

    logger.info('Processing files in:{}'.format(dicom_dir))
    logger.info('Processing {} files'.format(len(archives)))

    for archivefile in archives:
        scanid = archivefile[:-len(datman.utils.get_extension(archivefile))]
        archivefile = os.path.join(dicom_dir, archivefile)
        #  check the supplied archive is named correctly
        try:
            ident = datman.scanid.parse(scanid)
        except datman.scanid.ParseException:
            logger.warning('Invalid scanid:{} from archive:{}'
                           .format(scanid, archive))
            continue

        logger.debug('Processing file:{}'.format(scanid))
        # get the xant archive from the config

        xnat_project = cfg.get_key(['XNAT_Archive'],
                                   site=ident.site)
        try:
            XNAT.get_project(xnat_project)
        except datman.exceptions.XnatException as e:
            logger.error('Could not identify xnat archive'
                         ' for study: {} at site: {} with reason:{}'
                         .format(study, ident.site, e))
            continue

        logger.debug('Confimed xnat project name:{}'.format(xnat_project))

        try:
            xnat_subject = XNAT.get_session(xnat_project, str(ident), create=True)
        except datman.exceptions.XnatException as e:
            logger.error('Failed getting session:{} from xnat with reason:{}'
                         .format(str(ident), e))
            continue

        logger.debug('Got subject:{} from xnat'.format(str(ident)))

        files_exist = False
        try:
            files_exist = check_files_exist(archivefile, xnat_project, str(ident))
        except:
            continue

        if not files_exist:
            logger.info('Uploading dicoms from:{}'.format(archivefile))
            upload_dicom_data(archivefile, xnat_project, str(ident))
        else:
            logger.info('Archive:{} already on xnat.'.format(archivefile))

        logger.info('Uploading non-dicom data from:{}'.format(archivefile))
        upload_non_dicom_data(archivefile, xnat_project, str(ident))


def check_files_exist(archive, xnat_project, scanid):
    logger.info('Checking for archive:{} contents on xnat'.format(scanid))
    try:
        xnat_session = XNAT.get_session(xnat_project, scanid)
    except datman.exceptions.XnatException as e:
        logger.error('Failed getting session:{} from xnat project:{} with reason:{}'
                     .format(scanid, xnat_project, e))
        raise

    try:
        local_headers = datman.utils.get_archive_headers(archive)
    except:
        logger.error('Failed getting archive headers for:'.format(archive))
        raise

    try:
        xnat_session['children'][0]
    except (KeyError, IndexError):
        # session has no scan data uploaded yet
        return False

    xnat_scans = [child for child in xnat_session['children']
                  if child['field'] == 'experiments/experiment']
    xnat_scans = xnat_scans[0]
    xnat_scans = xnat_scans['items'][0]
    xnat_scans = xnat_scans['children']
    xnat_scans = [r['items'] for r in xnat_scans if r['field'] == 'scans/scan']

    xnat_scan_uids = [scan['data_fields']['UID']
                      for scan in xnat_scans[0]]

    local_scan_uids = [scan.SeriesInstanceUID
                       for scan
                       in local_headers.values()]

    xnat_experiment_id = [child for child in xnat_session['children']
                          if child['field'] == 'experiments/experiment']
    xnat_experiment_id = xnat_experiment_id[0]
    xnat_experiment_id = xnat_experiment_id['items'][0]
    xnat_experiment_id = xnat_experiment_id['data_fields']['UID']

    local_experiment_ids = [v.StudyInstanceUID for v in local_headers.values()]

    if not xnat_experiment_id in local_experiment_ids:
        msg = 'Study UID for archive:{} doesnt match XNAT'.format(archive)
        logger.error(msg)
        raise UserWarning(msg)

    if not set(local_scan_uids).issubset(set(xnat_scan_uids)):
        logger.info('UIDs in archive:{} not in xnat'.format(archive))
        return(False)

    return(True)


def upload_non_dicom_data(archive, xnat_project, scanid):
    zf = zipfile.ZipFile(archive)

    # filter dirs
    files = zf.namelist()
    files = filter(lambda f: not f.endswith('/'), files)

    # filter files named like dicoms
    files = filter(lambda f: not is_named_like_a_dicom(f), files)

    # filter actual dicoms :D.
    resource_files = []
    for f in files:
        try:
            if not is_dicom(io.BytesIO(zf.read(f))):
                resource_files.append(f)
        except zipfile.BadZipfile:
            logger.error('Error in zipfile:{}'.format(f))

    logger.info("Uploading {} files of non-dicom data..."
                .format(len(resource_files)))
    for f in resource_files:
        # convert to HTTP language
        try:
            XNAT.put_resource(xnat_project,
                              scanid,
                              scanid,
                              os.path.basename(f),
                              zf.read(f))
        except Exception as e:
            logger.error("Failed uploading file {} with error:{}"
                         .format(f, str(e)))

    return True


def upload_dicom_data(archive, xnat_project, scanid):
    try:
        ##update for XNAT
        XNAT.put_dicoms(xnat_project, scanid, scanid, archive)
    except Exception as e:
        logger.error('Failed uploading archive to xnat project:{}'
                     ' for subject:{}'.format(xnat_project, scanid))


def is_named_like_a_dicom(path):
    dcm_exts = ('dcm', 'img')
    return any(map(lambda x: path.lower().endswith(x), dcm_exts))


def is_dicom(fileobj):
    try:
        dicom.read_file(fileobj)
        return True
    except dicom.filereader.InvalidDicomError:
        return False

if __name__ == '__main__':
    main()
