"""Module to interact with the xnat server"""

from abc import ABC
import getpass
import logging
import os
import re
import time
import tempfile
import urllib.parse
from xml.etree import ElementTree

import requests

from datman.exceptions import XnatException, ExportException

logger = logging.getLogger(__name__)


def get_server(config, url=None, port=None):
    if url and not port:
        # Avoid mangling user's url by appending a port from the config
        use_port = False
    else:
        use_port = True

    if not url:
        url = config.get_key("XNATSERVER")

    # Check for 'http' and NOT https, because checking for https could mangle a
    # url into https://http<restof>
    if not url.startswith("http"):
        url = "https://" + url

    if not use_port:
        return url

    try:
        port_str = get_port_str(config, port)
    except KeyError:
        logger.debug("'XNATPORT' undefined in config. Omitting port number "
                     "for {}".format(url))
        port_str = ""

    # Will create a bad url if a port is appended after '/'
    if url.endswith("/"):
        url = url[:-1]

    server = "{}{}".format(url, port_str)

    return server


def get_port_str(config, port):
    """
    Returns a port string of the format :portnum

    Will raise KeyError if port is None and config file doesnt define XNATPORT
    """
    if port is None:
        port = config.get_key("XNATPORT")

    if not str(port).startswith(":"):
        port = ":{}".format(port)

    return port


def get_auth(username=None):
    if username:
        return (username, getpass.getpass())

    try:
        username = os.environ["XNAT_USER"]
    except KeyError:
        raise KeyError("'XNAT_USER' not defined in environment")
    try:
        password = os.environ["XNAT_PASS"]
    except KeyError:
        raise KeyError("'XNAT_PASS' not defined in environment")

    return (username, password)


class xnat(object):
    server = None
    auth = None
    headers = None
    session = None

    def __init__(self, server, username, password):
        if server.endswith("/"):
            server = server[:-1]
        self.server = server
        self.auth = (username, password)
        try:
            self.open_session()
        except Exception:
            raise XnatException("Failed to open session with server {}".format(
                    server))

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        # Ends the session on the server side
        url = "{}/data/JSESSION".format(self.server)
        self.session.delete(url)

    def open_session(self):
        """Open a session with the XNAT server.
        """
        url = "{}/data/JSESSION".format(self.server)

        s = requests.Session()

        response = s.post(url, auth=self.auth)

        if not response.status_code == requests.codes.ok:
            logger.warn("Failed connecting to xnat server {} "
                        "with response code {}"
                        "".format(self.server, response.status_code))
            logger.debug("Username: {}")
            response.raise_for_status()

        # Cookies are set automatically, dont manually set them or it wipes
        # out other session info
        self.session = s

    def get_projects(self, project=""):
        """Query the XNAT server for project metadata.

        Args:
            project (str, optional): The name of an XNAT project to search for.
                If unset, metadata from all accessible projects on the server
                will be returned. Defaults to the empty string.

        Raises:
            XnatException: If failure is experienced while attempting to access
                the server's API.

        Returns:
            list: A list with one dictionary for each study found. Beware - the
                formats of the dictionaries returned by a server-wide versus a
                single project search differ greatly in structure.
                This is a consequence of XNAT's API.
        """
        logger.debug("Querying XNAT server for projects")
        if project:
            logger.debug("Narrowing search to {}".format(project))

        url = "{}/data/archive/projects/{}?format=json".format(
            self.server, project)

        try:
            result = self._make_xnat_query(url)
        except Exception:
            raise XnatException("Failed getting projects from server with "
                                "search URL {}".format(url))

        if not result:
            logger.debug("No projects found on server {}".format(self.server))
            return []

        if not project:
            return result["ResultSet"]["Result"]

        return result["items"]

    def get_subject_ids(self, project):
        """Return IDs for all subjects within an XNAT project.

        Args:
            project (:obj:`str`): The 'Project ID' for a project on XNAT.

        Raises:
            XnatException: If the project does not exist or access fails.

        Returns:
            list: A list of string subject IDs found within the project.
        """
        logger.debug("Querying xnat server {} for subjects in project {}"
                     .format(self.server, project))

        if not self.get_project(project):
            raise XnatException("Invalid XNAT project: {}".format(project))

        url = "{}/data/archive/projects/{}/subjects/".format(
            self.server, project)

        try:
            result = self._make_xnat_query(url)
        except Exception:
            raise XnatException("Failed getting xnat sessions with URL {}"
                                .format(url))

        if not result:
            return []

        return [item.get("label") for item in result["ResultSet"]["Result"]]

    def get_subject(self, project, subject_id, create=False):
        """Get a subject from the XNAT server.

        Args:
            project (:obj:`str`): The XNAT project to search within.
            subject_id (:obj:`str`): The XNAT subject to retrieve.
            create (bool, optional): Whether to create a subject matching
                subject_id if a match is not found. Defaults to False.

        Raises:
            XnatException: If access through the API failed or if the subject
                does not exist and can't be made.

        Returns:
            :obj:`datman.xnat.XNATSubject`: An XNATSubject instance matching
                the given subject_id.
        """
        logger.debug("Querying for subject {} in project {}"
                     .format(subject_id, project))

        url = "{}/data/archive/projects/{}/subjects/{}?format=json" \
              .format(self.server, project, subject_id)

        try:
            result = self._make_xnat_query(url)
        except Exception:
            raise XnatException("Failed getting subject {} with URL {}"
                                .format(subject_id, url))

        if not create and not result:
            raise XnatException("Subject {} does not exist for project "
                                "{}".format(subject_id, project))

        if not result:
            logger.info("Creating {} in project {}".format(
                subject_id, project))
            self.make_subject(project, subject_id)
            return self.get_subject(project, subject_id)

        try:
            subject_json = result["items"][0]
        except (IndexError, KeyError):
            raise XnatException("Could not access metadata about subject {}"
                                "".format(subject_id, project))

        return XNATSubject(subject_json)

    def make_subject(self, project, subject):
        """Make a new (empty) subject on the XNAT server.

        Args:
            project (:obj:`str`): The 'Project ID' of an existing XNAT project.
            subject (:obj:`str`): The ID to create the new subject under.

        Raises:
            XnatException: If subject creation fails.
        """
        url = "{}/REST/projects/{}/subjects/{}".format(
            self.server, project, subject)

        try:
            self._make_xnat_put(url)
        except requests.exceptions.RequestException as e:
            raise XnatException("Failed to create xnat subject {} in project "
                                "{}. Reason - {}".format(subject, project, e))

    def get_experiments(self, study, session):
        logger.debug("Getting experiments for session: {} in study: {}"
                     .format(session, study))
        url = "{}/data/archive/projects/{}" \
              "/subjects/{}/experiments/?format=json".format(self.server,
                                                             study,
                                                             session)
        try:
            result = self._make_xnat_query(url)
        except Exception:
            raise XnatException("Failed getting experiments with url: {}"
                                .format(url))

        if not result:
            logger.warn("No experiments found for session: {} in study: {}"
                        .format(session, study))
            return

        return(result["ResultSet"]["Result"])

    def get_experiment(self, study, session, experiment):
        logger.debug("Getting experiment: {} for session: {} in study: {}"
                     .format(experiment, session, study))
        url = "{}/data/archive/projects/{}" \
              "/subjects/{}/experiments/{}" \
              "?format=json".format(self.server,
                                    study,
                                    session,
                                    experiment)
        try:
            result = self._make_xnat_query(url)
        except Exception:
            raise XnatException("Failed getting experiments with url: {}"
                                .format(url))

        if not result:
            raise XnatException("Experiment: {} not found for session: {}"
                                " in study: {}"
                                .format(experiment, session, study))

        return result["items"][0]

    def make_experiment(self, project, session, experiment):
        """
        Submits a PUT request to XNAT API to make experiment for a given
        project and session
        """

        url = "{server}/data/archive/projects/{project}/" \
              "subjects/{subject}/experiments/{experiment}" \
              "?xsiType=xnat:mrSessionData" \
              .format(server=self.server,
                      project=project,
                      subject=session,
                      experiment=experiment)

        self._make_xnat_put(url)

    def get_scan_list(self, study, session, experiment):
        """The list of dicom scans in an experiment"""
        url = "{}/data/archive/projects/{}" \
              "/subjects/{}/experiments/{}" \
              "/scans/?format=json".format(self.server,
                                           study,
                                           session,
                                           experiment)
        try:
            result = self._make_xnat_query(url)
        except Exception:
            raise XnatException("Failed getting scans with url: {}"
                                "".format(url))

        if result is None:
            e = XnatException("Scan not found for experiment: {}"
                              .format(experiment))
            e.study = study
            e.session = session
            raise e

        return result["ResultSet"]["Result"]

    def get_scan_info(self, study, session, experiment, scanid):
        """Returns info about an xnat scan"""
        url = "{}/data/archive/projects/{}" \
              "/subjects/{}/experiments/{}" \
              "/scans/{}/?format=json".format(self.server,
                                              study,
                                              session,
                                              experiment,
                                              scanid)
        try:
            result = self._make_xnat_query(url)
        except Exception:
            raise XnatException("Failed getting scan with url: {}"
                                "".format(url))

        if result is None:
            e = XnatException("Scan:{} not found for experiment: {}"
                              .format(scanid, experiment))
            e.study = study
            e.session = session
            raise e

        return result["items"][0]

    def get_resource_ids(self, study, session, experiment, folderName=None,
                         create=True):
        """
        Return a list of resource id's (subfolders) from an experiment
        """
        logger.debug("Getting resource ids for expeiment: {}"
                     .format(experiment))
        url = "{}/data/archive/projects/{}" \
              "/subjects/{}/experiments/{}" \
              "/resources/?format=json".format(self.server,
                                               study,
                                               session,
                                               experiment)
        try:
            result = self._make_xnat_query(url)
        except Exception:
            raise XnatException("Failed getting resource ids with url: {}"
                                .format(url))
        if result is None:
            raise XnatException("Experiment: {} not found for session: {}"
                                " in study: {}"
                                .format(experiment, session, study))

        if create and int(result["ResultSet"]["totalRecords"]) < 1:
            return self.create_resource_folder(study,
                                               session,
                                               experiment,
                                               folderName)

        resource_ids = {}
        for r in result["ResultSet"]["Result"]:
            try:
                label = r["label"]
                resource_ids[label] = r["xnat_abstractresource_id"]
            except KeyError:
                # some resource folders have no label
                resource_ids["No Label"] = r["xnat_abstractresource_id"]

        if not folderName:
            # foldername not specified return them all
            resource_id = [val for val in resource_ids.values()]
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
        url = "{}/data/archive/projects/{}" \
              "/subjects/{}/experiments/{}" \
              "/resources/{}/".format(self.server,
                                      study,
                                      session,
                                      experiment,
                                      label)
        self._make_xnat_put(url)
        return self.get_resource_ids(study, session, experiment, label)

    def get_resource_list(self, study, session, experiment, resource_id):
        """The list of non-dicom resources associated with an experiment
        returns a list of dicts, mostly interested in ID and name"""
        logger.debug("Getting resource list for expeiment: {}"
                     .format(experiment))
        url = "{}/data/archive/projects/{}" \
              "/subjects/{}/experiments/{}" \
              "/resources/{}/?format=xml".format(self.server,
                                                 study,
                                                 session,
                                                 experiment,
                                                 resource_id)
        try:
            result = self._make_xnat_xml_query(url)
        except Exception:
            raise XnatException("Failed getting resources with url: {}"
                                "".format(url))
        if result is None:
            raise XnatException("Experiment: {} not found for session: {}"
                                " in study: {}"
                                .format(experiment, session, study))

        # define the xml namespace
        ns = {"cat": "http://nrg.wustl.edu/catalog"}
        entries = result.find("cat:entries", ns)
        if entries is None:
            # no files found, just a label
            return []

        items = [entry.attrib for entry
                 in entries.findall("cat:entry", ns)]

        return items

    def find_session(self, subject_id, projects=None):
        """Find a session label in the xnat archive
        searches all xnat projects unless study is specified
        in which case the search is limited to projects in the list"""
        if not projects:
            projects = self.get_projects()
            projects = [p["ID"] for p in projects]

        for project in projects:
            if subject_id in self.get_subject_ids(project):
                logger.debug("Found session {} in project {}"
                             .format(subject_id, project))
                return project

    def put_dicoms(self, project, session, experiment, filename, retries=3):
        """Upload an archive of dicoms to XNAT
        filename: archive to upload"""
        headers = {"Content-Type": "application/zip"}

        upload_url = "{server}/data/services/import?project={project}" \
                     "&subject={subject}&session={session}&overwrite=delete" \
                     "&prearchive=false&inbody=true"

        upload_url = upload_url.format(server=self.server,
                                       project=project,
                                       subject=session,
                                       session=experiment)
        try:
            with open(filename, "rb") as data:
                self._make_xnat_post(upload_url, data, retries, headers)
        except XnatException as e:
            e.study = project
            e.session = session
            raise e
        except IOError as e:
            logger.error("Failed to open file: {} with excuse: {}"
                         .format(filename, e.strerror))
            err = XnatException("Error in file: {}".
                                format(filename))
            err.study = project
            err.session = session
            raise err
        except requests.exceptions.RequestException:
            err = XnatException("Error uploading data with url: {}"
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
        url = "{}/data/archive/projects/{}/" \
              "subjects/{}/experiments/{}/" \
              "scans/{}/resources/DICOM/files?format=zip" \
              .format(self.server, project, session, experiment, scan)

        if not filename:
            filename = tempfile.mkstemp(prefix="dm2_xnat_extract_")
            # mkstemp returns a filename and a file object
            # dealing with the filename in future so close the file object
            os.close(filename[0])
            filename = filename[1]
        try:
            self._get_xnat_stream(url, filename, retries)
            return(filename)
        except Exception:
            try:
                os.remove(filename)
            except OSError as e:
                logger.warning("Failed to delete tempfile: {} with excuse: {}"
                               .format(filename, str(e)))
            err = XnatException("Failed getting dicom with url: {}".format(url))
            err.study = project
            err.session = session
            raise err

    def put_resource(self, project, session, experiment, filename, data,
                     folder, retries=3):
        """
        POST a resource file to the xnat server
        filename: string to store filename as
        data: string containing data
            (such as produced by zipfile.ZipFile.read())
        """

        try:
            self.get_experiment(project, session, experiment)
        except XnatException:
            logger.warning("Experiment: {} in session: {} does not exist! "
                           "Making new experiment".format(experiment, session))
            self.make_experiment(project, session, experiment)

        resource_id = self.get_resource_ids(project,
                                            session,
                                            experiment,
                                            folderName=folder)

        attach_url = "{server}/data/archive/projects/{project}/" \
                     "subjects/{subject}/experiments/{experiment}/" \
                     "resources/{resource_id}/" \
                     "files/{filename}?inbody=true"

        uploadname = urllib.parse.quote(filename)

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
        except Exception:
            logger.warning("Failed adding resource to xnat with url: {}"
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

        url = "{}/data/archive/projects/{}/" \
              "subjects/{}/experiments/{}/" \
              "resources/{}/files/{}".format(self.server,
                                             project,
                                             session,
                                             experiment,
                                             resource_group_id,
                                             resource_id)
        if zipped:
            url = url + "?format=zip"

        if not filename:
            filename = tempfile.mkstemp(prefix="dm2_xnat_extract_")
            # mkstemp returns a file object and a filename we will deal with
            # the filename in future so close the file object
            os.close(filename[0])
            filename = filename[1]
        try:
            self._get_xnat_stream(url, filename, retries)
            return(filename)
        except Exception:
            try:
                os.remove(filename)
            except OSError as e:
                logger.warning("Failed to delete tempfile: {} with excude: {}"
                               .format(filename, str(e)))
            logger.error("Failed getting resource from xnat", exc_info=True)
            raise XnatException("Failed downloading resource with url: {}"
                                .format(url))

    def get_resource_archive(self, project, session, experiment, resource_id,
                             filename=None, retries=3):
        """Download a resource archive from xnat to filename
        If filename is not specified creates a temporary file and
        returns the path to that, user needs to be responsible format
        cleaning up any created tempfiles"""
        url = "{}/data/archive/projects/{}/" \
              "subjects/{}/experiments/{}/" \
              "resources/{}/files?format=zip" \
              .format(self.server, project, session, experiment, resource_id)

        if not filename:
            filename = tempfile.mkstemp(prefix="dm2_xnat_extract_")
            # mkstemp returns a file object and a filename we will deal
            # with the filename in future so close the file object
            os.close(filename[0])
            filename = filename[1]
        try:
            self._get_xnat_stream(url, filename, retries)
            return(filename)
        except Exception:
            try:
                os.remove(filename)
            except OSError as e:
                logger.warning("Failed to delete tempfile: {} with error: {}"
                               .format(filename, str(e)))
            logger.error("Failed getting resource archive from xnat",
                         exc_info=True)
            raise XnatException("Failed downloading resource archive with "
                                "url: {}".format(url))

    def delete_resource(self, project, session, experiment,
                        resource_group_id, resource_id, retries=3):

        """Delete a resource file from xnat"""
        url = "{}/data/archive/projects/{}/" \
              "subjects/{}/experiments/{}/" \
              "resources/{}/files/{}".format(self.server,
                                             project,
                                             session,
                                             experiment,
                                             resource_group_id,
                                             resource_id)
        try:
            self._make_xnat_delete(url)
        except Exception:
            raise XnatException("Failed deleting resource with url: {}"
                                .format(url))

    def _get_xnat_stream(self, url, filename, retries=3, timeout=120):
        logger.debug("Getting {} from XNAT".format(url))
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
            logger.info("Session may have expired, resetting")
            self.open_session()
            response = self.session.get(url, stream=True, timeout=timeout)

        if response.status_code == 404:
            logger.info("No records returned from xnat server for query: {}"
                        "".format(url))
            return
        elif response.status_code == 504:
            if retries:
                logger.warning("xnat server timed out, retrying")
                time.sleep(30)
                self._get_xnat_stream(url, filename, retries=retries - 1,
                                      timeout=timeout * 2)
            else:
                logger.error("xnat server timed out, giving up")
                response.raise_for_status()
        elif response.status_code != 200:
            logger.error("xnat error: {} at data upload"
                         .format(response.status_code))
            response.raise_for_status()

        with open(filename, "wb") as f:
            try:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            except requests.exceptions.RequestException as e:
                logger.error("Failed reading from xnat")
                raise(e)
            except IOError as e:
                logger.error("Failed writing to file")
                raise(e)

    def _make_xnat_query(self, url, retries=3):
        try:
            response = self.session.get(url, timeout=30)
        except requests.exceptions.Timeout as e:
            if retries > 0:
                return(self._make_xnat_query(url, retries=retries-1))
            else:
                logger.error("Xnat server timed out getting url {}"
                             "".format(url))
                raise e

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info("Session may have expired, resetting")
            self.open_session()
            response = self.session.get(url, timeout=30)

        if response.status_code == 404:
            logger.info("No records returned from xnat server for query: {}"
                        "".format(url))
            return
        elif not response.status_code == requests.codes.ok:
            logger.error("Failed connecting to xnat server {} "
                         "with response code {}"
                         .format(self.server, response.status_code))
            logger.debug("Username: {}")
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
            logger.info("Session may have expired, resetting")
            self.open_session()
            response = self.session.get(url, timeout=30)

        if response.status_code == 404:
            logger.info("No records returned from xnat server to query {}"
                        "".format(url))
            return
        elif not response.status_code == requests.codes.ok:
            logger.error("Failed connecting to xnat server {}"
                         " with response code {}"
                         .format(self.server, response.status_code))
            logger.debug("Username: {}")
            response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        return(root)

    def _make_xnat_put(self, url, retries=3):
        if retries == 0:
            logger.info("Timed out making xnat put {}".format(url))
            requests.exceptions.HTTPError()

        try:
            response = self.session.put(url, timeout=30)
        except requests.exceptions.Timeout:
            return(self._make_xnat_put(url, retries=retries-1))

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info("Session may have expired, resetting")
            self.open_session()
            response = self.session.put(url, timeout=30)

        if response.status_code not in [200, 201]:
            logger.warn("http client error at folder creation: {}"
                        .format(response.status_code))
            response.raise_for_status()

    def _make_xnat_post(self, url, data, retries=3, headers=None):
        logger.debug("POSTing data to xnat, {} retries left".format(retries))
        response = self.session.post(url,
                                     headers=headers,
                                     data=data,
                                     timeout=60*60)

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info("Session may have expired, resetting")
            self.open_session()
            response = self.session.post(url,
                                         headers=headers,
                                         data=data)

        if response.status_code == 504:
            if retries:
                logger.warning("xnat server timed out, retrying")
                time.sleep(30)
                self._make_xnat_post(url, data, retries=retries - 1)
            else:
                logger.warn("xnat server timed out, giving up")
                response.raise_for_status()

        elif response.status_code != 200:
            if "multiple imaging sessions." in response.content:
                raise XnatException("Multiple imaging sessions in archive,"
                                    " check prearchive")
            if "502 Bad Gateway" in response.content:
                raise XnatException("Bad gateway error: Check tomcat logs")
            if "Unable to identify experiment" in response.content:
                raise XnatException("Unable to identify experiment, did "
                                    "dicom upload fail?")
            else:
                raise XnatException("An unknown error occured uploading data."
                                    "Status code: {}, reason: {}"
                                    .format(response.status_code,
                                            response.content))

    def _make_xnat_delete(self, url, retries=3):
        try:
            response = self.session.delete(url, timeout=30)
        except requests.exceptions.Timeout:
            return(self._make_xnat_delete(url, retries=retries-1))

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info("Session may have expired, resetting")
            self.open_session()
            response = self.session.delete(url, timeout=30)

        if response.status_code not in [200, 201]:
            logger.warn("http client error deleting resource: {}"
                        .format(response.status_code))
            response.raise_for_status()


class XNATObject(ABC):
    def _get_field(self, key):
        if not self.raw_json.get("data_fields"):
            return ""
        return self.raw_json["data_fields"].get(key, "")


class XNATSubject(XNATObject):

    def __init__(self, subject_json):
        self.raw_json = subject_json
        self.name = self._get_field("label")
        self.project = self._get_field("project")
        self.experiments = self._get_experiments()

    def _get_experiments(self):
        experiments = [exp for exp in self.raw_json["children"]
                       if exp["field"] == "experiments/experiment"]

        if not experiments:
            logger.debug("No experiments found for {}".format(self.name))
            return {}

        found = {}
        for item in experiments[0]["items"]:
            exper = XNATExperiment(self.name, item)
            found[exper.name] = exper

        return found

    def __str__(self):
        return "<XNATSubject {}>".format(self.name)

    def __repr__(self):
        return self.__str__()


class XNATExperiment(XNATObject):

    def __init__(self, session_name, experiment_json):
        self.raw_json = experiment_json
        self.session = session_name
        self.uid = self._get_field("UID")
        self.id = self._get_field("ID")
        self.name = self._get_field("label")
        self.date = self._get_field("date")

        # Scan attributes
        self.scans = self._get_scans()
        self.scan_UIDs = self._get_scan_UIDs()
        self.scan_resource_IDs = self._get_scan_rIDs()

        # Resource attributes
        self.resource_files = self._get_contents("resources/resource")
        self.resource_IDs = self._get_resource_IDs()

        # Misc - basically just OPT CU1 needs this
        self.misc_resource_IDs = self._get_other_resource_IDs()

    def _get_contents(self, data_type):
        children = self.raw_json.get("children", [])

        contents = [child["items"] for child in children
                    if child["field"] == data_type]
        return contents

    def _get_scans(self):
        scans = self._get_contents("scans/scan")
        if not scans:
            logger.debug("No scans found for experiment {}".format(self.name))
            return scans
        xnat_scans = []
        for scan_json in scans[0]:
            xnat_scans.append(XNATSeries(self.name, scan_json))
        return xnat_scans

    def _get_scan_UIDs(self):
        return [scan.uid for scan in self.scans]

    def _get_scan_rIDs(self):
        # These can be used to download a series from xnat
        resource_ids = []
        for scan in self.scans:
            for child in scan.raw_json["children"]:
                if child["field"] != "file":
                    continue
                for item in child["items"]:
                    try:
                        label = item["data_fields"]["label"]
                    except KeyError:
                        continue
                    if label != "DICOM":
                        continue
                    r_id = item["data_fields"]["xnat_abstractresource_id"]
                    resource_ids.append(str(r_id))
        return resource_ids

    def _get_resource_IDs(self):
        if not self.resource_files:
            return {}

        resource_ids = {}
        for resource in self.resource_files[0]:
            label = resource["data_fields"].get("label", "No Label")
            resource_ids[label] = str(resource["data_fields"][
                                                "xnat_abstractresource_id"])
        return resource_ids

    def _get_other_resource_IDs(self):
        """
        OPT's CU site uploads niftis to their server. These niftis are neither
        classified as resources nor as scans so our code misses them entirely.
        This functions grabs the abstractresource_id for these and
        any other unique files aside from snapshots so they can be downloaded
        """
        r_ids = []
        for scan in self.scans:
            for child in scan.raw_json["children"]:
                for file_upload in child["items"]:
                    data_fields = file_upload["data_fields"]
                    try:
                        label = data_fields["label"]
                    except KeyError:
                        # Some entries dont have labels. Only hold some header
                        # values. These are safe to ignore
                        continue

                    try:
                        data_format = data_fields["format"]
                    except KeyError:
                        # Some entries have labels but no format... or neither
                        if not label:
                            # If neither, ignore. Should just be an entry
                            # containing scan parameters, etc.
                            continue
                        data_format = label

                    try:
                        r_id = str(data_fields["xnat_abstractresource_id"])
                    except KeyError:
                        # Some entries have labels and/or a format but no
                        # actual files and so no resource id. These can also be
                        # safely ignored.
                        continue

                    # ignore DICOM, it's grabbed elsewhere. Ignore snapshots
                    # entirely. Some things may not be labelled DICOM but may
                    # be format 'DICOM' so that needs to be checked for too.
                    if label != "DICOM" and (data_format != "DICOM" and
                                             label != "SNAPSHOTS"):
                        r_ids.append(r_id)
        return r_ids

    def get_resources(self, xnat_connection):
        """
        Returns a list of all resource URIs from this session.
        """
        resources = []
        resource_ids = list(self.resource_IDs.values())
        resource_ids.extend(self.misc_resource_IDs)
        for r_id in resource_ids:
            resource_list = xnat_connection.get_resource_list(
                                    self.project,
                                    self.name,
                                    self.experiment_label,
                                    r_id)
            resources.extend([item["URI"] for item in resource_list])
        return resources

    def download(self, xnat, dest_folder, zip_name=None):
        """
        Download a zip file containing all data for this session. Returns the
        path to the new file if download is successful, raises an exception if
        not

        xnat                An instance of datman.xnat.xnat()
        dest_folder         The absolute path to the folder where the zip
                            should be deposited
        zip_name            An optional name for the output zip file. If not
                            set the zip name will be session.name
        """
        # Grab dicoms
        resources_list = self.scan_resource_IDs
        # Grab what we define as resources (i.e. tech notes, non-dicoms)
        resources_list.extend(list(self.resource_IDs.values()))
        # Grab anything else other than snapshots (i.e. 'MUX' for OPT CU1)
        resources_list.extend(self.misc_resource_IDs)

        if not resources_list:
            raise ValueError("No scans or resources found for {}"
                             "".format(self.name))

        url = ("{}/REST/experiments/{}/resources/{}/files"
               "?structure=improved&all=true&format=zip".format(
                            xnat.server,
                            self.id,
                            ",".join(resources_list)))

        if not zip_name:
            zip_name = self.session.upper() + ".zip"

        output_path = os.path.join(dest_folder, zip_name)
        if os.path.exists(output_path):
            logger.error("Cannot download {}, file already exists.".format(
                    output_path))
            return output_path

        xnat._get_xnat_stream(url, output_path)

        return output_path

    def __str__(self):
        return "<XNATExperiment {}>".format(self.name)

    def __repr__(self):
        return self.__str__()


class XNATSeries(XNATObject):

    def __init__(self, experiment_name, scan_json):
        self.raw_json = scan_json
        self.experiment = experiment_name
        self.uid = self._get_field("UID")
        self.series = self._get_field("ID")
        self.image_type = self._get_field("parameters/imageType")
        self.multiecho = self.is_multiecho()
        self.description = self._set_description()

    def _set_description(self):
        series_descr = self._get_field("series_description")
        if series_descr:
            return series_descr
        return self._get_field("type")

    def is_multiecho(self):
        try:
            child = self.raw_json["children"][0]["items"][0]
        except (KeyError, IndexError):
            return False
        name = child["data_fields"].get("name")
        if name and "MultiEcho" in name:
            return True
        return False

    def raw_dicoms_exist(self):
        for child in self.raw_json["children"]:
            for item in child["items"]:
                file_type = item["data_fields"].get("content")
                if file_type == "RAW":
                    return True
        return False

    def is_derived(self):
        if not self.image_type:
            logger.warning("Image type could not be found for series {}. "
                           "Assuming it's derived.".format(self.series))
            return True
        if "DERIVED" in self.image_type:
            return True
        return False

    def set_tag(self, tag_map):
        matches = {}
        for tag, pattern in tag_map.items():
            regex = pattern["SeriesDescription"]
            if isinstance(regex, list):
                regex = "|".join(regex)
            if re.search(regex, self.description, re.IGNORECASE):
                matches[tag] = pattern

        if len(matches) == 1 or (len(matches) == 2 and self.multiecho):
            self.tags = list(matches.keys())
            return matches
        return self._set_fmap_tag(tag_map, matches)

    def _set_fmap_tag(self, tag_map, matches):
        try:
            for tag, pattern in tag_map.items():
                if tag in matches:
                    if not re.search(pattern["ImageType"], self.image_type):
                        del matches[tag]
        except Exception:
            matches = {}

        if len(matches) > 2 or (len(matches) == 2 and not self.multiecho):
            matches = {}
        self.tags = list(matches.keys())
        return matches

    def set_datman_name(self, tag_map):
        mangled_descr = self._mangle_descr()
        padded_series = self.series.zfill(2)
        tag_settings = self.set_tag(tag_map)
        if not tag_settings:
            raise ExportException("Can't identify tag for series {}".format(
                                  self.series))
        names = []
        self.echo_dict = {}
        for tag in tag_settings:
            name = "_".join([self.experiment, tag, padded_series,
                             mangled_descr])
            if self.multiecho:
                echo_num = tag_settings[tag]["EchoNumber"]
                if echo_num not in self.echo_dict:
                    self.echo_dict[echo_num] = name
            names.append(name)

        self.names = names
        return names

    def _mangle_descr(self):
        if not self.description:
            return ""
        return re.sub(r"[^a-zA-Z0-9.+]+", "-", self.description)

    def __str__(self):
        return "<XNATSeries {} - {}>".format(self.experiment, self.series)

    def __repr__(self):
        return self.__str__()
