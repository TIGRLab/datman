"""Module to interact with the xnat server"""

import logging
import requests
import time
import tempfile
import os
import urllib
from exceptions import XnatException
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
            logger.warn('Failed getting xnat session')
            raise XnatException("Failed getting xnat session")

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        # Ends the session on the server side
        url = '{}/data/JSESSION'.format(self.server)
        self.session.delete(url)

    def get_xnat_session(self):
        """Setup a session with xnat"""
        url = '{}/data/JSESSION'.format(self.server)

        s = requests.Session()

        response = s.post(url, auth=self.auth)

        if not response.status_code == requests.codes.ok:
            logger.warn('Failed connecting to xnat server:{}'
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
        try:
            result = self._make_xnat_query(url)
        except:
            raise XnatException("Failed getting projects with url:{}"
                                .format(url))

        if not result:
            raise XnatException("No studies on server:{}"
                                .format(self.server))

        return(result['ResultSet']['Result'])

    def get_project(self, project):
        logger.debug('Querying xnat server for project:{}'.format(project))
        url = '{}/data/archive/projects/{}?format=json'.format(self.server,
                                                               project)
        try:
            result = self._make_xnat_query(url)
        except:
            raise XnatException("Failed getting project with url:{}"
                                .format(url))

        if not result:
            logger.warn('Project:{} not found'.format(project))
            raise XnatException("Project:{} not found. Are credentials"
                                "exported to the environment and clevis given"
                                "permission on the xnat project?"
                                .format(project))

        return(result['items'][0])

    def get_sessions(self, study):
        logger.debug('Querying xnat server for sessions in study'
                     .format(study))
        if not self.get_project(study):
            raise XnatException('Invalid xnat project:'
                                .format(study))

        url = '{}/data/archive/projects/{}/subjects/'.format(self.server,
                                                             study)
        try:
            result = self._make_xnat_query(url)
        except:
            raise XnatException("Failed getting xnat sessions with url:{}"
                                .format(url))

        if not result:
            raise XnatException('No sessions found for study:{}'.format(study))

        return(result['ResultSet']['Result'])

    def get_session(self, study, session, create=False):
        """Checks to see if session exists in xnat,
        if create and study doesnt exist will try to create it
        returns study or none"""
        logger.debug('Querying for session:{} in study:{}'
                     .format(session, study))
        url = '{}/data/archive/projects/{}/subjects/{}?format=json' \
              .format(self.server, study, session)

        try:
            result = self._make_xnat_query(url)
        except:
            raise XnatException("Failed getting session with url:{}"
                                .format(url))

        if not result:
            logger.info('Session:{} not found in study:{}'
                        .format(session, study))
            if create:
                try:
                    self.make_session(study, session)
                except:
                    raise XnatException("Failed to create session:{} in study:{}"
                                        .format(session, study))
                result = self.get_session(study, session)
                return result
        try:
            session_json = result['items'][0]
        except:
            msg = "Session:{} doesnt exist on xnat for study:{}".format(session,
                    study)
            raise XnatException(msg)

        return Session(session_json)

    def make_session(self, study, session):
        url = "{server}/REST/projects/{project}/subjects/{subject}"
        url = url.format(server=self.server,
                         project=study,
                         subject=session)
        try:
            self._make_xnat_put(url)
        except requests.exceptions.RequestException as e:
            logger.warn('Failed to create xnat subject:{}'.format(session))
            raise e

    def get_experiments(self, study, session):
        logger.debug('Getting experiments for session:{} in study:{}'
                     .format(session, study))
        url = '{}/data/archive/projects/{}' \
              '/subjects/{}/experiments/?format=json'.format(self.server,
                                                             study,
                                                             session)
        try:
            result = self._make_xnat_query(url)
        except:
            raise XnatException("Failed getting experiments with url:{}"
                                .format(url))

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
        try:
            result = self._make_xnat_query(url)
        except:
            raise XnatException("Failed getting experiments with url:{}"
                                .format(url))

        if not result:
            raise XnatException('Experiment:{} not found for session:{}'
                                ' in study:{}'
                                .format(experiment, session, study))

        return(result['items'][0])

    def get_scan_list(self, study, session, experiment):
        """The list of dicom scans in an experiment"""
        url = '{}/data/archive/projects/{}' \
              '/subjects/{}/experiments/{}' \
              '/scans/?format=json'.format(self.server,
                                           study,
                                           session,
                                           experiment)
        try:
            result = self._make_xnat_query(url)
        except:
            return XnatException('Failed getting scans with url:{}'
                                 .format(url))

        if result is None:
            e = XnatException('Scan not found for experiment:{}'
                              .format(experiment))
            e.study = study
            e.session = session
            raise e

        return(result['ResultSet']['Result'])

    def get_scan_info(self, study, session, experiment, scanid):
        """Returns info about an xnat scan"""
        url = '{}/data/archive/projects/{}' \
              '/subjects/{}/experiments/{}' \
              '/scans/{}/?format=json'.format(self.server,
                                              study,
                                              session,
                                              experiment,
                                              scanid)
        try:
            result = self._make_xnat_query(url)
        except:
            return XnatException('Failed getting scan with url:{}'
                                 .format(url))

        if result is None:
            e = XnatException('Scan:{} not found for experiment:{}'
                              .format(scanid, experiment))
            e.study = study
            e.session = session
            raise e

        return(result['items'][0])

    def get_resource_ids(self, study, session, experiment, folderName=None, create=True):
        """
        Return a list of resource id's (subfolders) from an experiment
        """
        logger.debug('Getting resource ids for expeiment:{}'
                     .format(experiment))
        url = '{}/data/archive/projects/{}' \
              '/subjects/{}/experiments/{}' \
              '/resources/?format=json'.format(self.server,
                                               study,
                                               session,
                                               experiment)
        try:
            result = self._make_xnat_query(url)
        except:
            raise XnatException("Failed getting resource ids with url:"
                                .format(url))
        if result is None:
            raise XnatException('Experiment:{} not found for session:{}'
                                ' in study:{}'
                                .format(experiment, session, study))

        if create and int(result['ResultSet']['totalRecords']) < 1:
            return self.create_resource_folder(study,
                                               session,
                                               experiment,
                                               folderName)

        resource_ids = {}
        for r in result['ResultSet']['Result']:
            try:
                label = r['label']
                resource_ids[label] = r['xnat_abstractresource_id']
            except KeyError:
                # some resource folders have no label
                resource_ids['No Label'] = r['xnat_abstractresource_id']

        if not folderName:
            # foldername not specified return them all
            resource_id = [val for val in resource_ids.itervalues()]
        else:
            # check if folder exists, if not create it
            try:
                resource_id = resource_ids[folderName]
            except KeyError:
                # folder doesn't exist, create it
                if not create:
                    return None
                else:
                    resource_id = self.create_resource_folder(study,
                                                              session,
                                                              experiment,
                                                              folderName)

        return resource_id

    def create_resource_folder(self, study, session, experiment, label):
        """
        Creates a resource subfolder and returns the xnat identifier.
        """
        url = '{}/data/archive/projects/{}' \
              '/subjects/{}/experiments/{}' \
              '/resources/{}/'.format(self.server,
                                        study,
                                        session,
                                        experiment,
                                        label)
        self._make_xnat_put(url)
        return self.get_resource_ids(study, session, experiment, label)

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
        try:
            result = self._make_xnat_xml_query(url)
        except:
            return XnatException("Failed getting resources with url:"
                                 .format(url))
        if result is None:
            raise XnatException('Experiment:{} not found for session:{}'
                                ' in study:{}'
                                .format(experiment, session, study))

        # define the xml namespace
        ns = {'cat': 'http://nrg.wustl.edu/catalog'}
        entries = result.find('cat:entries', ns)
        if entries is None:
            # no files found, just a label
            return None

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
        except XnatException as e:
            e.study = project
            e.session = session
            raise e
        except IOError as e:
            logger.error('Failed to open file:{} with excuse:'
                         .format(filename, e.strerror))
            err = XnatException("Error in file:{}".
                                format(filename))
            err.study = project
            err.session = session
            raise err
        except requests.exceptions.RequestException as e:
            err = XnatException("Error uploading data with url:{}"
                                .format(upload_url))
            err.study = project
            err.session = session
            raise err

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
            filename = tempfile.mkstemp(prefix="dm2_xnat_extract_")
            # mkstemp returns a filename and a file object
            # dealing with the filename in future so close the file object
            os.close(filename[0])
        try:
            self._get_xnat_stream(url, filename, retries)
            return(filename)
        except:
            try:
                os.remove(filename[1])
            except OSError as e:
                logger.warning('Failed to delete tempfile:{} with excuse:{}'
                               .format(filename, str(e)))
            err = XnatException("Failed getting dicom with url:{}".format(url))
            err.study = project
            err.session = session
            raise err

    def put_resource(self, project, session, experiment, filename, data, folder,
                     retries=3):
        """POST a resource file to the xnat server
        filename: string to store filename as
        data: string containing data
            (such as produced by zipfile.ZipFile.read())"""

        resource_id = self.get_resource_ids(project,
                                            session,
                                             experiment,
                                             folderName=folder)

        attach_url = "{server}/data/archive/projects/{project}/" \
                     "subjects/{subject}/experiments/{experiment}/" \
                     "resources/{resource_id}/" \
                     "files/{filename}?inbody=true"

        uploadname = urllib.quote(filename)

        url = attach_url.format(server=self.server,
                                project=project,
                                subject=session,
                                experiment=experiment,
                                resource_id=resource_id,
                                filename=uploadname)

        try:
            self._make_xnat_post(url, data)
        except XnatException as err:
            err.study = project
            err.session = session
            raise err
        except:
            logger.warning("Failed adding resource to xnat with url:{}"
                           .format(url))
            err = XnatException("Failed adding resource to xnat")
            err.study = project
            err.session = session

    def get_resource(self, project, session, experiment,
                     resource_group_id, resource_id,
                     filename=None, retries=3, zipped=True):
        """Download a single resource from xnat to filename
        If filename is not specified creates a temporary file and
        retrns the path to that, user needs to be responsible for
        cleaning up any created tempfiles"""


        url = '{}/data/archive/projects/{}/' \
              'subjects/{}/experiments/{}/' \
              'resources/{}/files/{}'.format(self.server,
                                             project,
                                             session,
                                             experiment,
                                             resource_group_id,
                                             resource_id)
        if zipped:
            url = url + '?format=zip'

        if not filename:
            filename = tempfile.mkstemp(prefix="dm2_xnat_extract_")
            #  mkstemp returns a file object and a filename
            #  we will deal with the filename in future so close the file object
            os.close(filename[0])
        try:
            self._get_xnat_stream(url, filename, retries)
            return(filename)
        except:
            try:
                os.remove(filename[1])
            except OSError as e:
                logger.warning('Failed to delete tempfile:{} with excude:{}'
                               .format(filename, str(e)))
            logger.error('Failed getting resource from xnat', exc_info=True)
            raise XnatException("Failed downloading resource with url:{}"
                                .format(url))

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
            filename = tempfile.mkstemp(prefix="dm2_xnat_extract_")
            #  mkstemp returns a file object and a filename
            #  we will deal with the filename in future so close the file object
            os.close(filename[0])
        try:
            self._get_xnat_stream(url, filename, retries)
            return(filename)
        except:
            try:
                os.remove(filename[1])
            except OSError as e:
                logger.warning('Failed to delete tempfile:{} with excude:{}'
                               .format(filename, str(e)))
            logger.error('Failed getting resource archive from xnat', exc_info=True)
            raise XnatException("Failed downloading resource archive with url:{}"
                                .format(url))

    def delete_resource(self, project, session, experiment,
                        resource_group_id, resource_id, retries=3):

        """Delete a resource file from xnat"""
        url = '{}/data/archive/projects/{}/' \
              'subjects/{}/experiments/{}/' \
              'resources/{}/files/{}'.format(self.server,
                                            project,
                                            session,
                                            experiment,
                                            resource_group_id,
                                            resource_id)
        try:
            self._make_xnat_delete(url)
        except:
            raise XnatException('Failed deleting resource with url:{}'
                                .format(url))

    def _get_xnat_stream(self, url, filename, retries=3, timeout=120):
        logger.info('Getting data from xnat')
        try:
            response = self.session.get(url, stream=True, timeout=timeout)
        except requests.exceptions.Timeout as e:
            if retries > 0:
                return(self._get_xnat_stream(url, filename, retries=retries-1,
                                             timeout=timeout*2))
            else:
                raise e

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info('Session may have expired, resetting')
            self.get_xnat_session()
            response = self.session.get(url, stream=True, timeout=timeout)

        if response.status_code == 404:
            logger.info("No records returned from xnat server to query:{}"
                         .format(url))
            return
        elif response.status_code is 504:
            if retries:
                logger.warning('xnat server timed out, retrying')
                time.sleep(30)
                self._get_xnat_stream(url, filename, retries=retries - 1,
                                      timeout=timeout * 2)
            else:
                logger.error('xnat server timed out, giving up')
                response.raise_for_status()
        elif response.status_code is not 200:
            logger.error('xnat error:{} at data upload'
                         .format(response.status_code))
            response.raise_for_status()

        with open(filename[1], 'wb') as f:
            try:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            except requests.exceptions.RequestException as e:
                logger.error('Failed reading from xnat')
                raise(e)
            except IOError as e:
                logger.error('Failed writing to file')
                raise(e)

    def _make_xnat_query(self, url, retries=3):
        try:
            response = self.session.get(url, timeout=30)
        except requests.exceptions.Timeout as e:
            if retries > 0:
                return(self._make_xnat_query(url, retries=retries-1))
            else:
                logger.error('Xnat server timed out getting url:{}'
                             .format(url))
                raise e

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info('Session may have expired, resetting')
            self.get_xnat_session()
            response = self.session.get(url, timeout=30)

        if response.status_code == 404:
            logger.info("No records returned from xnat server to query:{}"
                         .format(url))
            return
        elif not response.status_code == requests.codes.ok:
            logger.error('Failed connecting to xnat server:{}'
                         ' with response code:{}'
                         .format(self.server, response.status_code))
            logger.debug('Username: {}')
            response.raise_for_status()
        return(response.json())

    def _make_xnat_xml_query(self, url, retries=3):
        try:
            response = self.session.get(url, timeout=30)
        except requests.exceptions.Timeout as e:
            if retries > 0:
                return(self._make_xnat_xml_query(url, retries=retries-1))
            else:
                raise e

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info('Session may have expired, resetting')
            self.get_xnat_session()
            response = self.session.get(url, timeout=30)

        if response.status_code == 404:
            logger.info("No records returned from xnat server to query:{}"
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

    def _make_xnat_put(self, url, retries=3):
        if retries == 0:
            logger.info('Timed out making xnat put:{}'.format(url))
            requests.exceptions.HTTPError()

        try:
            response = self.session.put(url, timeout=30)
        except requests.exceptions.Timeout:
            return(self._make_xnat_put(url, retries=retries-1))

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info('Session may have expired, resetting')
            self.get_xnat_session()
            response = self.session.put(url, timeout=30)

        if not response.status_code in [200, 201]:
            logger.warn("http client error at folder creation: {}"
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
                logger.warn('xnat server timed out, giving up')
                response.raise_for_status()

        elif response.status_code is not 200:
            if 'multiple imaging sessions.' in response.content:
                raise XnatException('Multiple imaging sessions in archive,'
                                    ' check prearchive')
            if '502 Bad Gateway' in response.content:
                raise XnatException('Bad gateway error: Check tomcat logs')
            if 'Unable to identify experiment' in response.content:
                raise XnatException('Unable to identify experiment, did dicom upload fail?')
            else:
                raise XnatException('An unknown error occured uploading data.'
                                    'Status code:{}, reason:{}'
                                    .format(response.status_code,
                                            response.content))

    def _make_xnat_delete(self, url, retries=3):
        try:
            response = self.session.delete(url, timeout=30)
        except requests.exceptions.Timeout:
            return(self._make_xnat_delete(url, retries=retries-1))

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info('Session may have expired, resetting')
            self.get_xnat_session()
            response = self.session.delete(url, timeout=30)

        if not response.status_code in [200, 201]:
            logger.warn("http client error deleting resource: {}"
                        .format(response.status_code))
            response.raise_for_status()


class Session(object):

    raw_json = None

    def __init__(self, session_json):
        # Session attributes
        self.raw_json = session_json
        self.name = session_json['data_fields']['label']
        self.project = session_json['data_fields']['project']
        # Experiment attributes
        self.experiment = self._get_experiment()
        self.experiment_UID = self.experiment['data_fields']['UID']
        # Scan attributes
        self.scans = self._get_scans()
        self.scan_UIDs = self._get_scan_UIDs()
        # Resource attributes
        self.resource_IDs = self._get_resource_IDs()

    def _get_experiment(self):
        experiments = [exp for exp in self.raw_json['children']
                if exp['field'] == 'experiments/experiment']

        if not experiments:
            raise ValueError("No experiments found for {}".format(self.name))
        elif len(experiments) > 1:
            logger.error("More than one session uploaded to ID {}. Processing "
                    "only the first.".format(self.name))

        return experiments[0]['items'][0]

    def _get_scans(self):
        scans = [child['items'] for child in self.experiment['children']
                if child['field'] == 'scans/scan']
        if not scans:
            logger.info("No scans found for session {}".format(self.name))
            return scans
        return scans[0]

    def _get_scan_UIDs(self):
        scan_uids = [scan['data_fields']['UID'] for scan in self.scans]
        return scan_uids

    def _get_resource_IDs(self):
        resources = [resource['items'] for resource in self.experiment
                if resource['field'] == 'resources/resource']

        if not resources:
            return []

        # The dict seems to only be need for xnat_upload to check duplicate
        # resources. May be able to simplify and switch to a list of IDs...
        resource_ids = {}
        for resource in resources[0]:
            try:
                label = resource['data_fields']['label']
                resource_ids[label] = resource['data_fields']['xnat_abstractresource_id']
            except KeyError:
                resource_ids['No Label'] = resource['data_fields']['xnat_abstractresource_id']
        return resource_ids

    def  get_resources(self, xnat_connection):
        """
        Returns a list of all resource URIs from this session.
        """
        resources = []
        for r_id in self.resource_IDs:
            resource_list = xnat_connection.get_resource_list(self.project,
                    self.name, self.name, r_id)
            resources.extend([item['URI'] for item in resource_list])
        return resources
