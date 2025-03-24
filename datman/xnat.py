"""Module to interact with the xnat server"""

import getpass
import logging
import os
import tempfile
import time
import urllib.parse
from xml.etree import ElementTree

import requests

from datman.exceptions import UndefinedSetting, XnatException, InputException
from datman.importers import XNATSubject, XNATExperiment


logger = logging.getLogger(__name__)


def get_server(config: 'datman.config.config' = None,
               url: str = None,
               port: str = None):
    """Get correctly formatted XNAT server URL.

    Args:
        config (:obj:`datman.config.config`, optional): A datman configuration
            object. Must be provided if url argument is not given.
        url (:obj:`str`, optional): A server url to use (and possibly
            re-adjust). Must be provided if config argument is not given.
        port (:obj:`str`, optional): A string representation of a port to use
            instead of traditional http/https ports.

    Returns:
        str: A server url of the expected format.
    """
    if not config and not url:
        raise XnatException("Can't construct a valid server URL without a "
                            "datman.config.config instance or string url")

    if url and not port:
        # Avoid mangling user's url by appending a port from the config
        use_port = False
    else:
        use_port = True

    if not url:
        url = config.get_key("XnatServer")

    # Check for 'http' and NOT https, because checking for https could mangle a
    # url into https://http<restof>
    if not url.startswith("http"):
        url = "https://" + url

    if not use_port:
        return url

    try:
        port_str = get_port_str(config, port)
    except UndefinedSetting:
        logger.debug(
            f"XnatPort undefined in config. Omitting port number for {url}")
        port_str = ""

    # Will create a bad url if a port is appended after '/'
    if url.endswith("/"):
        url = url[:-1]

    server = f"{url}{port_str}"

    return server


def get_port_str(config=None, port=None):
    """
    Returns a port string of the format :portnum

    Will raise KeyError if port is None and config file doesn't define XnatPort
    """
    if not config and not port:
        raise XnatException("Can't construct port substring without a "
                            "datman.config.config instance or a port number")
    if port is None:
        port = config.get_key("XnatPort")

    if not str(port).startswith(":"):
        port = f":{port}"

    return port


def get_auth(username=None, file_path=None):
    """Retrieve username and password for XNAT.

    If no inputs are given then the environment variables XNAT_USER and
    XNAT_PASS will be used.

    Args:
        username (:obj:`str`, optional): A username to use. If given, the
            user will be prompted for a password.
        file_path (:obj:`str`, optional): A path to a credentials file.

    Returns:
        tuple(str, str): A tuple containing a username and password.
    """
    if username:
        return (username, getpass.getpass())

    if file_path:
        try:
            with open(file_path, "r", encoding="utf-8") as cred_file:
                contents = cred_file.readlines()
        except Exception as e:
            raise XnatException(
                f"Failed to read credentials file {file_path}. "
                f"Reason - {e}") from e
        try:
            username = contents[0].strip()
            password = contents[1].strip()
        except IndexError as e:
            raise XnatException(
                f"Failed to read credentials file {file_path} - "
                "incorrectly formatted.") from e
        return (username, password)

    try:
        username = os.environ["XNAT_USER"]
    except KeyError:
        raise KeyError("XNAT_USER not defined in environment") from None
    try:
        password = os.environ["XNAT_PASS"]
    except KeyError:
        raise KeyError("XNAT_PASS not defined in environment") from None

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
        url = config.get_key("XnatServer", site=site)

    if server_cache:
        try:
            return server_cache[url]
        except KeyError:
            pass

    server_url = get_server(url=url)

    if auth:
        connection = XNAT(server_url, auth[0], auth[1])
    else:
        try:
            auth_file = config.get_key("XnatCredentials", site=site)
        except UndefinedSetting:
            auth_file = None
        else:
            if not os.path.exists(auth_file) and not os.path.dirname(
                    auth_file):
                # User probably provided metadata file name only
                auth_file = os.path.join(config.get_path("meta"), auth_file)
        username, password = get_auth(file_path=auth_file)
        connection = XNAT(server_url, username, password)

    if server_cache is not None:
        server_cache[url] = connection

    return connection


# pylint: disable-next=too-many-public-methods
class XNAT:
    """Manage a connection to an XNAT server.
    """

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
        except Exception as e:
            raise XnatException(
                f"Failed to open session with server {server}. Reason - {e}"
                ) from e

    def __enter__(self):
        return self

    def __exit__(self, *args):
        # Ends the session on the server side
        url = f"{self.server}/data/JSESSION"
        self.session.delete(url)

    def open_session(self):
        """Open a session with the XNAT server."""

        url = f"{self.server}/data/JSESSION"

        s = requests.Session()

        response = s.post(url, auth=self.auth)

        if response.status_code != 200:
            logger.warning(f"Failed connecting to xnat server {self.server} "
                           f"with response code {response.status_code}")
            logger.debug(f"Username: {self.auth[0]}")
            response.raise_for_status()

        # If password is expired, XNAT returns status 200 and a sea of
        # HTML causing later, unexpected, exceptions when using
        # the connection. So! Check to see if we got HTML instead of a token.
        if '<html' in response.text:
            raise XnatException(
                f"Password for user {self.auth[0]} on server {self.server} "
                "has expired. Please update it."
            )

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
        except Exception as e:
            raise XnatException(
                f"Failed getting projects from server with search URL {url}"
                ) from e

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
            str or None: The name of the XNAT project the subject belongs to.
                Note: if the same ID is found in more than one project only the
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
                logger.debug(
                    f"Found session {subject_id} in project {project}")
                return project
        return None

    def get_subject_ids(self, project):
        """Retrieve the IDs for all subjects within an XNAT project.

        Args:
            project (:obj:`str`): The 'Project ID' for a project on XNAT.

        Raises:
            XnatException: If the project does not exist or access fails.

        Returns:
            list: A list of string subject IDs found within the project.
        """
        logger.debug(f"Querying xnat server {self.server} for subjects in "
                     f"project {project}")

        if not self.get_projects(project):
            raise XnatException(f"Invalid XNAT project: {project}")

        url = f"{self.server}/data/archive/projects/{project}/subjects/"

        try:
            result = self._make_xnat_query(url)
        except Exception as e:
            raise XnatException(f"Failed getting xnat subjects with URL {url}"
                                ) from e

        if not result:
            return []

        try:
            subids = [item["label"] for item in result["ResultSet"]["Result"]]
        except KeyError as e:
            raise XnatException(f"get_subject_ids - Malformed response. {e}"
                                ) from None

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

        url = (f"{self.server}/data/archive/projects/{project}/"
               f"subjects/{subject_id}?format=json")

        try:
            result = self._make_xnat_query(url)
        except Exception as e:
            raise XnatException(
                f"Failed getting subject {subject_id} with URL {url}"
                ) from e

        if not create and not result:
            raise XnatException(
                f"Subject {subject_id} does not exist for project {project}")

        if not result:
            logger.info(f"Creating {subject_id} in project {project}")
            self.make_subject(project, subject_id)
            return self.get_subject(project, subject_id)

        try:
            subject_json = result["items"][0]
        except (IndexError, KeyError) as e:
            raise XnatException(
                f"Could not access metadata for subject {subject_id}") from e

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
                f"{project}. Reason - {e}") from e

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
        url = (f"{self.server}/data/archive/projects/{project}/"
               f"experiments/{exper_id}?format=json")

        try:
            result = self._make_xnat_query(url)
        except Exception as e:
            raise XnatException(f"Failed to query XNAT server {project} for "
                                f"experiment {exper_id}") from e
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
            f"subject {subject} in project {project}")

        if subject:
            subject = f"subjects/{subject}/"

        url = (f"{self.server}/data/projects/{project}/{subject}"
               "experiments/?format=json")

        try:
            result = self._make_xnat_query(url)
        except Exception as e:
            raise XnatException(
                f"Failed getting experiment IDs for subject {subject}"
                f" with URL {url}") from e

        if not result:
            return []

        return [item.get("label") for item in result["ResultSet"]["Result"]]

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def get_experiment(self, project, subject_id=None, exper_id=None,
                       create=False, ident=None):
        """Get an experiment from the XNAT server.

        Args:
            project (:obj:`str`): The XNAT project to search within.
            subject_id (:obj:`str`, optional): The XNAT subject to search.
                Either subject_id and exper_id must both be provided or
                ident must be given.
            exper_id (:obj:`str`, optional): The name of the experiment
                to retrieve. Either subject_id and exper_id must both be
                provided or ident must be given.
            create (bool, optional): Whether to create an experiment matching
                exper_id if a match is not found. Defaults to False.
            ident (:obj:`datman.scanid.Identifier`, optional): a datman
                identifier. Must be provided if subject_id and exper_id are
                not given.

        Raises:
            XnatException: If the experiment doesn't exist and can't be made
                or the server/API can't be accessed.
            InputException: If not given both subject_id and exper_id OR
                ident as arguments.

        Returns:
            :obj:`datman.xnat.XNATExperiment`: An XNATExperiment instance
                matching the given experiment ID.
        """
        if not (subject_id and exper_id):
            if not ident:
                raise InputException(
                    "Must be given either 1) subject ID and "
                    "experiment ID or 2) A datman.scanid.Identifier")
            subject_id = ident.get_xnat_subject_id()
            exper_id = ident.get_xnat_experiment_id()
        logger.debug(
            f"Querying XNAT server {self.server} for experiment {exper_id} "
            f"belonging to {subject_id} in project {project}")

        url = (f"{self.server}/data/archive/projects/{project}/subjects/"
               f"{subject_id}/experiments/{exper_id}?format=json")

        try:
            result = self._make_xnat_query(url)
        except Exception as e:
            raise XnatException(f"Failed getting experiment with URL {url}"
                                ) from e

        if not create and not result:
            raise XnatException(
                f"Experiment {exper_id} does not exist for subject "
                f"{subject_id} in project {project}")

        if not result:
            logger.info(
                f"Creating experiment {exper_id} for subject_id {subject_id}")
            self.make_experiment(project, subject_id, exper_id)
            return self.get_experiment(project, subject_id, exper_id)

        try:
            exper_json = result["items"][0]
        except (IndexError, KeyError) as e:
            raise XnatException(
                f"Could not access metadata for experiment {exper_id}") from e

        return XNATExperiment(project, subject_id, exper_json, ident=ident)

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
            f"{self.server}/data/archive/projects/{project}/subjects/"
            f"{subject}/experiments/{experiment}?xsiType=xnat:mrSessionData")
        try:
            self._make_xnat_put(url)
        except requests.exceptions.RequestException as e:
            raise XnatException(
                f"Failed to create XNAT experiment {experiment} under "
                f"subject {subject} in project {project}. Reason - {e}") from e

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
            f"experiment {experiment} of subject {subject} in project "
            f"{project}"
        )

        url = (
            f"{self.server}/data/archive/projects/{project}/subjects/"
            f"{subject}/experiments/{experiment}/scans/?format=json")

        try:
            result = self._make_xnat_query(url)
        except Exception as e:
            raise XnatException(
                f"Failed getting scan IDs for experiment {experiment} with "
                f"URL {url}") from e

        if not result:
            return []

        try:
            scan_ids = [
                item.get("ID") for item in result["ResultSet"]["Result"]
            ]
        except KeyError as e:
            raise XnatException(f"get_scan_ids - Malformed response. {e}"
                                ) from None

        return scan_ids

    def get_resource_ids(self,
                         study,
                         session,
                         experiment,
                         folder_name=None,
                         create=True):
        """
        Return a list of resource id's (subfolders) from an experiment
        """
        logger.debug(f"Getting resource ids for experiment: {experiment}")
        url = (f"{self.server}/data/archive/projects/{study}"
               f"/subjects/{session}/experiments/{experiment}"
               "/resources/?format=json")
        try:
            result = self._make_xnat_query(url)
        except Exception as e:
            raise XnatException(f"Failed getting resource ids with url: {url}"
                                ) from e
        if result is None:
            raise XnatException(
                f"Experiment: {experiment} not found for session: {session}"
                f" in study: {study}")

        if create and int(result["ResultSet"]["totalRecords"]) < 1:
            return self.create_resource_folder(study, session, experiment,
                                               folder_name)

        resource_ids = {}
        for r in result["ResultSet"]["Result"]:
            label = r.get("label", "No Label")
            resource_ids[label] = r["xnat_abstractresource_id"]

        if not folder_name:
            # foldername not specified return them all
            resource_id = list(resource_ids.values())
        else:
            # check if folder exists, if not create it
            try:
                resource_id = resource_ids[folder_name]
            except KeyError:
                # folder doesn't exist, create it
                if not create:
                    return None
                resource_id = self.create_resource_folder(
                    study, session, experiment, folder_name)

        return resource_id

    def create_resource_folder(self, study, session, experiment, label):
        """
        Creates a resource subfolder and returns the xnat identifier.
        """
        url = (f"{self.server}/data/archive/projects/{study}"
               f"/subjects/{session}/experiments/{experiment}"
               f"/resources/{label}/")
        self._make_xnat_put(url)
        return self.get_resource_ids(study, session, experiment, label)

    def get_resource_list(self, study, session, experiment, resource_id):
        """The list of non-dicom resources associated with an experiment
        returns a list of dicts, mostly interested in ID and name"""
        logger.debug(f"Getting resource list for experiment: {experiment}")
        url = (f"{self.server}/data/archive/projects/{study}"
               f"/subjects/{session}/experiments/{experiment}"
               f"/resources/{resource_id}/?format=xml")
        try:
            result = self._make_xnat_xml_query(url)
        except Exception as e:
            raise XnatException(f"Failed getting resources with url: {url}"
                                ) from e
        if result is None:
            raise XnatException(
                f"Experiment: {experiment} not found for session: {session}"
                f" in study: {study}")

        # define the xml namespace
        ns = {"cat": "http://nrg.wustl.edu/catalog"}
        entries = result.find("cat:entries", ns)
        if entries is None:
            # no files found, just a label
            return []

        items = [entry.attrib for entry in entries.findall("cat:entry", ns)]

        return items

    def put_dicoms(self, project, subject, experiment, filename, retries=3,
                   timeout=86400):
        """Upload an archive of dicoms to XNAT
        filename: archive to upload"""
        headers = {"Content-Type": "application/zip"}

        upload_url = (
            f"{self.server}/data/services/import?project={project}"
            f"&subject={subject}&session={experiment}&overwrite=delete"
            "&prearchive=false&Ignore-Unparsable=true&inbody=true")

        try:
            with open(filename, "rb") as data:
                self.make_xnat_post(upload_url, data, retries=retries,
                                    headers=headers, timeout=timeout)
        except requests.exceptions.Timeout as e:
            if retries == 1:
                raise e
            self.put_dicoms(project, subject, experiment, filename,
                            retries=retries-1, timeout=timeout+1200)
        except XnatException as e:
            e.study = project
            e.session = experiment
            raise e
        except requests.exceptions.RequestException as e:
            err = XnatException(f"Error uploading data with url: {upload_url}")
            err.study = project
            err.session = experiment
            raise err from e
        except IOError as e:
            logger.error(
                f"Failed to open file: {filename} with excuse: {e.strerror}")
            err = XnatException(f"Error in file: {filename}")
            err.study = project
            err.session = experiment
            raise err from e

    def get_dicom(self,
                  project,
                  session,
                  experiment,
                  scan,
                  filename=None,
                  retries=3):
        """Downloads a dicom file from xnat to filename
        If filename is not specified creates a temporary file
        and returns the path to that, user needs to be responsible
        for cleaning up any created tempfiles"""
        url = (f"{self.server}/data/archive/projects/{project}/"
               f"subjects/{session}/experiments/{experiment}/"
               f"scans/{scan}/resources/DICOM/files?format=zip")

        if not filename:
            filename = tempfile.mkstemp(prefix="dm2_xnat_extract_")
            # mkstemp returns a filename and a file object
            # dealing with the filename in future so close the file object
            os.close(filename[0])
            filename = filename[1]
        try:
            self.get_xnat_stream(url, filename, retries)
            return filename
        except Exception as e:
            try:
                os.remove(filename)
            except OSError as exc:
                logger.warning(f"Failed to delete tempfile: {filename} with "
                               f"excuse: {str(exc)}")
            err = XnatException(f"Failed getting dicom with url: {url}")
            err.study = project
            err.session = session
            raise err from e

    def put_resource(self, project, subject, experiment, filename, data,
                     folder):
        """Upload a resource file to the XNAT server.

        Args:
            project (:obj:`str`): the project to upload to.
            subject (:obj:`str`): The subject ID to upload to.
            experiment (:obj:`str`): the experiment ID to upload to.
            filename (:obj:`str`): The absolute path to a file to upload
            data (bytes): Bytes as produced from reading a file with
                ZipFile.read
            folder (:obj:`str`): The folder name to deposit the file in on
                XNAT.

        """

        try:
            self.get_experiment(project, subject, experiment)
        except XnatException:
            logger.warning(
                f"Experiment: {experiment} in subject: {subject} does not "
                "exist! Making new experiment")
            self.make_experiment(project, subject, experiment)

        resource_id = self.get_resource_ids(project,
                                            subject,
                                            experiment,
                                            folder_name=folder)

        uploadname = urllib.parse.quote(filename)

        attach_url = (f"{self.server}/data/archive/projects/{project}/"
                      f"subjects/{subject}/experiments/{experiment}/"
                      f"resources/{resource_id}/"
                      f"files/{uploadname}?inbody=true")

        try:
            self.make_xnat_post(attach_url, data)
        except XnatException as err:
            err.study = project
            err.session = experiment
            raise err
        except Exception as e:
            logger.warning(
                f"Failed adding resource to xnat with url: {attach_url}")
            err = XnatException("Failed adding resource to xnat")
            err.study = project
            err.session = experiment
            raise err from e

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

        url = (f"{self.server}/data/archive/projects/{project}/"
               f"subjects/{session}/experiments/{experiment}/"
               f"resources/{resource_group_id}/files/{resource_id}")
        if zipped:
            url = url + "?format=zip"

        if not filename:
            filename = tempfile.mkstemp(prefix="dm2_xnat_extract_")
            # mkstemp returns a file object and a filename we will deal with
            # the filename in future so close the file object
            os.close(filename[0])
            filename = filename[1]
        try:
            self.get_xnat_stream(url, filename, retries)
            return filename
        except Exception as e:
            try:
                os.remove(filename)
            except OSError as exc:
                logger.warning(f"Failed to delete tempfile: {filename} with "
                               f"exclude: {str(exc)}")
            logger.error("Failed getting resource from xnat", exc_info=True)
            raise XnatException(f"Failed downloading resource with url: {url}"
                                ) from e

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
        url = (f"{self.server}/data/archive/projects/{project}/"
               f"subjects/{session}/experiments/{experiment}/"
               f"resources/{resource_id}/files?format=zip")

        if not filename:
            filename = tempfile.mkstemp(prefix="dm2_xnat_extract_")
            # mkstemp returns a file object and a filename we will deal
            # with the filename in future so close the file object
            os.close(filename[0])
            filename = filename[1]
        try:
            self.get_xnat_stream(url, filename, retries)
            return filename
        except Exception as e:
            try:
                os.remove(filename)
            except OSError as exc:
                logger.warning(f"Failed to delete tempfile: {filename} with "
                               f"error: {str(exc)}")
            logger.error("Failed getting resource archive from xnat",
                         exc_info=True)
            raise XnatException(
                f"Failed downloading resource archive with url: {url}") from e

    def delete_resource(self, project, session, experiment, resource_group_id,
                        resource_id):
        """Delete a resource file from xnat"""
        url = (f"{self.server}/data/archive/projects/{project}/"
               f"subjects/{session}/experiments/{experiment}/"
               f"resources/{resource_group_id}/files/{resource_id}")
        try:
            self._make_xnat_delete(url)
        except Exception as e:
            raise XnatException(f"Failed deleting resource with url: {url}"
                                ) from e

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

        url = (f"{self.server}/data/archive/projects/{project}/subjects/"
               f"{old_name}?xsiType=xnat:mrSessionData&label={new_name}")
        try:
            self._make_xnat_put(url)
        except requests.HTTPError as e:
            if e.response.status_code == 409:
                raise XnatException(f"Can't rename {old_name} to {new_name}."
                                    "Subject already exists") from None
            if e.response.status_code == 422:
                # This is raised every time a subject is renamed.
                pass
            else:
                raise e

        if rename_exp:
            self.rename_experiment(project, new_name, old_name, new_name)

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
                f"experiment rename may fail. Error - {e}")

        experiments = self.get_experiment_ids(project, subject)
        if new_name in experiments:
            raise XnatException(
                f"Can't rename experiment {old_name} to {new_name}."
                "ID already in use.")

        url = (
            f"{self.server}/data/archive/projects/{project}/subjects/{subject}"
            f"/experiments/{old_name}?xsiType="
            f"xnat:mrSessionData&label={new_name}")

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

    def share_subject(self, source_project, source_sub, dest_project,
                      dest_sub):
        """Share an xnat subject into another project.

        Args:
            source_project (:obj:`str`): The name of the original project
                the subject was uploaded to.
            source_sub (:obj:`str`): The original ID of the subject to be
                shared.
            dest_project (:obj:`str`): The new project to add the subject to.
            dest_sub (:obj:`str`): The ID to give the subject in the
                destination project.

        Raises:
            XnatException: If the destination subject ID is already in use
                or the source subject doesn't exist.
            requests.HTTPError: If any unexpected behavior is experienced
                while interacting with XNAT's API
        """
        # Ensure source subject exists, raises an exception if not
        self.get_subject(source_project, source_sub)

        url = (f"{self.server}/data/projects/{source_project}/subjects/"
               f"{source_sub}/projects/{dest_project}?label={dest_sub}")

        try:
            self._make_xnat_put(url)
        except requests.HTTPError as e:
            if e.response.status_code == 409:
                raise XnatException(
                    f"Can't share {source_sub} as {dest_sub}, subject "
                    "ID already exists.") from None
            raise e

    def share_experiment(self, source_project, source_sub, source_exp,
                         dest_project, dest_exp):
        """Share an experiment into a new xnat project.

        Note: The subject the experiment belongs to must have already been
        shared to the destination project for experiment sharing to work.

        Args:
            source_project (:obj:`str`): The original project the experiment
                belongs to.
            source_sub (:obj:`str`): The original subject ID in the source
                project.
            source_exp (:obj:`str`): The original experiment name in the
                source project.
            dest_project (:obj:`str`): The project the experiment is to be
                added to.
            dest_exp (:obj:`str`): The name to apply to the experiment when
                it is added to the destination project.

        Raises:
            XnatException: If the destination experiment ID is already in
                use or the source experiment ID doesnt exist.
            requests.HTTPError: If any unexpected behavior is experienced
                while interacting with XNAT's API.
        """
        # Ensure source experiment exists, raises an exception if not
        self.get_experiment(source_project, source_sub, source_exp)

        url = (f"{self.server}/data/projects/{source_project}/subjects/"
               f"{source_sub}/experiments/{source_exp}/projects/"
               f"{dest_project}?label={dest_exp}")

        try:
            self._make_xnat_put(url)
        except requests.HTTPError as e:
            if e.response.status_code == 409:
                raise XnatException(f"Can't share {source_exp} as {dest_exp}"
                                    " experiment ID already exists") from None
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
            dismiss_url = (f"{self.server}/data/workflows/{autorun}"
                           "?wrk:workflowData/status=Complete")
            self._make_xnat_put(dismiss_url)

    def get_xnat_stream(self, url, filename, retries=3, timeout=300):
        """Get large objects from XNAT in a stream.
        """
        logger.debug(f"Getting {url} from XNAT")
        try:
            response = self.session.get(url, stream=True, timeout=timeout)
        except requests.exceptions.Timeout as e:
            if retries > 0:
                return self.get_xnat_stream(url,
                                            filename,
                                            retries=retries - 1,
                                            timeout=timeout * 2)
            raise e

        if response.status_code == 401:
            logger.info("Session may have expired, resetting")
            self.open_session()
            return self.get_xnat_stream(
                    url, filename, retries=retries, timeout=timeout)

        if response.status_code == 404:
            logger.info(
                f"No records returned from xnat server for query: {url}")
            return None

        if response.status_code == 504:
            if retries:
                logger.warning("xnat server timed out, retrying")
                time.sleep(30)
                self.get_xnat_stream(url,
                                     filename,
                                     retries=retries - 1,
                                     timeout=timeout * 2)
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
                raise e
            except IOError as e:
                logger.error("Failed writing to file")
                raise e
        return None

    def _make_xnat_query(self, url, retries=3, timeout=150):
        try:
            response = self.session.get(url, timeout=timeout)
        except requests.exceptions.Timeout as e:
            if retries > 0:
                return self._make_xnat_query(
                    url, retries=retries - 1, timeout=timeout * 2
                )
            logger.error(f"Xnat server timed out getting url {url}")
            raise e

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info("Session may have expired, resetting")
            self.open_session()
            response = self.session.get(url, timeout=timeout)

        if response.status_code == 404:
            logger.info(
                f"No records returned from xnat server for query: {url}")
            return None

        if response.status_code != 200:
            logger.error(f"Failed connecting to xnat server {self.server} "
                         f"with response code {response.status_code}")
            logger.debug("Username: {}")
            response.raise_for_status()

        return response.json()

    def _make_xnat_xml_query(self, url, retries=3):
        try:
            response = self.session.get(url)
        except requests.exceptions.Timeout as e:
            if retries > 0:
                return self._make_xnat_xml_query(url, retries=retries - 1)
            raise e

        if response.status_code == 401:
            # possibly the session has timed out
            logger.info("Session may have expired, resetting")
            self.open_session()
            response = self.session.get(url)

        if response.status_code == 404:
            logger.info(f"No records returned from xnat server to query {url}")
            return None
        if response.status_code != 200:
            logger.error(f"Failed connecting to xnat server {self.server}"
                         f" with response code {response.status_code}")
            logger.debug(f"Username: {self.auth[0]}")
            response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        return root

    def _make_xnat_put(self, url, retries=3):
        """Modify XNAT contents.
        """
        if retries == 0:
            raise requests.exceptions.HTTPError(
                f"Timed out adding data to xnat {url}"
            )

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
            logger.warning(
                f"http client error at folder creation: {response.status_code}"
            )
            response.raise_for_status()
        return None

    def make_xnat_post(self, url, data, retries=3, headers=None, timeout=3600):
        """Add data to XNAT.
        """
        logger.debug(f"POSTing data to xnat, {retries} retries left")
        response = self.session.post(url,
                                     headers=headers,
                                     data=data,
                                     timeout=timeout)

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
                self.make_xnat_post(url, data, retries=retries - 1)
            else:
                logger.warning("xnat server timed out, giving up")
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
            logger.warning(
                f"http client error deleting resource: {response.status_code}")
            response.raise_for_status()
        return None

    def __str__(self):
        return f"<datman.xnat.xnat {self.server}>"

    def __repr__(self):
        return self.__str__()
