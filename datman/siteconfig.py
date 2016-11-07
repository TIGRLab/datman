"""
A class to make access to information in project_settings.yml files easier
and more uniform.

"""

import yaml

class SiteConfig(object):
    """
    Will raise an IOError exception if the given path does not exist or a
    YAMLError if the project-settings.yaml file is not a parseable yaml file.
    """
    def __init__(self, config_path):
        self.settings_path = config_path

        with open(config_path, 'r') as stream:
            config = yaml.load(stream)
            self.paths = config['paths']
            self.sites = config['Sites']
            self.pipeline_settings = config['PipelineSettings']

    def get_path(self, path_key):
        try:
            path = self.paths[path_key]
        except KeyError:
            path = ""
        return path

    def get_export_info(self, site_key):
        try:
            export_dict = self.sites[site_key]['ExportInfo']
        except KeyError:
            export_dict = {}
        return ExportInfo(export_dict)

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
