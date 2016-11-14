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
import os
import getpass
import requests
import time
import zipfile
import urllib
import io
import dicom

logger = logging.getLogger(__file__)

username = None
password = None
server = None


def main():
    global username
    global server
    global password

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

    dicom_dir = cfg.get_path('dicom', study)
    # deal with a single archive specified on the command line,
    # otherwise process all files in dicom_dir
    if archive:
        ext = datman.utils.splitext(archive)[1]
        if not ext:
            archive = archive +'.zip'

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
        if not datman.scanid.is_scanid(scanid):
            logger.warning('Invalid scanid:{} from archive:{}'
                           .format(scanid, archive))
            continue
        else:
            ident = datman.scanid.parse(scanid)
        logger.debug('Processing file:{}'.format(scanid))
        # get the xant archive from the config

        xnat_project = cfg.get_key(['XNAT_Archive'],
                                   site=ident.site)
        if not check_xnat_project_exists(xnat_project):
            logger.error('Could not identify xnat archive'
                         ' for study: {} at site: {}'.format(study,
                                                            ident.site))
            continue

        logger.debug('Confimed xnat project name:{}'.format(xnat_project))

        xnat_subject = get_xnat_subject(scanid, xnat_project)
        if not xnat_subject:
            logger.error('Failed to get subject:{} from xnat'.format(scanid))
            continue
        logger.debug('Got subject:{} from xnat'
                     .format(scanid))

        try:
            if not check_files_exist(archivefile, xnat_project, scanid):
                logger.info('Uploading dicoms from:{}'.format(archivefile))
                upload_dicom_data(archivefile, xnat_project, scanid)
            else:
                logger.info('Archive:{} already on xnat.'.format(archivefile))
        except IOError:
            logger.error('Failed uploading dicom data from:{}'
                         .format(archivefile))
            return

        try:
            logger.info('Uploading non-dicom data from:{}'.format(archivefile))
            upload_non_dicom_data(archivefile, xnat_project, scanid)
        except requests.exceptions.HTTPError:
            logger.error('Failed uploading non-dicom data for subject:{}'
                         .format(scanid))
            return


def check_files_exist(archive, xnat_project, scanid):
    logger.info('Checking for archive:{} contents on xnat'.format(scanid))
    query_url = "{server}/data/archive/projects/{project}" \
                "/subjects/{scanid}?format=json" \
                .format(server=server, scanid=scanid, project=xnat_project)

    local_headers = datman.utils.get_archive_headers(archive)
    xnat_headers = make_xnat_query(query_url)

    xnat_scans = xnat_headers['items'][0]

    if not xnat_scans['children']:
        # session has no scan data uploaded yet
        return False

    xnat_scans = [child for child in xnat_scans['children']
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

    xnat_experiment_id = xnat_headers['items'][0]
    xnat_experiment_id = [child for child in xnat_experiment_id['children']
                          if child['field'] == 'experiments/experiment']
    xnat_experiment_id = xnat_experiment_id[0]
    xnat_experiment_id = xnat_experiment_id['items'][0]
    xnat_experiment_id = xnat_experiment_id['data_fields']['UID']

    local_experiment_id = local_headers.values()[0].StudyInstanceUID

    if not xnat_experiment_id == local_experiment_id:
        msg = 'Study UID for archive:{} doesnt match XNAT'.format(archive)
        logger.error(msg)
        raise UserWarning(msg)

    if not set(local_scan_uids).issubset(set(xnat_scan_uids)):
        logger.info('UIDs in archive:{} not in xnat'.format(archive))
        return(False)

    return(True)


def upload_non_dicom_data(archive, xnat_project, scanid):
    attach_url = "{server}/data/archive/projects/{project}/" \
                 "subjects/{subject}/experiments/{session}/" \
                 "files/{filename}?inbody=true"

    zf = zipfile.ZipFile(archive)

    # filter dirs
    files = zf.namelist()
    files = filter(lambda f: not f.endswith('/'), files)

    # filter files named like dicoms
    files = filter(lambda f: not is_named_like_a_dicom(f), files)

    # filter actual dicoms :D
    files = filter(lambda f: not is_dicom(io.BytesIO(zf.read(f))),
                   files)

    logger.info("Uploading {} files of non-dicom data...".format(len(files)))
    for f in files:
        # convert to HTTP language
        uploadname = urllib.quote(f)
        r = None
        try:
            r = requests.post(attach_url.format(filename=uploadname,
                                                server=server,
                                                project=xnat_project,
                                                subject=scanid,
                                                session=scanid),
                              data=zf.read(f),
                              auth=(username, password))
            r.raise_for_status()

        except requests.exceptions.HTTPError, e:
            logger.error("ERROR uploading file {}".format(f))
            raise e
    return True


def upload_dicom_data(archive, xnat_project, scanid):
    xnat_subject = get_xnat_subject(scanid, xnat_project)
    if not xnat_subject:
        logger.error('Subject:{} not found in xnat'.format(scanid))
        return
    xnat_subject_id = xnat_subject['ID']

    # xnat_experiment = get_xnat_experiment(scanid, scanid, xnat_project)
    # if not xnat_experiment:
    #     logger.error('Experiment:{} not found in xnat'.format(scanid))
    #     return
    #
    # xnat_experiment_id = xnat_experiment['ID']

    upload_url = "{server}/data/services/import?project={project}" \
                 "&subject={subject}&session={session}&overwrite=delete" \
                 "&prearchive=false&inbody=true".format(server=server,
                                                        project=xnat_project,
                                                        subject=xnat_subject_id,
                                                        session=scanid)

    try:
        make_xnat_post(upload_url, archive)
    except requests.exceptions.RequestException as e:
        logger.error('Failed uploading archive to xnat project:{}'
                     ' for subject:{}'.format(xnat_project, scanid))
        raise(e)


def get_xnat_subject(subject, xnat_study, create=True):
    """Checks xnat to see if a subject exists, creates if not"""
    create_url = "{server}/REST/projects/{project}/subjects/{subject}" \
        .format(server=server, project=xnat_study, subject=subject)

    xnat_subject = check_xnat_subject(subject, xnat_study)
    if xnat_subject:
        return(xnat_subject)

    if create:
        try:
            make_xnat_put(create_url)
            xnat_subject = check_xnat_subject(subject, xnat_study)
            return(xnat_subject)
        except requests.exceptions.RequestException:
            logger.error('Failed to create xnat subject:{}'.format(subject))
            return
    else:
        return None

def check_xnat_subject(subject, xnat_study):
    """Checks to see if a subject exists in xnat
    returns the subject object"""
    query_url = "{server}/data/archive/projects/{project}/subjects" \
                "?format=json".format(server=server, project=xnat_study)

    results = make_xnat_query(query_url)

    if not results:
        logger.error('Failed to query xnat for subject:{}'.format(subject))
        return
    results = results['ResultSet']['Result']
    names = [result['label'] for result in results]
    if subject in names:
        logger.debug('Found subject with label:{}'.format(subject))
        return results[names.index(subject)]
    else:
        logger.debug('Subject:{} doesnt exist'.format(subject))
        return False


def check_xnat_project_exists(project):
    query_url = '{}/data/archive/projects?format=json'.format(server)

    results = make_xnat_query(query_url)
    results = results['ResultSet']['Result']
    if not results:
        logger.error('Failed to query xnat for project:{}'.format(project))
        return

    names = [result['ID'] for result in results]
    if project in names:
        return True
    else:
        return


def make_xnat_query(url):
    response = requests.get(url, auth=(username, password))

    if not response.status_code == 200:
        logger.error('Failed connecting to xnat server:{}'
                     ' with response code:{}'
                     .format(server, response.status_code))
        logger.debug('Username: {}')
        response.raise_for_status()

    response = response.json()

    return(response)


def make_xnat_put(url):
    response = requests.put(url, auth=(username, password))

    if not response.status_code in [200, 201]:
        logger.error("http client error at folder creation: {}"
                     .format(response.status_code))
        response.raise_for_status()


def make_xnat_post(url, filename, retries=3):
    logger.info('POSTing data to xnat, {} retries left'.format(retries))
    logger.info('POSTing data to xnat, with url:{}'.format(url))
    with open(filename) as data:
        response = requests.post(url,
                                 auth=(username, password),
                                 headers={'Content-Type': 'application/zip'},
                                 data=data)
    if response.status_code is 504:
        if retries:
            logger.warning('xnat server timed out, retrying')
            time.sleep(30)
            make_xnat_post(url, filename, retries=retries - 1)
        else:
            logger.error('xnat server timed out, giving up')
            response.raise_for_status()

    elif response.status_code is not 200:
        logger.error('xnat error:{} at data upload, with message:{}'
                     .format(response.status_code,
                             response.text))
        response.raise_for_status()
    logger.info('Uploaded:{} to xnat'.format(filename))


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
