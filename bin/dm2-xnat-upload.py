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

logger = logging.getLogger(__name__)
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

    if quiet:
        ch.setLevel(logging.ERROR)
    if verbose:
        ch.setLevel(logging.INFO)
    if debug:
        ch.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s - %(name)s - '
                                  '%(levelname)s - %(message)s')
    ch.setFormatter(formatter)

    logger.addHandler(ch)

    # setup the config object
    cfg = datman.config.config(study=study)

    if not server:
        server = 'https://{}:{}'.format(cfg.get_key(['XNATSERVER'],
                                                    cfg.get_key(['XNATPORT'])))

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

    for archivefile in archives:
        scanid = archivefile[:-len(datman.utils.get_extension(archivefile))]
        #  check the supplied archive is named correctly
        if not datman.scanid.is_scanid(scanid):
            logger.warning('Invalid scanid:{} from archive:{}'
                           .format(scanid, archive))
            continue
        else:
            ident = datman.scanid.parse(scanid)
        # get the xant archive from the config
        xnat_project = cfg.get_key(['XNAT_Archive'],
                                   site=ident.site)
        if not check_xnat_project_exists(xnat_project):
            logger.error('Could not identify xnat archive'
                         'for study: {} at site: {}'.format(study,
                                                            ident.site))
            return

        if not check_create_xnat_subject(scanid, xnat_project):
            logger.error('Failed to get subject:{} from xnat'.format(scanid))
            return

        try:
            upload_dicom_data(archive, xnat_project, scanid)
        except IOError:
            return

        try:
            upload_non_dicom_data(archive, xnat_project, scanid)
        except requests.exceptions.HTTPError:
            logger.error('Failed uploading non-dicom data for subject:{}'
                         .format(scanid))
            return


def upload_non_dicom_data(archive, xnat_project, scanid):
    attach_url = "{server}/data/archive/projects/{project}/" \
                 "subjects/{subject}/experiments/{session}/" \
                 "files/{filename}?inbody=true"

    zf = zipfile.ZipFile(archive)

    # filter dirs
    files = zf.namelist()
    files = filter(lambda f: not f.endswith('/'), files)

    # filter files named like dicoms
    files = filter(lambda f: not datman.utils.is_named_like_a_dicom(f), files)

    # filter actual dicoms :D
    files = filter(lambda f: not datman.utils.is_dicom(io.BytesIO(zf.read(f))),
                   files)

    logger.info("Uploading non-dicom data...")
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
    upload_url = "{server}/data/services/import?project={project}" \
                 "&subject={subject}&session={session}&overwrite=delete" \
                 "&prearchive=false&inbody=true".format(server=server,
                                                        project=xnat_project,
                                                        subject=scanid,
                                                        session=scanid)

    try:
        make_xnat_post(upload_url, archive)
    except requests.exceptions.RequestException as e:
        logger.error('Failed uploading archive to xnat project:{}'
                     ' for subject:{}'.format(xnat_project, scanid))
        raise(e)


def check_create_xnat_subject(subject, xnat_study, create=True):
    """Checks xnat to see if a subject exists, creates if not"""
    create_url = "{server}/REST/projects/{project}/subjects/{subject}" \
        .format(server=server, project=xnat_study, subject=subject)
    query_url = "{server}/data/archives/projects/{project}/subjects" \
                "?format=json".format(server=server, project=xnat_study)

    results = make_xnat_query(query_url)
    if not results:
        logger.error('Failed to query xnat for subject:{}'.subject)
        return

    names = [result['label'] for result in results]
    if subject in names:
        return True
    elif create:
        if not make_xnat_put(create_url):
            logger.error('Failed to create xnat subject:{}'.format(subject))
            return
    else:
        return


def check_xnat_project_exists(project):
    query_url = '{server}/data/archives/projects?format=json'.format(server)

    results = make_xnat_query(query_url)
    if not results:
        logger.error('Failed to query xnat for project:{}'.format(project))
        return

    names = [result['name'] for result in results]
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
    results = response['ResultSet']['Result']
    return(results)


def make_xnat_put(url):
    response = requests.put(url, auth=(username, password))

    if not response.status_code in [200, 201]:
        logger.error("http client error at folder creation: {}"
                     .format(response.status_code))
        response.raise_for_status()


def make_xnat_post(url, filename, retries=3):
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
        logger.error('xnat error:{} at data upload'
                     .format(response.status_code))
        response.raise_for_status()


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
    logging.basicConfig()
    main()
