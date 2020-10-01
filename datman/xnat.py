"""Module to interact with the xnat server"""

import getpass
import json
import logging
import os
import re
import tempfile
import time
import urllib.parse
from abc import ABC
from xml.etree import ElementTree

import requests

from datman.exceptions import ExportException, UndefinedSetting, XnatException

logger = logging.getLogger(__name__)


def get_server(config=None, url=None, port=None):
    if not config and not url:
        raise XnatException(
            "Can't construct a valid server URL without a "
            "datman.config.config instance or string url"
        )

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
        logger.debug(
            f"XNATPORT undefined in config. Omitting port number for {url}"
        )
        port_str = ""

    # Will create a bad url if a port is appended after '/'
    if url.endswith("/"):
        url = url[:-1]

    server = f"{url}{port_str}"

    return server


def get_port_str(config=None, port=None):
    """
    Returns a port string of the format :portnum

    Will raise KeyError if port is None and config file doesn't define XNATPORT
    """
    if not config and not port:
        raise XnatException(
            "Can't construct port substring without a "
            "datman.config.config instance or a port number"
        )
    if port is None:
        port = config.get_key("XNATPORT")

    if not str(port).startswith(":"):
        port = f":{port}"

    return port


def get_auth(username=None, file_path=None):
    if username:
        return (username, getpass.getpass())

    if file_path:
        try:
            with open(file_path, "r") as cred_file:
                contents = cred_file.readlines()
        except Exception as e:
            raise XnatException(
                f"Failed to read credentials file {file_path}. " f"Reason - {e}"
            )
        try:
            username = contents[0].strip()
            password = contents[1].strip()
        except IndexError:
            raise XnatException(
                f"Failed to read credentials file {file_path} - "
                "incorrectly formatted."
            )
        return (username, password)

    try:
        username = os.environ["XNAT_USER"]
    except KeyError:
        raise KeyError("XNAT_USER not defined in environment")
    try:
        password = os.environ["XNAT_PASS"]
    except KeyError:
        raise KeyError("XNAT_PASS not defined in environment")

    return (username, password)


def get_connection(config, site=None, url=None, auth=None, server_cache=None):
    """Create (or retrieve) a connection to an XNAT server

    Args:
        config (:obj:`datman.config.config`): A study's configuration
        site (:obj:`str`, optional): A valid site for the current study. If
            given, site-specific settings will be searched for before
            defaulting to study or organization wide settings.
            Defaults to None.
        url (:obj:`str`, optional): An XNAT server URL. If given the
            configuration will NOT be consulted. Defaults to None.
        auth (:obj:`tuple`, optional): A (username, password) tuple. If given
            configuration / environment variables will NOT be consulted.
            Defaults to None.
        server_cache (:obj:`dict`, optional): A dictionary used to map URLs to
            open XNAT connections. If given, connections will be retrieved
            from the cache as needed or added if a new URL is requested.
            Defaults to None.

    Raises:
        XnatException: If a connection can't be made.

    Returns:
        :obj:`datman.xnat.xnat`: A connection to the required XNAT server.
    """
    if not url:
        url = config.get_key("XNATSERVER", site=site)

    if server_cache:
        try:
            return server_cache[url]
        except KeyError:
            pass

    server_url = get_server(url=url)

    if auth:
        connection = xnat(server_url, auth[0], auth[1])
    else:
        try:
            auth_file = config.get_key("XNAT_CREDENTIALS", site=site)
        except UndefinedSetting:
            auth_file = None
        else:
            if not os.path.exists(auth_file) and not os.path.dirname(auth_file):
                # User probably provided metadata file name only
                auth_file = os.path.join(config.get_path("meta"), auth_file)
        username, password = get_auth(file_path=auth_file)
        connection = xnat(server_url, username, password)

    if server_cache is not None:
        server_cache[url] = connection

    return connection


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
            raise XnatException(f"Failed to open session with server {server}")

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        # Ends the session on the server side
        url = f"{self.server}/data/JSESSION"
        self.session.delete(url)

    def open_session(self):
        """Open a session with the XNAT server."""

        url = f"{self.server}/data/JSESSION"

        s = requests.Session()

        response = s.post(url, auth=self.auth)

        if not response.status_code == requests.codes.ok:
            logger.warn(
                f"Failed connecting to xnat server {self.server} "
                f"with response code {response.status_code}"
            )
            logger.debug("Username: {}")
            response.raise_for_status()

        # Cookies are set automatically, don't manually set them or it wipes
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
            logger.debug(f"Narrowing search to {project}")

        url = f"{self.server}/data/archive/projects/{project}?format=json"

        try:
            result = self._make_xnat_query(url)
        except Exception:
            raise XnatException(
                f"Failed getting projects from server with search URL {url}"
            )

        if not result:
            logger.debug(f"No projects found on server {self.server}")
            return []

        if not project:
            return result["ResultSet"]["Result"]

        return result["items"]

    def find_project(self, subject_id, projects=None):
        """Find the project a subject belongs to.

        Args:
            subject_id (:obj:`str`): The subject to search for.
            projects (:obj:`list`, optional): A list of projects to restrict
                the search to. Defaults to None.

        Returns:
            str: The name of the XNAT project the subject belongs to. Note:
                if the same ID is found in more than one project only the
                first match is returned.
        """
        if not projects:
            projects = [p["ID"] for p in self.get_projects()]

        for project in projects:
            try:
                found_ids = self.get_subject_ids(project)
            except XnatException:
                continue
            if subject_id in found_ids:
                logger.debug(f"Found session {subject_id} in project {project}")
                return project

    def get_subject_ids(self, project):
        """Retrieve the IDs for all subjects within an XNAT project.

        Args:
            project (:obj:`str`): The 'Project ID' for a project on XNAT.

        Raises:
            XnatException: If the project does not exist or access fails.

        Returns:
            list: A list of string subject IDs found within the project.
        """
        logger.debug(
            f"Querying xnat server {self.server} for subjects in "
            f"project {project}"
        )

        if not self.get_projects(project):
            raise XnatException(f"Invalid XNAT project: {project}")

        url = f"{self.server}/data/archive/projects/{project}/subjects/"

        try:
            result = self._make_xnat_query(url)
        except Exception:
            raise XnatException(f"Failed getting xnat subjects with URL {url}")

        if not result:
            return []

        try:
            subids = [item["label"] for item in result["ResultSet"]["Result"]]
        except KeyError as e:
            raise XnatException(f"get_subject_ids - Malformed response. {e}")

        return subids

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
                the given subject ID.
        """
        logger.debug(f"Querying for subject {subject_id} in project {project}")

        url = (
            f"{self.server}/data/archive/projects/{project}/"
            f"subjects/{subject_id}?format=json"
        )

        try:
            result = self._make_xnat_query(url)
        except Exception:
            raise XnatException(
                f"Failed getting subject {subject_id} with URL {url}"
            )

        if not create and not result:
            raise XnatException(
                f"Subject {subject_id} does not exist for project {project}"
            )

        if not result:
            logger.info(f"Creating {subject_id} in project {project}")
            self.make_subject(project, subject_id)
            return self.get_subject(project, subject_id)

        try:
            subject_json = result["items"][0]
        except (IndexError, KeyError):
            raise XnatException(
                f"Could not access metadata for subject {subject_id}"
            )

        return XNATSubject(subject_json)

    def make_subject(self, project, subject):
        """Make a new (empty) subject on the XNAT server.

        Args:
            project (:obj:`str`): The 'Project ID' of an existing XNAT project.
            subject (:obj:`str`): The ID to create the new subject under.

        Raises:
            XnatException: If subject creation fails.
        """
        url = f"{self.server}/REST/projects/{project}/subjects/{subject}"

        try:
            self._make_xnat_put(url)
        except requests.exceptions.RequestException as e:
            raise XnatException(
                f"Failed to create xnat subject {subject} in project "
                f"{project}. Reason - {e}"
            )

    def find_subject(self, project, exper_id):
        """Find the parent subject ID for an experiment.

        Args:
            project (:obj:`str`): An XNAT project to search.
            exper_id (:obj:`str`): The experiment to find the parent ID for.

        Returns:
            str: The ID of the parent subject. Note that this returns the ID,
                not the label. The label and ID can be used interchangeably
                to query XNAT but the ID tends to not conform to any naming
                convention.
        """
        url = (
            f"{self.server}/data/archive/projects/{project}/"
            f"experiments/{exper_id}?format=json"
        )

        try:
            result = self._make_xnat_query(url)
        except Exception:
            XnatException(
                f"Failed to query XNAT server {project} for "
                f"experiment {exper_id}"
            )
        return result["items"][0]["data_fields"]["subject_ID"]

    def get_experiment_ids(self, project, subject=""):
        """Retrieve all experiment IDs belonging to an XNAT subject.

        Args:
            project (:obj:`str`): An XNAT project ID.
            subject (:obj:`str`, optional): An existing XNAT subject within
                'project' to restrict the search to. Defaults to ''.

        Raises:
            XnatException: If server/API access fails.

        Returns:
            list: A list of string experiment IDs belonging to 'subject'.
        """
        logger.debug(
            f"Querying XNAT server {self.server} for experiment IDs for "
            f"subject {subject} in project {project}"
        )

        if subject:
            subject = f"subjects/{subject}/"

        url = (
            f"{self.server}/data/projects/{project}/{subject}"
            "experiments/?format=json"
        )

        try:
            result = self._make_xnat_query(url)
        except Exception:
            raise XnatException(
                f"Failed getting experiment IDs for subject {subject}"
                f" with URL {url}"
            )

        if not result:
            return []

        return [item.get("label") for item in result["ResultSet"]["Result"]]

    def get_experiment(self, project, subject_id, exper_id, create=False):
        """Get an experiment from the XNAT server.

        Args:
            project (:obj:`str`): The XNAT project to search within.
            subject_id (:obj:`str`): The XNAT subject to search.
            exper_id (:obj:`str`): The name of the experiment to retrieve.
            create (bool, optional): Whether to create an experiment matching
                exper_id if a match is not found. Defaults to False.

        Raises:
            XnatException: If the experiment doesn't exist and can't be made
                or the server/API can't be accessed.

        Returns:
            :obj:`datman.xnat.XNATExperiment`: An XNATExperiment instance
                matching the given experiment ID.
        """
        logger.debug(
            f"Querying XNAT server {self.server} for experiment {exper_id} "
            f"belonging to {subject_id} in project {project}"
        )

        url = (
            f"{self.server}/data/archive/projects/{project}/subjects/"
            f"{subject_id}/experiments/{exper_id}?format=json"
        )

        try:
            result = self._make_xnat_query(url)
        except Exception:
            raise XnatException(f"Failed getting experiment with URL {url}")

        if not create and not result:
            raise XnatException(
                f"Experiment {exper_id} does not exist for subject "
                f"{subject_id} in project {project}"
            )

        if not result:
            logger.info(
                f"Creating experiment {exper_id} for subject_id {subject_id}"
            )
            self.make_experiment(project, subject_id, exper_id)
            return self.get_experiment(project, subject_id, exper_id)

        try:
            exper_json = result["items"][0]
        except (IndexError, KeyError):
            raise XnatException(
                f"Could not access metadata for experiment {exper_id}"
            )

        return XNATExperiment(project, subject_id, exper_json)

    def make_experiment(self, project, subject, experiment):
        """Make a new (empty) experiment on the XNAT server.

        Args:
            project (:obj:`str`): The 'Project ID' of an existing XNAT project.
            subject (:obj:`str`): The subject that should own the experiment.
            experiment (:obj:`str`):The ID to create the new experiment under.

        Raises:
            XnatException: If experiment creation fails.
        """

        url = (
            f"{self.server}/data/archive/projects/{project}/subjects/{subject}/"
            f"experiments/{experiment}?xsiType=xnat:mrSessionData"
        )
        try:
            self._make_xnat_put(url)
        except requests.exceptions.RequestException as e:
            raise XnatException(
                f"Failed to create XNAT experiment {experiment} under "
                f"subject {subject} in project {project}. Reason - {e}"
            )

    def get_scan_ids(self, project, subject, experiment):
        """Retrieve all scan IDs for an XNAT experiment.

        Args:
            project (:obj:`str`): An XNAT project ID.
            subject (:obj:`str`): An existing subject within 'project'.
            experiment (:obj:`str`): An existing experiment within 'subject'.

        Raises:
            XnatException: If server/API access fails.

        Returns:
            list: A list of scan IDs belonging to 'experiment'.
        """
        logger.debug(
            f"Querying XNAT server {self.server} for scan IDs belonging to "
            f"experiment {experiment} of subject {subject} in project {project}"
        )

        url = (
            f"{self.server}/data/archive/projects/{project}/subjects/{subject}/"
            f"experiments/{experiment}/scans/?format=json"
        )

        try:
            result = self._make_xnat_query(url)
        except Exception:
            raise XnatException(
                f"Failed getting scan IDs for experiment {experiment} with "
                f"URL {url}"
            )

        if not result:
            return []

        try:
            scan_ids = [
                item.get("ID") for item in result["ResultSet"]["Result"]
            ]
        except KeyError as e:
            raise XnatException(f"get_scan_ids - Malformed response. {e}")

        return scan_ids

    def get_scan(self, project, subject_id, exper_id, scan_id):
        """Get a scan from the XNAT server.

        Args:
            project (:obj:`str`): The XNAT project to search within.
            subject_id (:obj:`str`): The XNAT subject to search.
            exper_id (:obj:`str`): The XNAT experiment to search.
            scan_id (:obj:`str`): The ID of the scan to retrieve.

        Raises:
            XnatException: If the scan does not exist or the server/API can't
                be accessed.

        Returns:
            :obj:`datman.xnat.XNATScan`: An XNATScan instance matching the
                scan ID from the given experiment.
        """
        logger.debug(
            f"Querying XNAT server {self.server} for scan {scan_id} in "
            f"experiment {exper_id} belonging to subject {subject_id} in "
            f"project {project}"
        )

        url = (
            f"{self.server}/data/archive/projects/{project}/subject_ids/"
            f"{subject_id}/exper_ids/{exper_id}/scans/{scan_id}/?format=json"
        )

        try:
            result = self._make_xnat_query(url)
        except Exception:
            raise XnatException(f"Failed getting scan with URL {url}")

        if not result:
            raise XnatException(
                f"Scan {scan_id} does not exist for experiment {exper_id} "
                f"in project {project}"
            )

        try:
            scan_json = result["items"][0]
        except (IndexError, KeyError):
            raise XnatException(f"Could not access metadata for scan {scan_id}")

        return XNATScan(project, subject_id, exper_id, scan_json)

    def get_resource_ids(
        self, study, session, experiment, folderName=None, create=True
    ):
        """
        Return a list of resource id's (subfolders) from an experiment
        """
        logger.debug(f"Getting resource ids for experiment: {experiment}")
        url = (
            f"{self.server}/data/archive/projects/{study}"
            f"/subjects/{session}/experiments/{experiment}"
            "/resources/?format=json"
        )
        try:
            result = self._make_xnat_query(url)
        except Exception:
            raise XnatException(f"Failed getting resource ids with url: {url}")
        if result is None:
            raise XnatException(
                f"Experiment: {experiment} not found for session: {session}"
                f" in study: {study}"
            )

        if create and int(result["ResultSet"]["totalRecords"]) < 1:
            return self.create_resource_folder(
                study, session, experiment, folderName
            )

        resource_ids = {}
        for r in result["ResultSet"]["Result"]:
            label = r.get("label", "No Label")
            resource_ids[label] = r["xnat_abstractresource_id"]

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
                    resource_id = self.create_resource_folder(
                        study, session, experiment, folderName
                    )

        return resource_id

    def create_resource_folder(self, study, session, experiment, label):
        """
        Creates a resource subfolder and returns the xnat identifier.
        """
        url = (
            f"{self.server}/data/archive/projects/{study}"
            f"/subjects/{session}/experiments/{experiment}"
            f"/resources/{label}/"
        )
        self._make_xnat_put(url)
        return self.get_resource_ids(study, session, experiment, label)

    def get_resource_list(self, study, session, experiment, resource_id):
        """The list of non-dicom resources associated with an experiment
        returns a list of dicts, mostly interested in ID and name"""
        logger.debug(f"Getting resource list for experiment: {experiment}")
        url = (
            f"{self.server}/data/archive/projects/{study}"
            f"/subjects/{session}/experiments/{experiment}"
            f"/resources/{resource_id}/?format=xml"
        )
        try:
            result = self._make_xnat_xml_query(url)
        except Exception:
            raise XnatException(f"Failed getting resources with url: {url}")
        if result is None:
            raise XnatException(
                f"Experiment: {experiment} not found for session: {session}"
                f" in study: {study}"
            )

        # define the xml namespace
        ns = {"cat": "http://nrg.wustl.edu/catalog"}
        entries = result.find("cat:entries", ns)
        if entries is None:
            # no files found, just a label
            return []

        items = [entry.attrib for entry in entries.findall("cat:entry", ns)]

        return items

    def put_dicoms(self, project, subject, experiment, filename, retries=3):
        """Upload an archive of dicoms to XNAT
        filename: archive to upload"""
        headers = {"Content-Type": "application/zip"}

        upload_url = (
            f"{self.server}/data/services/import?project={project}"
            f"&subject={subject}&session={experiment}&overwrite=delete"
            "&prearchive=false&inbody=true"
        )

        try:
            with open(filename, "rb") as data:
                self._make_xnat_post(upload_url, data, retries, headers)
        except XnatException as e:
            e.study = project
            e.session = experiment
            raise e
        except IOError as e:
            logger.error(
                f"Failed to open file: {filename} with excuse: {e.strerror}"
            )
            err = XnatException(f"Error in file: {filename}")
            err.study = project
            err.session = experiment
            raise err
        except requests.exceptions.RequestException:
            err = XnatException(f"Error uploading data with url: {upload_url}")
            err.study = project
            err.session = experiment
            raise err

    def get_dicom(
        self, project, session, experiment, scan, filename=None, retries=3
    ):
        """Downloads a dicom file from xnat to filename
        If filename is not specified creates a temporary file
        and returns the path to that, user needs to be responsible
        for cleaning up any created tempfiles"""
        url = (
            f"{self.server}/data/archive/projects/{project}/"
            f"subjects/{session}/experiments/{experiment}/"
            f"scans/{scan}/resources/DICOM/files?format=zip"
        )

        if not filename:
            filename = tempfile.mkstemp(prefix="dm2_xnat_extract_")
            # mkstemp returns a filename and a file object
            # dealing with the filename in future so close the file object
            os.close(filename[0])
            filename = filename[1]
        try:
            self._get_xnat_stream(url, filename, retries)
            return filename
        except Exception:
            try:
                os.remove(filename)
            except OSError as e:
                logger.warning(
                    f"Failed to delete tempfile: {filename} with "
                    f"excuse: {str(e)}"
                )
            err = XnatException(f"Failed getting dicom with url: {url}")
            err.study = project
            err.session = session
            raise err

    def put_resource(
        self, project, subject, experiment, filename, data, folder, retries=3
    ):
        """
        POST a resource file to the xnat server

        Args:
            filename: string to store filename as
            data: string containing data
                (such as produced by zipfile.ZipFile.read())

        """

        try:
            self.get_experiment(project, subject, experiment)
        except XnatException:
            logger.warning(
                f"Experiment: {experiment} in subject: {subject} does not "
                "exist! Making new experiment"
            )
            self.make_experiment(project, subject, experiment)

        resource_id = self.get_resource_ids(
            project, subject, experiment, folderName=folder
        )

        uploadname = urllib.parse.quote(filename)

        attach_url = (
            f"{self.server}/data/archive/projects/{project}/"
            f"subjects/{subject}/experiments/{experiment}/"
            f"resources/{resource_id}/"
            f"files/{uploadname}?inbody=true"
        )

        try:
            self._make_xnat_post(attach_url, data)
        except XnatException as err:
            err.study = project
            err.session = experiment
            raise err
        except Exception:
            logger.warning(
                f"Failed adding resource to xnat with url: {attach_url}"
            )
            err = XnatException("Failed adding resource to xnat")
            err.study = project
            err.session = experiment

    def get_resource(
        self,
        project,
        session,
        experiment,
        resource_group_id,
        resource_id,
        filename=None,
        retries=3,
        zipped=True,
    ):
        """Download a single resource from xnat to filename
        If filename is not specified creates a temporary file and
        returns the path to that, user needs to be responsible for
        cleaning up any created tempfiles"""

        url = (
            f"{self.server}/data/archive/projects/{project}/"
            f"subjects/{session}/experiments/{experiment}/"
            f"resources/{resource_group_id}/files/{resource_id}"
        )
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
            return filename
        except Exception:
            try:
                os.remove(filename)
            except OSError as e:
                logger.warning(
                    f"Failed to delete tempfile: {filename} with "
                    f"exclude: {str(e)}"
                )
            logger.error("Failed getting resource from xnat", exc_info=True)
            raise XnatException(f"Failed downloading resource with url: {url}")

    def get_resource_archive(
        self,
        project,
        session,
        experiment,
        resource_id,
        filename=None,
        retries=3,
    ):
        """Download a resource archive from xnat to filename
        If filename is not specified creates a temporary file and
        returns the path to that, user needs to be responsible format
        cleaning up any created tempfiles"""
        url = (
            f"{self.server}/data/archive/projects/{project}/"
            f"subjects/{session}/experiments/{experiment}/"
            f"resources/{resource_id}/files?format=zip"
        )

        if not filename:
            filename = tempfile.mkstemp(prefix="dm2_xnat_extract_")
            # mkstemp returns a file object and a filename we will deal
            # with the filename in future so close the file object
            os.close(filename[0])
            filename = filename[1]
        try:
            self._get_xnat_stream(url, filename, retries)
            return filename
        except Exception:
            try:
                os.remove(filename)
            except OSError as e:
                logger.warning(
                    f"Failed to delete tempfile: {filename} with "
                    f"error: {str(e)}"
                )
            logger.error(
                "Failed getting resource archive from xnat", exc_info=True
            )
            raise XnatException(
                f"Failed downloading resource archive with url: {url}"
            )

    def delete_resource(
        self,
        project,
        session,
        experiment,
        resource_group_id,
        resource_id,
        retries=3,
    ):
        """Delete a resource file from xnat"""
        url = (
            f"{self.server}/data/archive/projects/{project}/"
            f"subjects/{session}/experiments/{experiment}/"
            f"resources/{resource_group_id}/files/{resource_id}"
        )
        try:
            self._make_xnat_delete(url)
        except Exception:
            raise XnatException(f"Failed deleting resource with url: {url}")

    def rename_subject(self, project, old_name, new_name, rename_exp=False):
        """Change a subjects's name on XNAT.

        Args:
            project (:obj:`str`): The name of the XNAT project that the subject
                belongs to.
            old_name (:obj:`str`): The current name on XNAT of the subject to
                be renamed.
            new_name (:obj:`str`): The new name to apply.
            rename_exp (bool, optional): Also change the experiment name to
                the new subject name. Obviously, this should NOT be used when
                subjects and experiments are meant to use different naming
                conventions. Defaults to False.

        Raises:
            XnatException: If unable to rename the subject (or the experiment
                if rename_exp=True) because:
                    1) The subject doesn't exist.
                    2) A stuck AutoRun.xml pipeline can't be dismissed
                    3) A subject exists under the 'new_name' already
            requests.HTTPError: If any unexpected behavior is experienced while
                interacting with XNAT's API
        """
        # Ensures subject exists, and raises an exception if not
        self.get_subject(project, old_name)

        url = (
            f"{self.server}/data/archive/projects/{project}/subjects/"
            f"{old_name}?xsiType=xnat:mrSessionData&label={new_name}"
        )
        try:
            self._make_xnat_put(url)
        except requests.HTTPError as e:
            if e.response.status_code == 409:
                raise XnatException(
                    f"Can't rename {old_name} to {new_name}."
                    "Subject already exists"
                )
            elif e.response.status_code == 422:
                # This is raised every time a subject is renamed.
                pass
            else:
                raise e

        if rename_exp:
            self.rename_experiment(project, new_name, old_name, new_name)

        return

    def rename_experiment(self, project, subject, old_name, new_name):
        """Change an experiment's name on XNAT.

        Args:
            project (:obj:`str`): The name of the project the experiment
                can be found in.
            subject (:obj:`str`): The ID of the subject this experiment
                belongs to.
            old_name (:obj:`str`): The current experiment name.
            new_name (:obj:`str`): The new name to give the experiment.

        Raises:
            XnatException: If unable to rename the experiment because:
                1) The experiment doesnt exist
                2) A stuck AutoRun.xml pipeline can't be dismissed
                3) An experiment exists under 'new_name' already
            requests.HTTPError: If any unexpected behavior is experienced while
                interacting with XNAT's API
        """
        experiment = self.get_experiment(project, subject, old_name)

        try:
            self.dismiss_autorun(experiment)
        except XnatException as e:
            logger.error(
                f"Failed to dismiss AutoRun.xml pipeline for {old_name}, "
                f"experiment rename may fail. Error - {e}"
            )

        experiments = self.get_experiment_ids(project, subject)
        if new_name in experiments:
            raise XnatException(
                f"Can't rename experiment {old_name} to {new_name}."
                "ID already in use."
            )

        url = (
            f"{self.server}/data/archive/projects/{project}/subjects/{subject}"
            f"/experiments/{old_name}?xsiType="
            f"xnat:mrSessionData&label={new_name}"
        )

        try:
            self._make_xnat_put(url)
        except requests.HTTPError as e:
            if e.response.status_code == 409:
                # A 409 when renaming a subject is a real problem, but a 409
                # always happens when an experiment rename succeeds. I have
                # no idea why XNAT works this way.
                pass
            else:
                raise e

    def dismiss_autorun(self, experiment):
        """Mark the AutoRun.xml pipeline as finished.

        AutoRun.xml gets stuck as 'Queued' and can cause failures at renaming
        and deletion. This marks the pipeline as 'Complete' to prevent it from
        interfering.

        Args:
            subject (:obj:`datman.xnat.XNATExperiment`): An XNAT experiment to
                dismiss the pipeline for.
        """
        autorun_ids = experiment.get_autorun_ids(self)

        for autorun in autorun_ids:
            dismiss_url = (
                f"{self.server}/data/workflows/{autorun}"
                "?wrk:workflowData/status=Complete"
            )
            self._make_xnat_put(dismiss_url)

    def _get_xnat_stream(self, url, filename, retries=3, timeout=120):
        logger.debug(f"Getting {url} from XNAT")
        try:
            response = self.session.get(url, stream=True, timeout=timeout)
        except requests.exceptions.Timeout as e:
            if retries > 0:
                return self._get_xnat_stream(
                    url, filename, retries=retries - 1, timeout=timeout * 2
                )
            else:
                raise e

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info("Session may have expired, resetting")
            self.open_session()
            response = self.session.get(url, stream=True, timeout=timeout)

        if response.status_code == 404:
            logger.info(
                f"No records returned from xnat server for query: {url}"
            )
            return
        elif response.status_code == 504:
            if retries:
                logger.warning("xnat server timed out, retrying")
                time.sleep(30)
                self._get_xnat_stream(
                    url, filename, retries=retries - 1, timeout=timeout * 2
                )
            else:
                logger.error("xnat server timed out, giving up")
                response.raise_for_status()
        elif response.status_code != 200:
            logger.error(f"xnat error: {response.status_code} at data upload")
            response.raise_for_status()

        with open(filename, "wb") as f:
            try:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            except requests.exceptions.RequestException as e:
                logger.error("Failed reading from xnat")
                raise (e)
            except IOError as e:
                logger.error("Failed writing to file")
                raise (e)

    def _make_xnat_query(self, url, retries=3):
        try:
            response = self.session.get(url, timeout=30)
        except requests.exceptions.Timeout as e:
            if retries > 0:
                return self._make_xnat_query(url, retries=retries - 1)
            else:
                logger.error(f"Xnat server timed out getting url {url}")
                raise e

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info("Session may have expired, resetting")
            self.open_session()
            response = self.session.get(url, timeout=30)

        if response.status_code == 404:
            logger.info(
                f"No records returned from xnat server for query: {url}"
            )
            return
        elif not response.status_code == requests.codes.ok:
            logger.error(
                f"Failed connecting to xnat server {self.server} "
                f"with response code {response.status_code}"
            )
            logger.debug("Username: {}")
            response.raise_for_status()
        return response.json()

    def _make_xnat_xml_query(self, url, retries=3):
        try:
            response = self.session.get(url, timeout=30)
        except requests.exceptions.Timeout as e:
            if retries > 0:
                return self._make_xnat_xml_query(url, retries=retries - 1)
            else:
                raise e

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info("Session may have expired, resetting")
            self.open_session()
            response = self.session.get(url, timeout=30)

        if response.status_code == 404:
            logger.info(f"No records returned from xnat server to query {url}")
            return
        elif not response.status_code == requests.codes.ok:
            logger.error(
                f"Failed connecting to xnat server {self.server}"
                f" with response code {response.status_code}"
            )
            logger.debug("Username: {}")
            response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        return root

    def _make_xnat_put(self, url, retries=3):
        if retries == 0:
            logger.info(f"Timed out making xnat put {url}")
            requests.exceptions.HTTPError()

        try:
            response = self.session.put(url, timeout=30)
        except requests.exceptions.Timeout:
            return self._make_xnat_put(url, retries=retries - 1)

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info("Session may have expired, resetting")
            self.open_session()
            response = self.session.put(url, timeout=30)

        if response.status_code not in [200, 201]:
            logger.warn(
                f"http client error at folder creation: {response.status_code}"
            )
            response.raise_for_status()

    def _make_xnat_post(self, url, data, retries=3, headers=None):
        logger.debug(f"POSTing data to xnat, {retries} retries left")
        response = self.session.post(
            url, headers=headers, data=data, timeout=60 * 60
        )

        reply = str(response.content)

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info("Session may have expired, resetting")
            self.open_session()
            response = self.session.post(url, headers=headers, data=data)

        if response.status_code == 504:
            if retries:
                logger.warning("xnat server timed out, retrying")
                time.sleep(30)
                self._make_xnat_post(url, data, retries=retries - 1)
            else:
                logger.warn("xnat server timed out, giving up")
                response.raise_for_status()

        elif response.status_code != 200:
            if "multiple imaging sessions." in reply:
                raise XnatException("Multiple imaging sessions in archive,"
                                    " check prearchive")
            if "502 Bad Gateway" in reply:
                raise XnatException("Bad gateway error: Check tomcat logs")
            if "Unable to identify experiment" in reply:
                raise XnatException("Unable to identify experiment, did "
                                    "dicom upload fail?")
            else:
                raise XnatException("An unknown error occured uploading data."
                                    f"Status code: {response.status_code}, "
                                    f"reason: {reply}")
        return reply

    def _make_xnat_delete(self, url, retries=3):
        try:
            response = self.session.delete(url, timeout=30)
        except requests.exceptions.Timeout:
            return self._make_xnat_delete(url, retries=retries - 1)

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info("Session may have expired, resetting")
            self.open_session()
            response = self.session.delete(url, timeout=30)

        if response.status_code not in [200, 201]:
            logger.warn(
                f"http client error deleting resource: {response.status_code}"
            )
            response.raise_for_status()

    def __str__(self):
        return f"<datman.xnat.xnat {self.server}>"

    def __repr__(self):
        return self.__str__()


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
        experiments = [
            exp
            for exp in self.raw_json["children"]
            if exp["field"] == "experiments/experiment"
        ]

        if not experiments:
            logger.debug(f"No experiments found for {self.name}")
            return {}

        found = {}
        for item in experiments[0]["items"]:
            exper = XNATExperiment(self.project, self.name, item)
            found[exper.name] = exper

        return found

    def __str__(self):
        return f"<XNATSubject {self.name}>"

    def __repr__(self):
        return self.__str__()


class XNATExperiment(XNATObject):
    def __init__(self, project, subject_name, experiment_json):
        self.raw_json = experiment_json
        self.project = project
        self.subject = subject_name
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

        contents = [
            child["items"] for child in children if child["field"] == data_type
        ]
        return contents

    def _get_scans(self):
        scans = self._get_contents("scans/scan")
        if not scans:
            logger.debug(f"No scans found for experiment {self.name}")
            return scans
        xnat_scans = []
        for scan_json in scans[0]:
            xnat_scans.append(
                XNATScan(self.project, self.subject, self.name, scan_json)
            )
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
            resource_ids[label] = str(
                resource["data_fields"]["xnat_abstractresource_id"]
            )
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
                        # Some entries don't have labels. Only hold some header
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
                    if label != "DICOM" and (
                        data_format != "DICOM" and label != "SNAPSHOTS"
                    ):
                        r_ids.append(r_id)
        return r_ids

    def get_autorun_ids(self, xnat):
        """Find the ID(s) of the 'autorun.xml' workflow

        XNAT has this obnoxious, on-by-default and seemingly impossible to
        disable, 'workflow' called AutoRun.xml. It appears to do nothing other
        than prevent certain actions (like renaming subjects/experiments) if
        it is stuck in the running or queued state. This will grab the autorun
        ID for this experiment so that it can be modified.

        Sometimes more than one pipeline gets launched for a subject even
        though the GUI only reports one. This will grab the ID for all of them.

        Returns:
            list: A list of string reference IDs that can be used to change
                the status of the pipeline for this subject using XNAT's API,
                or the empty string if the pipeline is not found.

        Raises:
            XnatException: If no AutoRun.xml pipeline instance is found or
                the API response can't be parsed.
        """
        query_xml = """
            <xdat:bundle
                    xmlns:xdat="http://nrg.wustl.edu/security"
                    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                    ID="@wrk:workflowData"
                    brief-description=""
                    description=""
                    allow-diff-columns="0"
                    secure="false">
                <xdat:root_element_name>wrk:workflowData</xdat:root_element_name>
                <xdat:search_field>
                    <xdat:element_name>wrk:workflowData</xdat:element_name>
                    <xdat:field_ID>pipeline_name</xdat:field_ID>
                    <xdat:sequence>0</xdat:sequence>
                    <xdat:type>string</xdat:type>
                    <xdat:header>wrk:workflowData/pipeline_name</xdat:header>
                </xdat:search_field>
                <xdat:search_field>
                    <xdat:element_name>wrk:workflowData</xdat:element_name>
                    <xdat:field_ID>wrk_workflowData_id</xdat:field_ID>
                    <xdat:sequence>1</xdat:sequence>
                    <xdat:type>string</xdat:type>
                    <xdat:header>wrk:workflowData/wrk_workflowData_id</xdat:header>
                </xdat:search_field>
                <xdat:search_where method="AND">
                    <xdat:criteria override_value_formatting="0">
                        <xdat:schema_field>wrk:workflowData/ID</xdat:schema_field>
                        <xdat:comparison_type>LIKE</xdat:comparison_type>
                        <xdat:value>{exp_id}</xdat:value>
                    </xdat:criteria>
                    <xdat:criteria override_value_formatting="0">
                        <xdat:schema_field>wrk:workflowData/ExternalID</xdat:schema_field>
                        <xdat:comparison_type>=</xdat:comparison_type>
                        <xdat:value>{project}</xdat:value>
                    </xdat:criteria>
                    <xdat:criteria override_value_formatting="0">
                        <xdat:schema_field>wrk:workflowData/pipeline_name</xdat:schema_field>
                        <xdat:comparison_type>=</xdat:comparison_type>
                        <xdat:value>xnat_tools/AutoRun.xml</xdat:value>
                    </xdat:criteria>
                </xdat:search_where>
            </xdat:bundle>
        """.format(
            exp_id=self.id, project=self.project
        )  # noqa: E501

        query_url = f"{xnat.server}/data/search?format=json"
        response = xnat._make_xnat_post(query_url, data=query_xml)

        if not response:
            raise XnatException("AutoRun.xml pipeline not found.")

        try:
            found_pipelines = json.loads(response)
        except json.JSONDecodeError:
            raise XnatException("Can't decode workflow query response.")

        try:
            results = found_pipelines["ResultSet"]["Result"]
        except KeyError:
            return []

        wf_ids = [item.get("workflow_id") for item in results]

        return wf_ids

    def get_resources(self, xnat_connection):
        """
        Returns a list of all resource URIs from this session.
        """
        resources = []
        resource_ids = list(self.resource_IDs.values())
        resource_ids.extend(self.misc_resource_IDs)
        for r_id in resource_ids:
            resource_list = xnat_connection.get_resource_list(
                self.project, self.subject, self.name, r_id
            )
            resources.extend([item["URI"] for item in resource_list])
        return resources

    def download(self, xnat, dest_folder, zip_name=None):
        """
        Download a zip file containing all data for this session. Returns the
        path to the new file if download is successful, raises an exception if
        not

        Args:
            xnat: An instance of datman.xnat.xnat()
            dest_folder: The absolute path to the folder where the zip
                should be deposited
            zip_name: An optional name for the output zip file. If not
                set the zip name will be session.name

        """
        if not self.experiment:
            raise ValueError(f"No data found for {self.name}")

        resources_list = list(self.scan_resource_IDs)
        resources_list.extend(self.misc_resource_IDs)
        resources_list.extend(self.resource_IDs)

        if not resources_list:
            raise ValueError(f"No scans or resources found for {self.name}")

        url = (
            f"{xnat.server}/REST/experiments/{self.id}/resources/"
            f"{','.join(resources_list)}/files?structure=improved"
            "&all=true&format=zip"
        )

        if not zip_name:
            zip_name = self.name.upper() + ".zip"

        output_path = os.path.join(dest_folder, zip_name)
        if os.path.exists(output_path):
            logger.error(f"Cannot download {output_path}, file already exists.")
            return output_path

        xnat._get_xnat_stream(url, output_path)

        return output_path

    def __str__(self):
        return f"<XNATExperiment {self.name}>"

    def __repr__(self):
        return self.__str__()


class XNATScan(XNATObject):
    def __init__(self, project, subject_name, experiment_name, scan_json):
        self.raw_json = scan_json
        self.project = project
        self.subject = subject_name
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
            logger.warning(
                f"Image type could not be found for series {self.series}. "
                "Assuming it's derived."
            )
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

    def set_datman_name(self, base_name, tag_map):
        mangled_descr = self._mangle_descr()
        padded_series = self.series.zfill(2)
        tag_settings = self.set_tag(tag_map)
        if not tag_settings:
            raise ExportException(
                f"Can't identify tag for series {self.series}"
            )
        names = []
        self.echo_dict = {}
        for tag in tag_settings:
            name = "_".join([base_name, tag, padded_series, mangled_descr])
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
        return f"<XNATScan {self.experiment} - {self.series}>"

    def __repr__(self):
        return self.__str__()
