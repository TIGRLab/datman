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
from docopt import docopt

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARN)


class config:
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
                self.site_config['ProjectSettings'][project_name]['basedir'],
                self.site_config['ProjectSettings'][project_name]['config_file'])

            self.study_config = self.load_yaml(project_settings_file)


def map_xnat_archive_to_project(archive, **kwargs):
    """Maps the XNAT tag (e.g. SPN01) to the project name e.g. SPINS"""
    cfg = config(**kwargs)

    for project in cfg.site_config['ProjectSettings'].keys():
        cfg.set_study_config(project)
        for site in cfg.study_config['Sites']:
            if site['XNAT_ID'].lower() == archive.lower():
                return(project)
    # didn't find a match throw a worning
    logger.warn('Failed to find a valid project for xnat id:{}'
                .format(archive))
    return

if __name__ == '__main__':
    ARGUMENTS = docopt(__doc__)
