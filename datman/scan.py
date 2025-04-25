"""
A class to make access to all information about a single scan easy
and uniform.

WARNING: This class currently assumes the contents of the directories
does not change after the object is created. Certain attribute values may
become out of date if this is not true.

"""
import glob
import os
import re
import logging

import datman.scanid
import datman.utils

logger = logging.getLogger(__name__)


class DatmanNamed(object):
    """
    A parent class for all classes that will obey the datman naming scheme

    Args:
        ident: A datman.scanid.Identifier instance

    """
    def __init__(self, ident):
        self._ident = ident
        self.full_id = ident.get_full_subjectid_with_timepoint()
        self.id_plus_session = (
            ident.get_full_subjectid_with_timepoint_session())  # noqa: E501
        self.study = ident.study
        self.site = ident.site
        self.subject = ident.subject
        self.timepoint = ident.timepoint
        self.session = ident.session
        self.bids_sub = f"sub-{ident.get_bids_name()}"
        self.bids_ses = f"ses-{ident.timepoint}"


class Series(DatmanNamed):
    """
    Holds all information about a series file of any format (e.g. nifti).

    Args:
        path: The absolute path to a single file.

    May raise a ParseException if the given file name does not match the
    datman naming convention.

    """
    def __init__(self, path):
        self.path = path
        self.ext = datman.utils.get_extension(path)
        self.file_name = os.path.basename(self.path)

        path_minus_ext = path.replace(self.ext, "")

        try:
            ident, tag, series, description = datman.scanid.parse_filename(
                path_minus_ext)
        except datman.scanid.ParseException:
            # re-raise the exception with a more descriptive message
            message = f"{path_minus_ext} does not match datman convention"
            raise datman.scanid.ParseException(message)
        DatmanNamed.__init__(self, ident)

        self.tag = tag
        self.series_num = series
        self.description = description

    def __str__(self):
        return self.file_name

    def __repr__(self):
        return f"<datman.scan.Series: {self.path}>"


class Scan(DatmanNamed):
    """
    Holds all information for a single scan (session).

    Args:
        subject_id (:obj:`str` or :obj:`datman.scanid.Identifier`):
            A valid datman subject ID.
        config (:obj:`datman.config.config`): The config object for
            the study this session belongs to.
        bids_root (:obj:`str`, optional): The root path where bids data
            is stored. If given, overrides any values from the configuration
            files.

    May raise a ParseException if the given subject_id does not match the
    datman naming convention

    """
    def __init__(self, subject_id, config, bids_root=None):
        self.is_phantom = datman.scanid.is_phantom(subject_id)

        if isinstance(subject_id, datman.scanid.Identifier):
            if subject_id.session:
                ident = subject_id
            else:
                ident = self._get_ident(str(subject_id))
        else:
            ident = self._get_ident(subject_id)

        try:
            self.project = config.map_xnat_archive_to_project(subject_id)
        except Exception as e:
            message = f"Failed getting project from config: {str(e)}"
            raise Exception(message)

        DatmanNamed.__init__(self, ident)

        for dir in ["nii", "nrrd", "mnc", "dcm", "qc"]:
            setattr(self, f"{dir}_path", self.__get_path(dir, config))

        if bids_root:
            self.bids_root = bids_root
        else:
            try:
                bids_root = config.get_path("bids")
            except datman.config.UndefinedSetting:
                bids_root = ""

        self.bids_root = bids_root
        self.bids_path = self.__get_bids()
        self._bids_inventory = self._make_bids_inventory()

        # This one lists all existing resource folders for the timepoint.
        self.resources = self._get_resources(config)
        # This one lists the intended location of the sessions' resource dir
        # The session num will be assumed to be 01 if one wasnt provided.
        self.resource_path = self.__get_path(
            "resources", config, session=True)

        self.__nii_dict = self.__make_dict(self.niftis)

        self.nii_tags = list(self.__nii_dict.keys())

    @property
    def niftis(self):
        return self.__get_series(self.nii_path, ['nii', '.nii.gz'])

    def _get_ident(self, subid):
        subject_id = self.__check_session(subid)
        try:
            ident = datman.scanid.parse(subject_id)
        except datman.scanid.ParseException:
            raise datman.scanid.ParseException(
                f"{subject_id} does not match datman convention")
        return ident

    def find_files(self, file_stem, format="nii"):
        """Find files belonging to the session matching a given file name.

        Args:
            file_stem (:obj:`str`): A valid datman-style file name, with or
                without the extension and preceding path.
            format (:obj:`str`): The configured datman folder path to search
                through. Default: 'nii'

        Returns:
            :obj:`list`: a list of full paths to matching files, if any. Or
                an empty list if none are found.

        Raises:
            datman.scanid.ParseException: If an invalid datman file name
                is given.
        """
        if format == 'bids':
            return self._find_bids_files(file_stem)

        try:
            base_path = getattr(self, f"{format}_path")
        except AttributeError:
            return []

        if not os.path.exists(base_path):
            return []

        return glob.glob(os.path.join(base_path, file_stem + "*"))

    def _find_bids_files(self, file_stem):
        ident, _, series, _ = datman.scanid.parse_filename(file_stem)
        if ident.session != self.session:
            return []
        if int(series) in self._bids_inventory:
            return self._bids_inventory[int(series)]
        return []

    def _make_bids_inventory(self):
        if not self.bids_path:
            return {}

        inventory = {}
        for path, _, files in os.walk(self.bids_path):
            if path.endswith("blacklisted"):
                continue

            for item in files:
                if item.endswith(".err"):
                    err_file = os.path.join(path, item)
                    ident, series = self._parse_err_file(err_file)
                    if ident and ident.session == self.session:
                        inventory.setdefault(series, []).append(err_file)
                    continue

                if not item.endswith(".json"):
                    continue

                json_path = os.path.join(path, item)
                contents = datman.utils.read_json(json_path)

                repeat = contents['Repeat'] if 'Repeat' in contents else '01'
                if repeat != self.session:
                    continue

                try:
                    series = int(contents['SeriesNumber'])
                except KeyError:
                    # Ignore sidecars missing a series number field.
                    continue
                base_fname = os.path.splitext(json_path)[0]

                inventory.setdefault(series, []).extend(
                    glob.glob(base_fname + "*")
                )

        return inventory

    def _parse_err_file(self, fname):
        with open(fname, "r") as fh:
            lines = fh.readlines()

        regex = ".*<.*Importer (.*) - ([0-9]+)>*"
        match = re.match(regex, lines[0])
        if not match:
            logger.error(f"Can't parse error file - {fname}")
            return None, None

        subid, series = match.groups()
        series = int(series)

        try:
            ident = datman.scan.parse(subid)
        except datman.scanid.ParseException:
            logger.error(f"Unparseable ID found in error file - {subid}")
            return None, series

        return ident, series

    def get_tagged_nii(self, tag):
        try:
            matched_niftis = self.__nii_dict[tag]
        except KeyError:
            matched_niftis = []
        return matched_niftis

    def get_resource_dir(self, session):
        for resource_dir in self.resources:
            ident = datman.scanid.parse(os.path.basename(resource_dir))
            if int(ident.session) != int(session):
                continue
            if os.path.exists(resource_dir):
                return resource_dir
        return

    def _get_resources(self, config):
        search_path = os.path.join(config.get_path("resources"),
                                   self.full_id + "*")
        valid_paths = []
        for found_path in glob.glob(search_path):
            try:
                ident = datman.scanid.parse(os.path.basename(found_path))
            except datman.scanid.ParseException:
                continue
            if ident.session:
                # ignore folders missing a session, this is an error.
                valid_paths.append(found_path)
        return valid_paths

    def __check_session(self, id_str):
        """
        Adds a default session number of "_01" if it's missing and the id
        doesn't belong to a phantom
        """
        fields = id_str.split("_")
        if len(fields) == 4 and not self.is_phantom:
            # Fill in missing session number with the default
            id_str = id_str + "_01"
        return id_str

    def __get_path(self, key, config, session=False):
        folder_name = self.full_id
        if session:
            folder_name = self.id_plus_session
        try:
            path = os.path.join(config.get_path(key), folder_name)
        except datman.config.UndefinedSetting:
            return ""
        return path

    def __get_bids(self):
        if not self.bids_root:
            return ""
        return os.path.join(self.bids_root, self.bids_sub, self.bids_ses)

    def __get_series(self, path, ext_list):
        """
        This method will generate a ParseException if any files are not named
        according to the datman naming convention.
        """
        glob_path = os.path.join(path, "*")
        series_list = []
        badly_named = []
        for item in glob.glob(glob_path):
            if datman.utils.get_extension(item) in ext_list:
                try:
                    series = Series(item)
                except datman.scanid.ParseException:
                    badly_named.append(item)
                    continue
                series_list.append(series)
        if badly_named:
            message = f"File(s) misnamed: {', '.join(badly_named)}"
            raise datman.scanid.ParseException(message)
        return series_list

    def __make_dict(self, series_list):
        tag_dict = {}
        for series in series_list:
            tag = series.tag
            try:
                tag_dict[tag].append(series)
            except KeyError:
                tag_dict[tag] = [series]
        return tag_dict

    def __str__(self):
        return self.full_id

    def __repr__(self):
        return f"<datman.scan.Scan: {self.full_id}>"
