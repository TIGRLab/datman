"""Return the site wide config file and ptoject config files

Usage:
    config.py [options] [<project>]

Arguments:
    <project>   Name of the project to return project specific config

Options:
    --site_config   Path to a site config file
                        [default: /archive/code/datman/assets/tigrlab_config.yaml]

"""
import logging
import yaml
import os
from . import scanid
from docopt import docopt

logging.basicConfig(level=logging.WARN)
logger = logging.getLogger(__name__)


class config(object):
    site_config = None
    study_config = None
    system_name = None

    def __init__(self, filename=None, system=None):
        if not filename:
            self.site_file = '/archive/code/datman/assets/tigrlab_config.yaml'
        else:
            self.site_file = filename

        self.site_config = self.load_yaml(self.site_file)

        if system:
            self.system_name = system
        else:
            self.system_name = 'kimel'

    def load_yaml(self, filename):
        ## Read in the configuration yaml file
        if not os.path.isfile(filename):
            raise ValueError("configuration file {} not found. Try again."
                             .format(filename))

        ## load the yml file
        with open(filename, 'r') as stream:
            config_yaml = yaml.load(stream)

        return config_yaml

    def set_study_config(self, project_name):
        # make the supplied project_name case insensitive
        valid_projects = {k.lower(): k
                          for k in self.site_config['ProjectSettings'].keys()}

        if project_name.lower() in valid_projects.keys():
            project_name = project_name.upper()
            system_settings = self.site_config['SystemSettings']
            config_path = system_settings[self.system_name]['CONFIG_DIR']

            project_settings_file = os.path.join(config_path,
                self.site_config['ProjectSettings'][project_name]['config_file'])

            self.study_config = self.load_yaml(project_settings_file)
        else:
            logger.error('Invalid project:{}'.format(project_name))
            raise KeyError

    def get_study_base(self, study=None):
        """Return the base directory for a study"""
        proj_dir = self.site_config['SystemSettings'][self.system_name]['DATMAN_PROJECTSDIR']
        if not study and self.study_config:
            logger.warning('Study not set')
            return(proj_dir)
        if not self.key_exists('site', ['ProjectSettings',
                                        study.upper(),
                                        'basedir']):
            logger.error('Invalid study:{}'.format(study))
            return(proj_dir)
        return(os.path.join(proj_dir,
                            self.site_config['ProjectSettings'][study.upper()]['basedir']))

    def map_xnat_archive_to_project(self, filename):
        """Maps the XNAT tag (e.g. SPN01) to the project name e.g. SPINS
        Can either supply a full filename in which case only the first part
        is considered or just a tag
        """
        try:
            parts = scanid.parse(filename)
            tag = parts.study
        except scanid.ParseException:
            parts = filename.split('_')
            tag = parts[0]

        for project in self.site_config['ProjectSettings'].keys():
            logger.debug('Searching project:{}'.format(project))
            self.set_study_config(project)
            # Check the study_config contains a 'Sites' key
            site_tags = []
            if 'Sites' in self.study_config.keys():
                for key, site_cfg in self.study_config['Sites'].iteritems():
                    try:
                        site_tags = site_tags + [t.lower()
                                                 for t
                                                 in site_cfg['SITE_IDS']]
                    except KeyError:
                        pass

            site_tags = site_tags + [self.study_config['STUDY_ID'].lower()]

            if tag.lower() in site_tags:
                if project.lower() == 'DTI':
                    # could be DTI15T or DTI3T
                    if type(parts) is list:
                        try:
                            site = parts[1]
                        except KeyError:
                            logger.error('Detected project DTI but '
                                         ' failed to identify using site')
                            return
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
        return

    def key_exists(self, scope, key):
        """Check the yaml file specified by scope for a key.
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
        """Check the yaml file specified by scope for a key.
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


if __name__ == '__main__':
    ARGUMENTS = docopt(__doc__)
