"""Module to interact with the xnat server"""

import logging
import requests
import time
import tempfile
import os

logger = logging.getLogger(__name__)


class xnat(object):
    server = None
    auth = None

    def __init__(self, server, username, password):
        self.server = server
        self.auth = (username, password)

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

    def get_session(self, study, session):
        logger.debug('Querying for session:{} in study:{}'
                     .format(session, study))
        url = '{}/data/archive/projects/{}/subjects/{}?format=json' \
              .format(self.server, study, session)

        result = self._make_xnat_query(url)

        if not result:
            logger.warn('Session:{} not found in study:{}'.format(session,
                                                                  study))
            return

        return(result['items'][0])

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
                os.remove(filename)
            except OSError as e:
                logger.warning('Failed to delete tempfile:{} with excuse:{}'
                               .format(filename, str(e)))

    def get_resource(self, project, session, experiment, resource_id,
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
        response = requests.get(url, auth=self.auth, stream=True)

        if response.status_code == 404:
            logger.error("No records returned from xnat server to query:{}"
                         .format(url))

            return
        elif response.status_code is 504:
            if retries:
                logger.warning('xnat server timed out, retrying')
                time.sleep(30)
                self._make_xnat_post(url, filename, retries=retries - 1)
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
        response = requests.get(url, auth=self.auth)

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

    def _make_xnat_put(self, url):
        response = requests.put(url, auth=self.auth)

        if not response.status_code in [200, 201]:
            logger.error("http client error at folder creation: {}"
                         .format(response.status_code))
            response.raise_for_status()

    def _make_xnat_post(self, url, filename, retries=3):
        logger.debug('POSTing data to xnat, {} retries left'.format(retries))
        with open(filename) as data:
            response = requests.post(url,
                                     auth=self.auth,
                                     headers={'Content-Type':
                                              'application/zip'},
                                     data=data)
        if response.status_code is 504:
            if retries:
                logger.warning('xnat server timed out, retrying')
                time.sleep(30)
                self._make_xnat_post(url, filename, retries=retries - 1)
            else:
                logger.error('xnat server timed out, giving up')
                response.raise_for_status()

        elif response.status_code is not 200:
            logger.error('xnat error:{} at data upload'
                         .format(response.status_code))
            response.raise_for_status()
        logger.info('Uploaded:{} to xnat'.format(filename))
