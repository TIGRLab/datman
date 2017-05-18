"""Return the site wide config file and ptoject config files

By default the site_config.yaml file is location is read from the
environment variable os.environ['DM_CONFIG']
The system is identified from os.environ['DM_SYSTEM']

These can both be overridden at __init__
"""
import logging
import yaml
import os
import datman.scanid

logger = logging.getLogger(__name__)


class config(object):
    site_config = None
    study_config = None
    system_config = None
    study_name = None
    study_config_file = None

    def __init__(self, filename=None, system=None, study=None):
        """Class object representing the site-wide configuration files.
        Inputs:
            filename - path to the site-wide config file (tigrlab_config.yaml)
                       If filename is not set will check the environment variable
                       DM_CONFIG (set during module load datman.module)
            system - Used to generate different paths when running on SCC or locally
                     Can be used to create test environments, checks environment variable
                    DM_SYSTEM if not set
            study - optional, limits searches to the defined study
            """

        if not filename:
            try:
                filename = os.environ['DM_CONFIG']
            except KeyError:
                logger.critical('Failed to find site_config file')
                raise

        self.site_config = self.load_yaml(filename)

        if not system:
            try:
                system = os.environ['DM_SYSTEM']
            except KeyError:
                logger.critical('Failed to identify current system')
                raise

        self.set_system(system)

        if study:
            self.set_study(study)

    def load_yaml(self, filename):
        ## Read in the configuration yaml file
        if not os.path.isfile(filename):
            raise ValueError("configuration file {} not found. Try again."
                             .format(filename))

        ## load the yml file
        with open(filename, 'r') as stream:
            config_yaml = yaml.load(stream)

        return config_yaml

    def set_system(self, system):
        if not self.site_config:
            logger.error('Site config not set')
            raise ValueError
        self.system_config = self.site_config['SystemSettings'][system]

    def set_study(self, study_name):
        # make the supplied project_name case insensitive
        valid_projects = {k.lower(): k
                          for k in self.site_config['Projects'].keys()}

        if study_name.lower() in valid_projects.keys():
            study_name = study_name.upper()
        else:
            study_name = self.map_xnat_archive_to_project(study_name)

        if not study_name:
            logger.error('Invalid project:{}'.format(study_name))
            raise KeyError

        self.study_name = study_name

        config_path = self.system_config['CONFIG_DIR']

        project_settings_file = os.path.join(config_path,
                                             self.site_config['Projects'][study_name])

        self.study_config = self.load_yaml(project_settings_file)
        self.study_config_name = project_settings_file

    def get_study_base(self, study=None):
        """Return the base directory for a study"""

        proj_dir = self.system_config['DATMAN_PROJECTSDIR']

        if study:
            self.set_study(study)

        if not self.study_config:

            logger.warning('Study not set')
            return(proj_dir)

        return(os.path.join(proj_dir,
                            self.study_config['PROJECTDIR']))

    def map_xnat_archive_to_project(self, filename):
        """Maps the XNAT tag (e.g. SPN01) to the project name e.g. SPINS
        Can either supply a full filename in which case only the first part
        is considered or just a tag.
        By default the project tag is extracted from the filename and matched
        to the "STUDY_TAG" in the study config file. If a study has used
        multiple site tags (e.g. SPN01, SPINS) these can be defined in the
        site specific [SITE_TAGS] key.
        One project tag (DTI) is shared between two xnat archives (DTI15TT and DTI3T)
        this is handled specially, the site is used to differentiate between
        them.
        """
        logger.debug('Searching projects for:{}'.format(filename))
        try:
            parts = datman.scanid.parse(filename)
            tag = parts.study
        except datman.scanid.ParseException:
            parts = filename.split('_')
            tag = parts[0]

        for project in self.site_config['Projects'].keys():
            # search each project for a match to the study tag,
            # this loop exits as soon as a match is found.
            logger.debug('Searching project:{}'.format(project))
            try:
                self.set_study(project)
                site_tags = []
                # Check the study_config contains a 'Sites' key,
                # this may contain site specific study names
                if 'Sites' in self.study_config.keys():
                    for key, site_cfg in self.study_config['Sites'].iteritems():
                        if 'SITE_TAGS' in site_cfg.keys():
                            site_tags = site_tags + [t.lower()
                                                     for t
                                                     in site_cfg['SITE_TAGS']]
            except (ValueError, KeyError):
                pass


            site_tags = site_tags + [self.study_config['STUDY_TAG'].lower()]

            if tag.lower() in site_tags:
                if project.lower() == 'DTI':
                    # could be DTI15T or DTI3T
                    if type(parts) is list:
                        try:
                            site = parts[1]
                        except KeyError:
                            logger.error('Detected project DTI but '
                                         ' failed to identify using site')
                            raise
                    else:
                        site = parts.site

                    if site == 'TGH':
                        project = 'DTI15T'
                    else:
                        project = 'DTI3T'

                return(project)
        # didn't find a match throw a worning
        logger.warn('Failed to find a valid project for xnat id:{}'
                    .format(tag))
        raise ValueError

    def get_key(self, key, scope=None, site=None):
        """recursively search the yaml files for a key
        if it exists in study_config returns that value
        otherwise checks site_config
        raises a key error if it's not found
        If site is specified the study_config first checks the
        ['Sites'][site] key of the study_config. If the key is not
        located there the top level of the study_config is checked
        followed by the site_config.
        key: [list of subscripted keys]
        """

        # quick check to see if a single string was passed
        if isinstance(key, basestring):
            key = [key]

        if scope:
            # called recursively, look in site config
            result = self.site_config
        elif self.study_config:
            # first call and study set, look here first
            result = self.study_config
        else:
            # first call and no study set, look at site config
            logger.warning('Study config not set')
            result = self.site_config
        if site:
            try:
                result = result['Sites'][site]
            except KeyError:
                logger.info('Site:{} not found in study_config:{}'
                               .format(site, self.study_config_file))

        for val in key:
            try:
                result = result[val]
            except KeyError as e:
                if site:
                    return(self.get_key(key))
                elif not scope:
                    return self.get_key(key, scope=1)
                else:
                    logger.warning('Failed to find key:{}'
                                   .format(key))
                    raise(e)
        return(result)

    def key_exists(self, scope, key):
            """DEPRECATED: use get_key()
            Check the yaml file specified by scope for a key.
            Return the True if the key exists, False otherwise.
            Scope [site | study]
            """
            if scope == 'site':
                # make a copy of the original yaml
                result = self.site_config
            else:
                result = self.study_config

            for val in key:
                try:
                    result = result[val]
                except KeyError:
                    return(False)

            return(True)

    def get_if_exists(self, scope, key):
        """DEPRECATED: use get_key()
        Check the yaml file specified by scope for a key.
        Return the value if the key exists, None otherwise.
        Scope [site | study]
        """
        if scope == 'site':
            # make a copy of the original yaml
            result = self.site_config
        else:
            result = self.study_config

        for val in key:
            try:
                result = result[val]
            except KeyError:
                return None

        return(result)

    def get_path(self, path_type, study=None):
        """returns the absolute path to a folder type"""
        # first try and get the path from the study config
        if study:
            self.set_study(study)
        if not self.study_config:
            logger.error('Study not set')
            raise KeyError

        try:
            return(os.path.join(self.get_study_base(),
                                self.study_config['paths'][path_type]))
        except (KeyError, TypeError):
            logger.info('Path {} not defined in study {} config file'
                        .format(path_type, self.study_name))
            return(os.path.join(self.get_study_base(),
                                self.site_config['paths'][path_type]))

    def get_exportinfo(self, site, study=None):
        """
        Takes the dictionary structure from project_settings.yaml and returns a
        pattern:tag dictionary.

        If multiple patterns are specified in the configuration file, these are
        joined with an '|' (OR) symbol.
        """
        if study:
            self.set_study(study)
        if not self.study_config:
            logger.error('Study not set')
            raise KeyError

        exportinfo = self.get_key(['ExportInfo'], site=site)
        if not exportinfo:
            return

        tags = exportinfo.keys()
        patterns = [tagtype["Pattern"] for tagtype in exportinfo.values()]

        regex = []
        for pattern in patterns:
            if type(pattern) == list:
                regex.append(("|").join(pattern))
            else:
                regex.append(pattern)

        tagmap = dict(zip(regex, tags))

        return(tagmap)

    def get_xnat_projects(self, study=None):
        if study:
            study = self.set_study(study)
        if not self.study_config:
            logger.error('Study not set')
            raise KeyError

        xnat_projects = [site['XNAT_Archive']
                         for site in self.get_key(['Sites']).values()]

        return(xnat_projects)

    def get_export_info_object(self, site, study=None):
        """
        Takes the dictionary structure from project_settings.yaml and returns a
        pattern:tag dictionary.

        If multiple patterns are specified in the configuration file, these are
        joined with an '|' (OR) symbol.
        """
        if study:
            self.set_study(study)
        if not self.study_config:
            logger.error('Study not set')
            raise KeyError

        exportinfo = self.get_key(['ExportInfo'], site=site)
        if not exportinfo:
            logger.error('Failed to get Export info for study:{} at site:{}'
                         .format(self.study_name, site))
            exportinfo = {}
        return ExportInfo(exportinfo)

    def get_qced_subjects(self):
        """
        Returns a dictionary of all the subjects that have been signed off on
        for a study. The'value' field for each subject is an empty list.

        Why a dictionary?
            1. Dicts dont allow duplicate keys, so it handles redundant
            checklist entries easily.
            2. It makes it easy and efficient to keep track of additional data
            on a per subject basis, e.g. all series a subject has
            3. Dicts can be treated like a list, so if the 'value' for
            each subject 'key' isn't needed it can just be ignored.
        """
        checklist_path = os.path.join(self.get_path('meta'), 'checklist.csv')
        if not os.path.isfile(checklist_path):
            raise ValueError("Checklist {} not found".format(checklist_path))

        qced_subjects = {}
        with open(checklist_path, 'r') as checklist:
            for entry in checklist:
                fields = entry.split(None, 1)
                if len(fields) < 2:
                    continue
                subid, _ = os.path.splitext(fields[0].strip('qc_'))
                qced_subjects[subid] = []
        return qced_subjects

    def get_blacklist(self):
        """
        Returns a dictionary mapping the subject id to a list of its blacklisted
        series. A subject id will not appear in the key list if none of that
        subject's data has been blacklisted.

        Blacklist entries with file names that violate the datman convention
        will be skipped.
        """
        blacklist_path = os.path.join(self.get_path('meta'), 'blacklist.csv')
        if not os.path.isfile(blacklist_path):
            raise ValueError("Blacklist {} not found.".format(blacklist_path))

        blacklist = {}
        with open(blacklist_path, 'r') as blacklist_file:
            header_line = blacklist_file.readline()
            for entry in blacklist_file:
                fields = entry.split(None, 1)
                try:
                    ident, _, _, _ = datman.scanid.parse_filename(fields[0])
                except datman.scanid.ParseException:
                    logger.warn("Bad subject id in series. Ignoring "
                            "blacklist entry {}".format(entry))
                    continue
                subid = ident.get_full_subjectid_with_timepoint()
                blacklist.setdefault(subid, []).append(fields[0])
        return blacklist

    def get_subject_metadata(self):
        """
        Returns a dictionary of all qced subjects, with any blacklisted
        series mapped to the subject id.
        """
        qced_subjects = self.get_qced_subjects()
        blacklist = self.get_blacklist()

        # Update is not used because it will add keys
        # That is, if a subject has NOT been signed off but has a blacklist
        # entry update would add them to qc'd subjects, which is not desirable.
        for subject in blacklist:
            try:
                qced_subjects[subject] = blacklist[subject]
            except KeyError:
                continue
        return qced_subjects

class ExportInfo(object):
    """
    Simplifies access to an export info dictionary
    """
    def __init__(self, export_dict):
        self.export_info = export_dict
        self.tags = export_dict.keys()

    def get_tag_info(self, tag):
        try:
            tag_info = self.export_info[tag]
        except KeyError:
            tag_info = {}
        return tag_info
