"""Return the site wide config file and project config files

By default the system_config.yaml file is location is read from the
environment variable ``os.environ['DM_CONFIG']``

The system is identified from ``os.environ['DM_SYSTEM']`` and can be used to
switch between multiple installations of datman or different computing systems.

These can both be overridden at ``__init__.py``
"""

import inspect
import logging
import os

import wrapt
import yaml

import datman.dashboard as dashboard
import datman.scanid
from datman.exceptions import ConfigException, UndefinedSetting

logger = logging.getLogger(__name__)


@wrapt.decorator
def study_required(func, instance, args, kwargs):
    # This is needed in case user passes keyword args as positional parameters
    # e.g. config.get_path('nii', 'SPINS') instead of
    # config.get_path('nii', study='SPINS')
    found_kwargs = inspect.getcallargs(func, *args, **kwargs)
    if "study" in found_kwargs and found_kwargs["study"]:
        instance.set_study(found_kwargs["study"])
    if not instance.study_config:
        raise ConfigException("Study not set.")
    return func(*args, **kwargs)


class config(object):
    system_config = None
    study_config = None
    install_config = None
    study_name = None
    study_config_file = None

    def __init__(self, filename=None, system=None, study=None):
        """
        Manages the datman configuration files.

        Inputs:
            filename - Full path to the site-wide config file. If filename is
                       not set will check the environment variable DM_CONFIG.
                       All study configuration files are located using the
                       'Projects' setting from this file
            system   - Used to generate different paths depending on which
                       installation is used. At least one 'system' must be
                       defined. If not set will check environment variable
                       DM_SYSTEM
            study    - Loads the settings for a specific study in addition to
                       the site-wide settings.
        """

        if not filename:
            try:
                filename = os.environ["DM_CONFIG"]
            except KeyError:
                raise ConfigException("Failed to find main config file")

        self.system_config = self.load_yaml(filename)

        if not system:
            try:
                system = os.environ["DM_SYSTEM"]
            except KeyError:
                raise ConfigException("Failed to identify current system")

        self.system = system
        system_settings = self._search_system_conf("SystemSettings")
        try:
            self.install_config = system_settings[system]
        except KeyError:
            raise ConfigException(
                f"Installation {system} not found in main config file"
            )

        if study:
            self.set_study(study)

    def load_yaml(self, filename):
        if not os.path.isfile(filename):
            raise ConfigException(
                f"configuration file {filename} not found. Try again."
            )
        with open(filename, "r") as stream:
            config_yaml = yaml.load(stream, Loader=yaml.SafeLoader)

        return config_yaml

    def set_study(self, study_name):
        """
        This function can take just the study ID for every study except DTI. So
        where possible, please give it an exact match to a project name or a
        full session ID.
        """
        # make the supplied project_name case insensitive
        valid_projects = {k.lower(): k for k in self.get_key("Projects")}

        if study_name.lower() in valid_projects:
            study_name = study_name.upper()
        else:
            # This will raise an exception if given only the 'DTI' id because
            # two studies are mapped to this ID. Give set_study() a full
            # session ID to avoid this
            study_name = self.map_xnat_archive_to_project(study_name)

        self.study_name = study_name

        config_path = self.get_key("CONFIG_DIR")
        projects = self.get_key("Projects")

        try:
            study_yaml = projects[study_name]
        except KeyError:
            raise UndefinedSetting(f"Study {study_name} not configured.")

        project_settings_file = os.path.join(config_path, study_yaml)
        self.study_config = self.load_yaml(project_settings_file)
        self.study_config_path = project_settings_file

    def get_study_base(self, study=None):
        """Return the base directory for a study"""

        proj_dir = self.get_key("DATMAN_PROJECTSDIR")

        if study:
            self.set_study(study)

        if not self.study_config:
            logger.warning("Study not set")
            return proj_dir

        return os.path.join(proj_dir, self.get_key("PROJECTDIR"))

    def map_xnat_archive_to_project(self, filename):
        """Maps the XNAT tag (e.g. SPN01) to the project name e.g. SPINS
        Can either supply a full filename in which case only the first part
        is considered or just a tag.

        By default the project tag is extracted from the filename and matched
        to the "STUDY_TAG" in the study config file. If a study has used
        multiple site tags (e.g. SPN01, SPINS) these can be defined in the
        site specific [SITE_TAGS] key.

        One project tag (DTI) is shared between two xnat archives (DTI15T and
        DTI3T), the site is used to differentiate between them. As a result, if
        only a 'DTI' project tag is given this function raises an exception.
        """
        logger.debug(f"Searching projects for: {filename}")

        try:
            parts = datman.scanid.parse(filename)
        except datman.scanid.ParseException:
            # The exception may be because a study tag was given instead of a
            # full ID. Check for this case, exit if it's just a bad ID
            parts = filename.split("_")
            if len(parts) > 1:
                raise datman.scanid.ParseException(f"Malformed ID: {filename}")
            tag = parts[0]
            site = None
        else:
            tag = parts.study
            site = parts.site

        project = dashboard.get_project(tag=tag, site=site)
        if project:
            return project.id

        # Abandon all hope, ye who enter here ##########

        if tag == "DTI" and not isinstance(parts, datman.scanid.Identifier):
            # if parts isnt a datman scanid, only the study tag was given. Cant
            # be sure which DTI study is correct without site info
            raise RuntimeError(
                "Cannot determine if DTI15T or DTI3T based on "
                f"input: {filename}"
            )

        # If a valid project name was given instead of a study tag, return that
        projects = self.get_key("Projects")
        if tag in projects.keys():
            self.set_study(tag)
            return tag

        for project in projects.keys():
            # search each project for a match to the study tag,
            # this loop exits as soon as a match is found.
            logger.debug(f"Searching project: {project}")

            self.set_study(project)
            site_tags = []

            if "Sites" not in self.study_config.keys():
                logger.debug(f"No sites defined for {project}")
                continue

            for key, site_config in self.get_key("Sites").items():
                try:
                    add_tags = [t.lower() for t in site_config["SITE_TAGS"]]
                except KeyError:
                    add_tags = []
                site_tags.extend(add_tags)

            site_tags.append(self.study_config["STUDY_TAG"].lower())

            if tag.lower() in site_tags:
                # Hack to deal with DTI not being a unique tag :(
                if project.upper() == "DTI15T" or project.upper() == "DTI3T":
                    if parts.site == "TGH":
                        project = "DTI15T"
                    else:
                        project = "DTI3T"
                # Needs to be set here in addition to at the top of the loop in
                # case the wrong DTI study settings were encountered
                # for the last set_study call. Ugh.
                self.set_study(project)
                return project
        # didn't find a match throw a warning
        logger.warn(f"Failed to find a valid project for xnat id: {tag}")
        raise ValueError

    def _search_site_conf(self, site, key):
        """
        Search a specific study's site for 'key'.

        Raises 'UndefinedSetting' if the key does not exist
        """
        try:
            site_conf = self._search_study_conf("Sites")
        except UndefinedSetting:
            raise ConfigException(
                f"'Sites' not defined for study {self.study_name}"
            )
        try:
            site_conf = site_conf[site]
        except KeyError:
            raise ConfigException(
                f"Site '{site}' not found for study {self.study_name}"
            )
        try:
            value = site_conf[key]
        except KeyError:
            raise UndefinedSetting(f"'{key}' not set for site {site}")
        return value

    def _search_study_conf(self, key):
        """
        Search the current study's config for 'key'. Does not search
        recursively i.e. will not check all sites.

        Raises UndefinedSetting if key is not found
        """
        if not self.study_config:
            raise ConfigException("Study not set.")
        try:
            value = self.study_config[key]
        except KeyError:
            raise UndefinedSetting(
                f"'{key}' not defined for study {self.study_name}"
            )
        return value

    def _search_local_conf(self, key):
        """
        Searches the currently configured system (i.e. the system found in
        'SystemSettings' for 'key')

        Raises UndefinedSetting if key is not found
        """
        try:
            system_settings = self._search_system_conf("SystemSettings")
        except UndefinedSetting:
            raise ConfigException("'SystemSettings' not defined")
        try:
            local_system = system_settings[self.system]
        except KeyError:
            raise ConfigException(
                f"System '{key}' not defined in SystemSettings"
            )
        try:
            value = local_system[key]
        except KeyError:
            raise UndefinedSetting(
                f"'{key}' not defined for system {self.system}"
            )
        return value

    def _search_system_conf(self, key):
        """
        Searches the global system-wide settings for 'key'. Will not search
        recursively (i.e. will not check within studies or sites)

        Raises UndefinedSetting if key is not found.
        """
        try:
            value = self.system_config[key]
        except KeyError:
            raise UndefinedSetting(f"'{key}' not set")
        return value

    def _get_setting(self, search_func, args, stop_search=False, merge=None):
        """
        A helper function to assist with changing scope and setting overrides.

        Raises UndefinedSetting if key is not found and 'stop_search' is set,
        otherwise returns None.

        May raise 'ConfigException' if 'merge' is used and the key returns a
        value with a type that differs from that of 'merge'.
        """
        try:
            value = search_func(*args)
        except UndefinedSetting:
            if stop_search and merge is None:
                raise
            value = None

        if merge is not None:
            if value is None:
                value = merge
            elif isinstance(merge, list) and isinstance(value, list):
                value = list(set(value).union(set(merge)))
            elif isinstance(merge, dict) and isinstance(value, dict):
                # Prevents accidental modification of the original values if
                # same setting accessed multiple times at different scopes
                value = value.copy()
                for key in merge:
                    value[key] = merge[key]
            elif type(merge) == type(value):
                value = merge
            else:
                raise ConfigException(
                    "Can't resolve conflicting settings. "
                    f"Found settings formated as type {type(value)} and "
                    f"type {type(merge)}, which may indicate accidental "
                    "duplication of setting names."
                )
        return value

    def get_key(
        self, key, site=None, ignore_defaults=False, defaults_only=False
    ):
        """
        Searches the configuration from most specific settings to least to
        allow overrides + additional settings to be discovered.

        Searches from site (if given) -> study -> local system -> system wide

        If 'defaults_only' is used the search will restrict itself to system
        wide settings and local system settings (i.e. settings from the main
        config file)

        If 'ignore_defaults' is set the search is restricted to only site (if
        site was given) or only the current study (if site was not).

        Raises UndefinedSetting if no value is found
        """

        value = None
        if site and not defaults_only:
            value = self._get_setting(
                self._search_site_conf, [site, key], stop_search=ignore_defaults
            )
            if ignore_defaults:
                return value

        if self.study_config and not defaults_only:
            value = self._get_setting(
                self._search_study_conf,
                [key],
                stop_search=ignore_defaults,
                merge=value,
            )
            if ignore_defaults:
                return value

        value = self._get_setting(
            self._search_local_conf, [key], stop_search=False, merge=value
        )
        value = self._get_setting(
            self._search_system_conf, [key], stop_search=True, merge=value
        )
        return value

    @study_required
    def get_path(self, path_type, study=None):
        """returns the absolute path to a folder type"""
        paths = self.get_key("Paths")

        try:
            sub_dir = paths[path_type]
        except KeyError:
            raise UndefinedSetting(f"Path {path_type} not defined")

        return os.path.join(self.get_study_base(), sub_dir)

    @study_required
    def get_tags(self, site=None, study=None):
        """
        Returns a TagInfo instance.

        If you get the tags without a study set or without specifying a site
        you get the configuration of all defined tags from 'ExportSettings' in
        the system config file.

        If you specify a site, you get the configuration for that site merged
        with the configuration of 'ExportSettings' for the tags matching that
        site. If there's a key conflict between 'ExportInfo' (study config) and
        'ExportSettings' (system config) the values in 'ExportInfo' will
        override the values in 'ExportSettings'.
        """
        if site:
            export_info = self.get_key("ExportInfo", site=site)
        else:
            export_info = {}

        try:
            export_settings = self.get_key("ExportSettings")
        except UndefinedSetting:
            raise UndefinedSetting(
                "Tag dictionary 'ExportSettings' not "
                "defined in main configuration file."
            )

        return TagInfo(export_settings, export_info)

    @study_required
    def get_xnat_projects(self, study=None):
        xnat_projects = [
            self.get_key("XNAT_Archive", site=item) for item in self.get_sites()
        ]
        return list(set(xnat_projects))

    @study_required
    def get_sites(self, study=None):
        try:
            sites = list(self.get_key("Sites"))
        except KeyError:
            raise ConfigException(
                f"No sites defined for study {self.study_name}"
            )
        return sites

    @study_required
    def get_study_tags(self, study=None):
        """
        Returns a dictionary of study tags mapped to the sites defined for
        that tag.

        If a study has not been set then an exception is raised
        """
        try:
            default_tag = self.get_key("STUDY_TAG")
        except UndefinedSetting:
            logger.info(f"No default study tag defined for {self.study_name}")
            default_tag = None

        tags = {}
        tags[default_tag] = []

        for site, site_config in self.study_config["Sites"].items():
            # Some sites use both the default and a site_tag so every defined
            # site should be in the default list (if a default is defined)
            tags[default_tag].append(site)

            try:
                site_tags = site_config["SITE_TAGS"]
            except KeyError:
                continue

            if isinstance(site_tags, str):
                site_tags = [site_tags]

            for tag_name in site_tags:
                tags.setdefault(tag_name, []).append(site)

        return tags


class TagInfo(object):
    def __init__(self, export_settings, site_settings=None):
        if not site_settings:
            self.tags = export_settings
            return
        self.tags = self._merge_tags(export_settings, site_settings)

    def _merge_tags(self, export, site):
        tags = {}
        for entry in site:
            new_entry = {}
            site_info = site[entry]
            try:
                export_info = export[entry]
            except KeyError:
                logger.info(f"{entry} not defined in ExportSettings.")
                export_info = {}
            # Update with export info first, so that site_info will override it
            # if there's a key conflict
            new_entry.update(export_info)
            new_entry.update(site_info)
            tags[entry] = new_entry
        return tags

    @property
    def series_map(self):
        """
        Maps the 'pattern' fields onto the expected tags. If multiple patterns
        exist, they're joined with '|'.
        """
        series_map = {}
        for tag in self:
            try:
                pattern = self.get(tag, "Pattern")
            except KeyError:
                raise KeyError(
                    "Cant retrieve 'Pattern' from config. Did you "
                    "specify a site?"
                )
            if isinstance(pattern, list):
                pattern = "|".join(pattern)
            series_map[tag] = pattern
        return series_map

    def keys(self):
        return list(self.tags)

    def get(self, tag, field=None):
        try:
            tag_entry = self.tags[tag]
        except KeyError:
            raise KeyError(f"Series tag {tag} not defined")

        if field:
            try:
                field_val = tag_entry[field]
            except KeyError:
                raise KeyError(f"Tag {tag} does not define {field}")
            return field_val

        return tag_entry

    def __iter__(self):
        return self.tags.__iter__()

    def __repr__(self):
        return str(self.tags)
