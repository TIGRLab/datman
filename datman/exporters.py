"""Functions to export data into different file formats and organizations.

To allow datman to export to a new format add a new function here
and then add it to the exporters dictionary.
"""
from abc import ABC, abstractmethod
import os

# EXPORTERS = {
#     "nii": export_nii,
#     "bids": export_bids,
#     "mnc": export_mnc,
#     "dcm": export_dcm,
#     "nrrd": export_nrrd
# }


class Exporter(ABC):

    type_key = None  # This should be the shorthand name used in config files
    ext = None  # Can optionally provide a file extension.

    def output_exists(self):

        return

    @abstractmethod
    def export(self, *args, **kwargs):
        """Implement to convert input data to this exporter's output type.
        """
        pass

    def __init__(self, input_dir, output_dir, fname_root):
        self.input = input_dir
        self.output_dir = output_dir
        self.fname_root = fname_root

    def __repr__(self):
        fq_name = str(self.__class__).replace("<class '", "").replace("'>", "")
        name = fq_name.split(".")[-1]
        return f"<{name} - '{self.input}'>"


class NiiExporter(Exporter):

    type_key = "nii"

    def output_exists(self):

        return

    def export(self):
        return
