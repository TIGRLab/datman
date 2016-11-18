"""Module to interact with the xnat server"""

import logging
import requests
import time
import tempfile
import os
import urllib
from xml.etree import ElementTree

logger = logging.getLogger(__name__)


class xnat(object):
    server = None
    auth = None
    headers = None
    session = None

    def __init__(self, server, username, password):
        if server.endswith('/'):
            server = server[:-1]
        self.server = server
        self.auth = (username, password)
        try:
            self.get_xnat_session()
        except Exception as e:
            logger.error('Failed getting xnat session')
            raise e

    def get_xnat_session(self):
        """Setup a session with xnat"""
        url = '{}/data/JSESSION'.format(self.server)

        s = requests.Session()

        response = s.post(url, auth=self.auth)

        if not response.status_code == requests.codes.ok:
            logger.error('Failed connecting to xnat server:{}'
                         ' with response code:{}'
                         .format(self.server, response.status_code))
            logger.debug('Username: {}')
            response.raise_for_status()

        s.cookies = requests.utils.cookiejar_from_dict({'JSESSIONID':
                                                        response.content})
        self.session = s

    def get_projects(self):
        """Queries the xnat server for a list of projects"""
        logger.debug('Querying xnat server for projects')
        url = '{}/data/archive/projects/?format=json'.format(self.server)
        result = self._make_xnat_query(url)

        if not result:
            logger.warn('No studies found on server:{}'.format(self.server))
            return

        return(result['ResultSet']['Result'])

    def get_project(self, project):
        logger.debug('Querying xnat server for project:{}'.format(project))
        url = '{}/data/archive/projects/{}?format=json'.format(self.server,
                                                               project)
        result = self._make_xnat_query(url)

        if not result:
            logger.warn('Project:{} not found'.format(project))
            return

        return(result['items'][0])

    def get_sessions(self, study):
        logger.debug('Querying xnat server for sessions in study'
                     .format(study))
        if not self.get_project(study):
            return
        url = '{}/data/archive/projects/{}/subjects/'.format(self.server,
                                                             study)
        result = self._make_xnat_query(url)

        if not result:
            logger.warn('No sessions found for study:{}'.format(study))
            return

        return(result['ResultSet']['Result'])

    def get_session(self, study, session, create=False):
        """Checks to see if session exists in xnat,
        if create and study doesnt exist will try to create it
        returns study or none"""
        logger.debug('Querying for session:{} in study:{}'
                     .format(session, study))
        url = '{}/data/archive/projects/{}/subjects/{}?format=json' \
              .format(self.server, study, session)

        result = self._make_xnat_query(url)

        if not result:
            logger.warn('Session:{} not found in study:{}'
                        .format(session, study))
            if create:
                self.make_session(study, session)
                result = self.get_session(study, session)
                return result
        try:
            return(result['items'][0])
        except (KeyError, ValueError):
            return None

    def make_session(self, study, session):
        url = "{server}/REST/projects/{project}/subjects/{subject}"
        url = url.format(server=self.server,
                         project=study,
                         subject=session)
        try:
            self._make_xnat_put(url)
        except requests.exceptions.RequestException:
            logger.error('Failed to create xnat subject:{}'.format(session))
            return

    def get_experiments(self, study, session):
        logger.debug('Getting experiments for session:{} in study:{}'
                     .format(session, study))
        url = '{}/data/archive/projects/{}' \
              '/subjects/{}/experiments/?format=json'.format(self.server,
                                                             study,
                                                             session)
        result = self._make_xnat_query(url)

        if not result:
            logger.warn('No experiments found for session:{} in study:{}'
                        .format(session, study))
            return

        return(result['ResultSet']['Result'])

    def get_experiment(self, study, session, experiment):
        logger.debug('Getting experiment:{} for session:{} in study:{}'
                     .format(experiment, session, study))
        url = '{}/data/archive/projects/{}' \
              '/subjects/{}/experiments/{}' \
              '?format=json'.format(self.server,
                                    study,
                                    session,
                                    experiment)

        result = self._make_xnat_query(url)

        if not result:
            logger.warn('Experiment:{} not found for session:{} in study:{}'
                        .format(experiment, session, study))
            return

        return(result['items'][0])

    def get_resource_list(self, study, session, experiment, resource_id):
        """The list of non-dicom resources associated with an experiment
        returns a list of dicts, mostly interested in ID and name"""
        logger.debug('Getting resource list for expeiment:{}'
                     .format(experiment))
        url = '{}/data/archive/projects/{}' \
              '/subjects/{}/experiments/{}' \
              '/resources/{}/?format=xml'.format(self.server,
                                                 study,
                                                 session,
                                                 experiment,
                                                 resource_id)
        result = self._make_xnat_xml_query(url)
        if result is None:
            logger.warn('Experiment:{} not found for session:{} in study:{}'
                        .format(experiment, session, study))
            return

        # define the xml namespace
        ns = {'cat': 'http://nrg.wustl.edu/catalog'}
        entries = result.find('cat:entries', ns)
        items = [entry.attrib for entry
                 in entries.findall('cat:entry', ns)]

        return(items)

    def find_session(self, session, projects=None):
        """Find a session label in the xnat archive
        searches all xnat projects unless study is specified
        in which case the search is limited to projects in the list"""
        if not projects:
            projects = self.get_projects()
            projects = [p['ID'] for p in projects]

        for project in projects:
            sessions = self.get_sessions(project)
            session_labels = [s['label'] for s in sessions]
            if session in session_labels:
                logger.debug('Found session:{} in project:{}'
                             .format(session, project))
                return(project)

    def put_dicoms(self, project, session, experiment, filename, retries=3):
        """Upload an archive of dicoms to XNAT
        filename: archive to upload"""
        headers = {'Content-Type': 'application/zip'}

        upload_url = "{server}/data/services/import?project={project}" \
                     "&subject={subject}&session={session}&overwrite=delete" \
                     "&prearchive=false&inbody=true"

        upload_url = upload_url.format(server=self.server,
                                       project=project,
                                       subject=session,
                                       session=experiment)
        try:
            with open(filename) as data:
                self._make_xnat_post(upload_url, data, retries, headers)
        except IOError as e:
            logger.error('Failed to open file:{} with excuse:'
                         .format(filename, e.strerror))
            raise e

    def get_dicom(self, project, session, experiment, scan,
                  filename=None, retries=3):
        """Downloads a dicom file from xnat to filename
        If filename is not specified creates a temporary file
        and returns the path to that, user needs to be responsible
        for cleaning up any created tempfiles"""
        url = '{}/data/archive/projects/{}/' \
              'subjects/{}/experiments/{}/' \
              'scans/{}/resources/DICOM/files?format=zip' \
              .format(self.server, project, session, experiment, scan)

        if not filename:
            filename = tempfile.mkstemp()

        if self._get_xnat_stream(url, filename, retries):
            return(filename)
        else:
            try:
                os.remove(filename[1])
            except OSError as e:
                logger.warning('Failed to delete tempfile:{} with excuse:{}'
                               .format(filename, str(e)))

    def put_resource(self, project, session, experiment, filename, data,
                     retries=3):
        """POST a resource file to the xnat server
        filename: string to store filename as
        data: string containing data
            (such as produced by zipfile.ZipFile.read())"""
        attach_url = "{server}/data/archive/projects/{project}/" \
                     "subjects/{subject}/experiments/{experiment}/" \
                     "files/{filename}?inbody=true"

        uploadname = urllib.quote(filename)
        url = attach_url.format(server=self.server,
                                project=project,
                                subject=session,
                                experiment=experiment,
                                filename=uploadname)

        self._make_xnat_post(url, data)

    def get_resource(self, project, session, experiment,
                     resource_group_id, resource_id,
                     filename=None, retries=3):
        """Download a single resource from xnat to filename
        If filename is not specified creates a temporary file and
        retrns the path to that, user needs to be responsible for
        cleaning up any created tempfiles"""

        url = '{}/data/archive/projects/{}/' \
              'subjects/{}/experiments/{}/' \
              'resources/{}/files/{}?format=zip'.format(self.server,
                                                        project,
                                                        session,
                                                        experiment,
                                                        resource_group_id,
                                                        resource_id)

        if not filename:
            filename = tempfile.mkstemp()

        if self._get_xnat_stream(url, filename, retries):
            return(filename)
        else:
            try:
                os.remove(filename[1])
            except OSError as e:
                logger.warning('Failed to delete tempfile:{} with excude:{}'
                               .format(filename, str(e)))

    def get_resource_archive(self, project, session, experiment, resource_id,
                             filename=None, retries=3):
        """Download a resource archive from xnat to filename
        If filename is not specified creates a temporary file and
        returns the path to that, user needs to be responsible format
        cleaning up any created tempfiles"""
        url = '{}/data/archive/projects/{}/' \
              'subjects/{}/experiments/{}/' \
              'resources/{}/files?format=zip' \
              .format(self.server, project, session, experiment, resource_id)

        if not filename:
            filename = tempfile.mkstemp()

        if self._get_xnat_stream(url, filename, retries):
            return(filename)
        else:
            try:
                os.remove(filename)
            except OSError as e:
                logger.warning('Failed to delete tempfile:{} with excuse:{}'
                               .format(filename, str(e)))


    def _get_xnat_stream(self, url, filename, retries=3):
        response = self.session.get(url, stream=True, timeout=30)

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info('Session may have expired, resetting')
            self.get_xnat_session()
            response = self.session.get(url, stream=True, timeout=30)

        if response.status_code == 404:
            logger.error("No records returned from xnat server to query:{}"
                         .format(url))
            return
        elif response.status_code is 504:
            if retries:
                logger.warning('xnat server timed out, retrying')
                time.sleep(30)
                self._get_xnat_stream(url, filename, retries=retries - 1)
            else:
                logger.error('xnat server timed out, giving up')
                response.raise_for_status()
        elif response.status_code is not 200:
            logger.error('xnat error:{} at data upload'
                         .format(response.status_code))
            response.raise_for_status()

        with open(filename[1], 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        return(True)

    def _make_xnat_query(self, url):
        response = self.session.get(url, timeout=30)

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info('Session may have expired, resetting')
            self.get_xnat_session()
            response = self.session.get(url, timeout=30)

        if response.status_code == 404:
            logger.error("No records returned from xnat server to query:{}"
                         .format(url))
            return
        elif not response.status_code == requests.codes.ok:
            logger.error('Failed connecting to xnat server:{}'
                         ' with response code:{}'
                         .format(self.server, response.status_code))
            logger.debug('Username: {}')
            response.raise_for_status()
        return(response.json())

    def _make_xnat_xml_query(self, url):
        response = self.session.get(url, timeout=30)

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info('Session may have expired, resetting')
            self.get_xnat_session()
            response = self.session.get(url, timeout=30)

        if response.status_code == 404:
            logger.error("No records returned from xnat server to query:{}"
                         .format(url))
            return
        elif not response.status_code == requests.codes.ok:
            logger.error('Failed connecting to xnat server:{}'
                         ' with response code:{}'
                         .format(self.server, response.status_code))
            logger.debug('Username: {}')
            response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        return(root)

    def _make_xnat_put(self, url):
        response = self.session.put(url, timeout=30)

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info('Session may have expired, resetting')
            self.get_xnat_session()
            response = self.session.put(url, timeout=30)

        if not response.status_code in [200, 201]:
            logger.error("http client error at folder creation: {}"
                         .format(response.status_code))
            response.raise_for_status()

    def _make_xnat_post(self, url, data, retries=3, headers=None):
        logger.debug('POSTing data to xnat, {} retries left'.format(retries))
        response = self.session.post(url,
                                     headers=headers,
                                     data=data,
                                     timeout=60*60)

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info('Session may have expired, resetting')
            self.get_xnat_session()
            response = self.session.post(url,
                                         headers=headers,
                                         data=data)

        if response.status_code is 504:
            if retries:
                logger.warning('xnat server timed out, retrying')
                time.sleep(30)
                self._make_xnat_post(url, data, retries=retries - 1)
            else:
                logger.error('xnat server timed out, giving up')
                response.raise_for_status()

        elif response.status_code is not 200:
            logger.error('xnat error:{} at data upload with reason:{}'
                         .format(response.status_code, response.content))
            response.raise_for_status()
