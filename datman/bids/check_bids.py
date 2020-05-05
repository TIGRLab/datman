#!/usr/bin/env python
"""
Class to parse and deal with requirements
    enforced by the BIDS naming convention
Data is read off a YAML configuration file that specifies
    the constraints and requirements
of each class of MR data within the BIDS framework
"""

import logging
import os

import yaml

logging.basicConfig(
    level=logging.WARN, format="[%(name)s %(levelname)s: %(message)s]",
)
logger = logging.getLogger(os.path.basename(__file__))

KEYLESS_FIELDS = ["modality_label", "contrast_label"]


class BIDSEnforcer(object):
    def __init__(self, yml_file):

        with open(yml_file, "r") as stream:
            self.descriptor = yaml.load(stream, Loader=yaml.SafeLoader)

        try:
            self.version = self.descriptor["VERSION"]
        except KeyError:
            logger.error(
                "No version indicated in BIDS syntax description file!"
            )
            logger.error(f"Add a VERSION key to {yml_file}")

        self.inverse_map = self._invert_descriptor_map()
        self.run_counter = {}

    def construct_bids_name(self, input_dict):
        """
        Receive a dictionary with input mappings (available in yaml)
        then apply input constraints to ensure compliance with BIDS
        naming standards

        Run has special behaviour where if not explicitly provided via dict
        then perform internal run counting
        """

        mode = input_dict["class"]
        input_constructor = []
        use_internal_run = False

        if "run" not in input_dict.keys():
            use_internal_run = True

        for m, f in self._get_mode_gen(mode):

            req_or_opt = self.inverse_map[m][f]

            try:
                entry = input_dict[f]
            except KeyError:
                if req_or_opt == "required":
                    logger.error(f"Missing required input: {f}")
                    logger.error(f"Input dict: {input_dict}")
                    raise
            else:
                if f not in KEYLESS_FIELDS:
                    input_constructor.append(f"{f}-{entry}")
                else:
                    input_constructor.append(entry)

        if use_internal_run:
            run = self._get_run_count(tuple(input_constructor))
            input_constructor.insert(-1, f"run-{run}")

        return "_".join(input_constructor)

    def _get_run_count(self, hashable):
        """
        Increment run counter and return run string
        """

        try:
            self.run_counter[hashable] += 1
        except KeyError:
            self.run_counter[hashable] = 1

        return self.run_counter[hashable]

    def _make_field_list(self, field, mode):
        """
        Makes a field list and applies reference matching if required
        """

        if "@" in field[0]:
            ref, var = field.strip("@").split(".")
            return (ref, var)
        else:
            return (mode, field)

    def _get_mode_gen(self, mode):
        """
        Iterate through order
        """

        field_list = [("global", o) for o in self.descriptor["global"]["order"]]

        try:
            mode_field_list = self.descriptor[mode]["order"]
        except KeyError:
            yield []

        field_list.extend(
            [self._make_field_list(o, mode) for o in mode_field_list]
        )

        for m, f in field_list:

            yield m, f

    def _invert_descriptor_map(self):
        """
        Invert the mapping for easier required/optional assignment
        Alternatively enumerate the list to get natural ordering... via dict
        """

        output_dict = {}
        for mode, key in self.descriptor.items():

            if mode == "VERSION":
                continue

            output_dict[mode] = {}
            mode_dict = self.descriptor[mode]

            inverse_dict_required = {
                k: "required" for k in mode_dict["required"].keys()
            }
            inverse_dict_optional = {
                k: "optional" for k in mode_dict["optional"].keys()
            }
            output_dict[mode].update(inverse_dict_required)
            output_dict[mode].update(inverse_dict_optional)

        return output_dict
