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
            raise ValueError("configuration file {} not found. Try again.".format(filename))

        ## load the yml file
        with open(filename, 'r') as stream:
            config_yaml = yaml.load(stream)

        return config_yaml

    def set_study_config(self, project_name):
        # make the supplied project_name case insensitive
        valid_projects = {k.lower(): k for k in self.site_config['Projects'].keys()}
        if project_name.lower() in valid_projects.keys():
            base_path = self.site_config['SystemSettings'][self.system_name]['DATMAN_PROJECTSDIR']
            project_path = self.site_config['Projects'][valid_projects[project_name.lower()]]
            project_path = project_path.replace('<DATMAN_PROJECTSDIR>', base_path)
            self.study_config = self.load_yaml(os.path.join(project_path,
                                                            'metadata',
                                                            'project_settings.yml'))
if __name__ == '__main__':
    ARGUMENTS = docopt(__doc__)
