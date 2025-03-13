"""Input formats that datman can use to read new data.

This file contains classes for reading in data that is _new_ to datman. Datman
uses these classes to create a uniform interface for its exporters, which
create the files and database contents users may actually interact with.
"""
from abc import ABC, abstractmethod
from datetime import datetime
import glob
import json
import logging
import os
import re
import shutil
from zipfile import ZipFile

from datman.exceptions import ParseException, XnatException, InputException
from datman.utils import is_dicom, get_archive_headers


logger = logging.getLogger(__name__)


class SessionImporter(ABC):

    # Exporters currently use these from XNATExperiment:
    # experiment.name
    # experiment.source_name (related to sharing data)
    # experiment.scans
    # experiment.date
    # experiment.is_shared()

    # Missed but possibly needed attributes (from extract):
    #   experiment.assign_scan_names(config, ident)
    #
    # Maybe we really just need a resource exporter class...
    #   experiment.resource_files (list of dicts)
    #   experiment.resource_IDs (dict of folder names to numerical IDs)
    #           e.g. {'behav': '297528', 'misc': '305312'}

    @property
    @abstractmethod
    def name(self) -> str:
        """A valid ID for the scan session being imported.
        """
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """The original ID of a scan session shared from another project.

        If the session currently being imported originates from another
        project, 'name' is the session's ID in the new project and source_name
        corresponds to it's original ID. This will be equal to 'name' when
        the session is not shared or sharing is not being tracked.
        """
        pass

    @property
    @abstractmethod
    def date(self) -> str:
        """A string representation (YYYY-MM-DD) of the scan collection date.
        """
        pass

    @property
    @abstractmethod
    def scans(self) -> list['SeriesImporter']:
        """A list scan series that belong to the session.
        """
        pass

    @property
    @abstractmethod
    def dcm_dir(self) -> str:
        """The subfolder that will hold the session's dicom dirs.
        """
        pass

    @abstractmethod
    def is_shared(self) -> bool:
        """Indicates whether the session is shared with other projects.
        """
        pass

    def assign_scan_names(self, config, ident):
        """Assign a datman style name to each scan in this experiment.

        This will populate the names and tags fields for any scan that
        matches the study's export configuration.

        Args:
            config (:obj:`datman.config.config`): A config object for the
                study this experiment belongs to.
            ident (:obj:`datman.scanid.Identifier`): A valid ID to apply
                to this experiment's data.
        """
        tags = config.get_tags(site=ident.site)
        if not tags.series_map:
            logger.error(
                f"Failed to get tag export info for study {config.study_name}"
                f" and site {ident.site}")
            return

        for scan in self.scans:
            try:
                scan.set_datman_name(str(ident), tags)
            except Exception as e:
                logger.info(
                    f"Failed to make file name for series {scan.series} "
                    f"in session {str(ident)}. Reason {type(e).__name__}: "
                    f"{e}")


class SeriesImporter(ABC):
    # XNATScan attributes and methods used by exporters...
    # .series
    # .subject (FakeSideCar needs)
    # .names
    # .description

    # MISSED (may have missed more in dm_xnat_extract):
    #   scan.download_dir
    #       xnat copy for example points to: /scratch/dawn/temp_stuff/export_zip/xnat_copy/SPN10_CMH_0083_01_SE01_MR/scans/6-t1_mprage_T1_900/resources/DICOM/files
    #       unzipped copy would be (diff session): 20190116_Ex09352_ASND1MR_ASQB002/Ex09352_Se00003_SagT1Bravo-1mm-32ch/
    @property
    @abstractmethod
    def dcm_dir(self) -> str:
        """Full path to the folder that holds a local copy of the dicom files.
        """
        pass

    @property
    @abstractmethod
    def series(self) -> str:
        """A string representation of the series 'number'

        This should be a string because sometimes the 'number' comes with
        non-numeric prefixes or postfixes (e.g. on XNAT in some circumstances).
        """
        pass

    @property
    @abstractmethod
    def subject(self) -> str:
        """The subject ID of the session this scan belongs to.

        The subject ID may vary from the SessionImporter.name (i.e. a
        truncated or extended version of it as subject may be to experiment
        on XNAT).
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """The series description (as from the dicom headers).
        """
        pass

    @property
    @abstractmethod
    def names(self) -> list[str]:
        """A list of valid scan names that may be applied to this series.
        """
        pass

    @abstractmethod
    def set_datman_name(self, ident: str, tags: 'datman.config.TagInfo'
        ) -> list[str]:
        pass

    def _mangle_descr(self) -> str:
        """Modify a series description to remove non-alphanumeric characters.
        """
        if not self.description:
            return ""
        return re.sub(r"[^a-zA-Z0-9.+]+", "-", self.description)


###############################################################################
#### XNAT classes, formerly in xnat.py


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
            exp for exp in self.raw_json["children"]
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


class XNATExperiment(SessionImporter, XNATObject):
    def __init__(self, project, subject_name, experiment_json,
                 ident=None):
        self.raw_json = experiment_json
        self.project = project
        self.subject = subject_name
        self.uid = self._get_field("UID")
        self.id = self._get_field("ID")
        self.date = self._get_field("date")
        self._ident = ident

        if self.is_shared():
            self.name = [label for label in self.get_alt_labels()
                         if self.subject in label][0]
            self.source_name = self._get_field("label")
        else:
            self.name = self._get_field("label")
            self.source_name = self.name

        # The subdirectory to find the dicoms in after download
        self.dcm_dir = os.path.join(self.name, "scans")

        # Scan attributes
        self.scans = self._get_scans()
        self.scan_UIDs = self._get_scan_UIDs()
        self.scan_resource_IDs = self._get_scan_rIDs()

        # Resource attributes
        self.resource_files = self._get_contents("resources/resource")
        self.resource_IDs = self._get_resource_IDs()

        # Misc - basically just OPT CU1 needs this
        self.misc_resource_IDs = self._get_other_resource_IDs()

    # Use properties here to conform with SessionImporter interface
    # and guarantee at creation that expected attributes exist
    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        self._name = value

    @property
    def source_name(self) -> str:
        return self._source_name

    @source_name.setter
    def source_name(self, value: str):
        self._source_name = value

    @property
    def scans(self) -> list['SeriesImporter']:
        return self._scans

    @scans.setter
    def scans(self, value: list['SeriesImporter']):
        self._scans = value

    @property
    def date(self) -> str:
        return self._date

    @date.setter
    def date(self, value: str):
        self._date = value

    @property
    def dcm_dir(self) -> str:
        return self._dcm_dir

    @dcm_dir.setter
    def dcm_dir(self, value: str):
        self._dcm_dir = value

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
            xnat_scans.append(XNATScan(self, scan_json))
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
                resource["data_fields"]["xnat_abstractresource_id"])
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
                    if label != "DICOM" and (data_format != "DICOM"
                                             and label != "SNAPSHOTS"):
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
        """.format(exp_id=self.id, project=self.project)  # noqa: E501

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
                self.project, self.subject, self.name, r_id)
            resources.extend([item["URI"] for item in resource_list])
        return resources

    def get_files(self, dest_folder, xnat, zip_name=None):
        """
        Download a zip file containing all data for this session. Returns the
        path to the new file if download is successful, raises an exception if
        not

        Args:
            dest_folder: The absolute path to the folder where the zip
                should be deposited
            xnat: An instance of datman.xnat.xnat()
            zip_name: An optional name for the output zip file. If not
                set the zip name will be session.name

        """
        resources_list = list(self.scan_resource_IDs)
        resources_list.extend(self.misc_resource_IDs)
        resources_list.extend(self.resource_IDs)

        if not resources_list:
            raise ValueError(f"No scans or resources found for {self.name}")

        url = (f"{xnat.server}/REST/experiments/{self.id}/resources/"
               f"{','.join(resources_list)}/files?structure=improved"
               "&all=true&format=zip")

        if not zip_name:
            zip_name = self.name.upper() + ".zip"

        output_path = os.path.join(dest_folder, zip_name)
        if os.path.exists(output_path):
            logger.error(
                f"Cannot download {output_path}, file already exists.")
            return output_path

        xnat._get_xnat_stream(url, output_path)

        return output_path

    def is_shared(self) -> bool:
        """Check if the experiment is shared from another project.
        """
        alt_names = self.get_alt_labels()
        if not alt_names:
            return False

        return any([self.subject in label for label in alt_names])

    def get_alt_labels(self):
        """Find the names for all shared copies of the XNAT experiment.
        """
        shared = self._get_contents("sharing/share")
        if not shared:
            return []
        return [item['data_fields']['label'] for item in shared[0]]

    def __str__(self):
        return f"<XNATExperiment {self.name}>"

    def __repr__(self):
        return self.__str__()


class XNATScan(SeriesImporter, XNATObject):
    def __init__(self, experiment, scan_json):
        self.project = experiment.project
        self.subject = experiment.subject
        self.experiment = experiment.name
        self.shared = experiment.is_shared()
        self.source_experiment = experiment.source_name
        self.raw_json = scan_json
        self.uid = self._get_field("UID")
        self.series = self._get_field("ID")
        self.image_type = self._get_field("parameters/imageType")
        self.multiecho = self.is_multiecho()
        self.description = self._set_description()
        self.type = self._get_field("type")
        self.names = []
        self.tags = []
        self.dcm_dir = None

    # Use properties here to conform with SeriesImporter interface
    # and guarantee at creation that expected attributes exist
    @property
    def dcm_dir(self) ->str:
        return self._dcm_dir

    @dcm_dir.setter
    def dcm_dir(self, value: str):
        self._dcm_dir = value

    @property
    def series(self) -> str:
        return self._series

    @series.setter
    def series(self, value: str):
        self._series = value

    @property
    def subject(self) -> str:
        return self._subject

    @subject.setter
    def subject(self, value: str):
        self._subject = value

    @property
    def description(self) -> str:
        return self._description

    @description.setter
    def description(self, value: str):
        self._description = value

    @property
    def names(self) -> list[str]:
        return self._names

    @names.setter
    def names(self, value: list[str]):
        self._names = value

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
                "Assuming it's not derived.")
            return False
        if "DERIVED" in self.image_type:
            return True
        return False

    def set_tag(self, tag_map):
        matches = {}
        for tag, pattern in tag_map.items():

            if 'SeriesDescription' in pattern:
                regex = pattern['SeriesDescription']
                search_target = self.description
            elif 'XnatType' in pattern:
                regex = pattern['XnatType']
                search_target = self.type
            else:
                raise KeyError(
                    "Missing keys 'SeriesDescription' or 'XnatType'"
                    " for Pattern!")

            if isinstance(regex, list):
                regex = "|".join(regex)
            if re.search(regex, search_target, re.IGNORECASE):
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

    def set_datman_name(self, base_name, tags):
        mangled_descr = self._mangle_descr()
        padded_series = self.series.zfill(2)
        tag_settings = self.set_tag(tags.series_map)
        if not tag_settings:
            raise ParseException(
                f"Can't identify tag for series {self.series}")
        names = []
        self.echo_dict = {}
        for tag in tag_settings:
            name = "_".join([base_name, tag, padded_series, mangled_descr])
            if self.multiecho:
                echo_num = tag_settings[tag]["EchoNumber"]
                if echo_num not in self.echo_dict:
                    self.echo_dict[echo_num] = name
            names.append(name)

        if len(self.tags) > 1 and not self.multiecho:
            logger.error(f"Multiple export patterns match for {base_name}, "
                         f"descr: {self.description}, tags: {self.tags}")
            names = []
            self.tags = []

        self.names = names
        return names

    def is_usable(self, strict=False):
        if not self.raw_dicoms_exist():
            logger.debug(f"Ignoring {self.series} for {self.experiment}. "
                         f"No RAW dicoms exist.")
            return False

        if not self.description:
            logger.error(f"Can't find description for series {self.series} "
                         f"from session {self.experiment}.")
            return False

        if not strict:
            return True

        if self.is_derived():
            logger.debug(
                f"Series {self.series} in session {self.experiment} is a "
                "derived scan. Ignoring.")
            return False

        if not self.names:
            return False

        return True

    def get_files(self, output_dir, xnat_conn):
        """Download all dicoms for this series.

        This will download all files in the series, and if successful,
        set the dcm_dir attribute to the destination folder.

        Args:
            output_dir (:obj:`str`): The full path to the location to
                download all files to.
            xnat_conn (:obj:`datman.xnat.xnat`): An open xnat connection
                to the server to download from.

        Returns:
            bool: True if the series was downloaded, False otherwise.
        """
        logger.info(f"Downloading dicoms for {self.experiment} series: "
                    f"{self.series}.")

        if self.dcm_dir:
            logger.debug(
                "Data has been previously downloaded, skipping redownload.")
            return True

        try:
            dicom_zip = xnat_conn.get_dicom(self.project, self.subject,
                                            self.experiment, self.series)
        except Exception as e:
            logger.error(f"Failed to download dicom archive for {self.subject}"
                         f" series {self.series}. Reason - {e}")
            return False

        if os.path.getsize(dicom_zip) == 0:
            logger.error(
                f"Server returned an empty file for series {self.series} in "
                f"session {self.experiment}. This may be a server error."
            )
            os.remove(dicom_zip)
            return False

        logger.info(f"Unpacking archive {dicom_zip}")

        try:
            with ZipFile(dicom_zip, "r") as fh:
                fh.extractall(output_dir)
        except Exception as e:
            logger.error("An error occurred unpacking dicom archive for "
                         f"{self.experiment}'s series {self.series}' - {e}")
            os.remove(dicom_zip)
            return False
        else:
            logger.info("Unpacking complete. Deleting archive file "
                        f"{dicom_zip}")
            os.remove(dicom_zip)

        if self.shared:
            self._fix_download_name(output_dir)

        dicom_file = self._find_first_dicom(output_dir)

        try:
            self.dcm_dir = os.path.dirname(dicom_file)
        except TypeError:
            logger.warning("No valid dicom files found in XNAT session "
                           f"{self.subject} series {self.series}.")
            return False
        return True

    def _find_first_dicom(self, dcm_dir):
        """Finds a dicom from the series (if any) in the given directory.

        Args:
            dcm_dir (:obj:`str`): The directory to search for dicoms.

        Returns:
            str: The full path to a dicom, or None if no readable dicoms
                exist in the folder.
        """
        search_dir = self._find_series_dir(dcm_dir)
        for root_dir, folder, files in os.walk(search_dir):
            for item in files:
                path = os.path.join(root_dir, item)
                if is_dicom(path):
                    return path

    def _find_series_dir(self, search_dir):
        """Find the directory a series was downloaded to, if any.

        If multiple series are downloaded to the same temporary directory
        this will search for the expected downloaded path of this scan.

        Args:
            search_dir (:obj:`str`): The full path to a directory to search.

        Returns:
            str: The full path to this scan's download location.
        """
        expected_path = os.path.join(search_dir, self.experiment, "scans")
        found = glob.glob(os.path.join(expected_path, f"{self.series}-*"))
        if not found:
            return search_dir
        if not os.path.exists(found[0]):
            return search_dir
        return found[0]

    def _fix_download_name(self, output_dir):
        """Rename a downloaded XNAT-shared scan to match the expected label.
        """
        orig_dir = os.path.join(output_dir, self.source_experiment)
        try:
            os.rename(orig_dir,
                      orig_dir.replace(
                          self.source_experiment,
                          self.experiment))
        except OSError:
            for root, dirs, _ in os.walk(orig_dir):
                for item in dirs:
                    try:
                        os.rename(os.path.join(root, item),
                                  os.path.join(
                                      root.replace(
                                          self.source_experiment,
                                          self.experiment),
                                      item)
                                  )
                    except OSError:
                        pass
                    else:
                        shutil.rmtree(orig_dir)
                        return

    def __str__(self):
        return f"<XNATScan {self.experiment} - {self.series}>"

    def __repr__(self):
        return self.__str__()


#############################################################################
# Zip file classes


class ZipImporter(SessionImporter):

    def __init__(self, ident, zip_path):
        # Would be good to not need ident here...
        self._ident = ident
        self.path = zip_path
        self.name = zip_path
        self.contents = self.parse_contents()
        self.scans = self.get_scans()
        self.resources = self.contents['resources']
        # For compatibility (fix later)
        self.resource_files = self.resources
        self.dcm_dir = os.path.split(self.scans[0].series_dir)[0]
        try:
            # Convert date to same format XNAT gives
            self.date = str(datetime.strptime(self.scans[0].date, "%Y%m%d").date())
        except ValueError:
            logger.error("Unexpected date format in dicom header.")
            self.date = self.scans[0].date

    # Use properties here to conform with SessionImporter interface
    # and guarantee at creation that expected attributes exist
    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        self._name, _ = os.path.splitext(os.path.basename(value))

    @property
    def source_name(self) -> str:
        # When using zip files, can't really track shared IDs so always
        # equal name.
        return self.name

    @source_name.setter
    def source_name(self, value: str):
        self.name = value

    @property
    def scans(self) -> list['SeriesImporter']:
        return self._scans

    @scans.setter
    def scans(self, value: list['SeriesImporter']):
        self._scans = value

    @property
    def date(self) -> str:
        return self._date

    @date.setter
    def date(self, value: str):
        self._date = value

    @property
    def dcm_dir(self) -> str:
        return self._dcm_dir

    @dcm_dir.setter
    def dcm_dir(self, value: str):
        self._dcm_dir = value

    def is_shared(self) -> bool:
        # Can't track shared sessions with zip files.
        return False

    def get_files(self, dest_path: str, *args) -> str:
        """Unpack the zip file at the given location.

        Args:
            dest_path (str): The full path to the location to extract into.
        """
        for item in self.scans:
            item.get_files(dest_path)
        self.extract_resources(dest_path)

    def get_resources(self, dest_path: str, fname: str = None):
        with ZipFile(self.path, "r") as fh:
            if fname:
                fh.extract(fname, path=dest_path)
                return
            for item in self.resources:
                fh.extract(item, path=dest_path)

    def parse_contents(self):
        contents = {
            'scans': {},
            'resources': []
        }
        with ZipFile(self.path, "r") as fh:
            par_dir = fh.filelist[0].filename.strip('/')
            for item in fh.filelist[1:]:
                if item.is_dir():
                    contents['scans'].setdefault(item.filename.strip('/'), [])
                else:
                    folder, _ = os.path.split(item.filename)
                    if folder == par_dir:
                        contents['resources'].append(item.filename)
                    else:
                        contents['scans'].setdefault(folder, []).append(
                            item.filename)
        return contents

    def get_scans(self):
        # Headers = dict[rel_path -> pydicom.dataset.FileDataset]
        headers = get_archive_headers(self.path)
        # scans = []
        # for sub_path in headers:
        #     # .get_full_subjectid may need to be changed for compatibility
        #     scans.append(
        #         ZipSeriesImporter(
        #             self.ident.get_full_subjectid(), self.path, sub_path,
        #             headers[sub_path], self.contents['scans'][sub_path]
        #         )
        #     )
        # return scans
        scans = {}
        duplicate_series = set()
        for sub_path in headers:
            # .get_full_subjectid may need to be changed for compatibility
            zip_scan = ZipSeriesImporter(
                    self._ident.get_full_subjectid(), self.path, sub_path,
                    headers[sub_path], self.contents['scans'][sub_path]
            )
            if zip_scan.series in scans:
                duplicate_series.add(zip_scan.series)
            else:
                scans[zip_scan.series] = zip_scan

        # Omit scans when more than one has the same series num (can't handle
        # these...)
        if duplicate_series:
            logger.error("Duplicate series present in zip file. "
                         f"Ignoring: {duplicate_series}")

        for series in duplicate_series:
            del scans[series]

        return list(scans.values())

    def __str__(self):
        return f"<ZipImporter {self.path}"

    def __repr__(self):
        return self.__str__()


class ZipSeriesImporter(SeriesImporter):

    def __init__(self, subject, zip_file, series_dir, header, zip_items):
        self.subject = subject
        self.zip_file = zip_file
        self.series_dir = series_dir
        self.header = header
        self.contents = zip_items
        self.date = str(header.get('StudyDate'))
        self.series = str(header.get('SeriesNumber'))
        self.description = str(header.get('SeriesDescription'))
        self.uid = str(header.get('StudyInstanceUID'))
        try:
            self.image_type = "////".join(header.get("ImageType"))
        except TypeError:
            self.image_type = ""
        self.names = []
        self.dcm_dir = None

    # Use properties here to conform with SeriesImporter interface
    # and guarantee at creation that expected attributes exist
    @property
    def dcm_dir(self) -> str:
        return self._dcm_dir

    @dcm_dir.setter
    def dcm_dir(self, value):
        self._dcm_dir = value

    @property
    def series(self) -> str:
        return self._series

    @series.setter
    def series(self, value: str):
        self._series = value

    @property
    def subject(self) -> str:
        return self._subject

    @subject.setter
    def subject(self, value: str):
        self._subject = value

    @property
    def description(self) -> str:
        return self._description

    @description.setter
    def description(self, value: str):
        self._description = value

    @property
    def names(self) -> list[str]:
        return self._names

    @names.setter
    def names(self, value: list[str]):
        self._names = value

    def is_usable(self):
        return any([item.endswith(".dcm") for item in self.contents])

    def get_files(self, output_dir: str, *args):
        with ZipFile(self.zip_file, "r") as fh:
            for item in self.contents:
                fh.extract(item, path=output_dir)
        self.dcm_dir = os.path.join(output_dir, self.series_dir)

    def set_datman_name(self, base_name: str, tags: 'datman.config.TagInfo'
            ) -> list[str]:
        mangled_descr = self._mangle_descr()
        tag_settings = self.set_tag(tags.series_map)
        if not tag_settings:
            raise ParseException(
                f"Can't identify tag for series {self.series}")

        names = []
        for tag in tag_settings:
            names.append(
                "_".join([base_name, tag, self.series.zfill(2), mangled_descr])
            )

        self.names = names
        return names

    def set_tag(self, tag_map):
        matches = {}
        for tag, pattern in tag_map.items():
            if 'SeriesDescription' not in pattern:
                raise KeyError(
                    "Missing key 'SeriesDescription' for 'Pattern'!")

            regex = pattern['SeriesDescription']
            if isinstance(regex, list):
                regex = "|".join(regex)

            if re.search(regex, self.description, re.IGNORECASE):
                matches[tag] = pattern

        if (len(matches) == 1 or
                all(['EchoNumber' in matches[tag] for tag in matches])):
            self.tags = list(matches.keys())
            return matches

    def __str__(self):
        return f"<ZipSeriesImporter {self.series} - {self.description}>"

    def __repr__(self):
        return self.__str__()
