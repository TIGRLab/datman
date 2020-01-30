#!/usr/bin/env python
"""
This script contains code to generate a scans.csv for instances where the
subject ID in the dicom headers is wrong in a systematic way. That is,
this script can be used when the dicom headers and/or file name contains enough
information to derive a correct datman ID, but the PatientName field is not
already formatted that way.

To make use of this library, the calling script should create a subclass of
ScanEntryABC and define the function get_target_name() to return the intended
datman ID. generate_scan_list() can then be called by passing in this class,
a list of zip files and the destination directory for the scans.csv file.

Example:

class ExampleScanEntry(datman.scan_list.ScanEntryABC):

    def __init__(self, scan_path):
        super(ExampleScanEntry, self).__init__(scan_path)

    def get_target_name(self):
        ... (code to generate correct datman ID goes here) ...
        return datman_id

datman.scan_list.generate_scan_list(ExampleScanEntry,
                                    my_zip_list,
                                    metadata_path)
"""
import os
import logging
from abc import ABCMeta, abstractmethod
from collections import defaultdict

from datman.utils import get_archive_headers

logger = logging.getLogger(os.path.basename(__file__))


def generate_scan_list(scan_entry_class, zip_files, dest_dir):
    """
    Use this function to generate a scans.csv file of the expected format.

    scan_entry_class:       A subclass of ScanEntryABC that will be used to
                            generate each entry in scans.csv

    zip_files:              A list of zip files to manage

    dest_dir:               The directory where scans.csv will be saved
    """

    output = os.path.join(dest_dir, "scans.csv")

    if not os.path.exists(output):
        start_new_scan_list(output)

    try:
        processed_scans = get_scan_list_contents(output)
    except Exception as e:
        raise RuntimeError("Can't read scan entries from existing scans.csv "
                           "file. Reason: {}".format(e))

    new_entries = make_new_entries(processed_scans, zip_files,
                                   scan_entry_class)

    logger.debug("Writing {} new entries to scans file".format(
                                                        len(new_entries)))
    if new_entries:
        update_scans_csv(output, new_entries)


def start_new_scan_list(output):
    logger.info("Starting new scans.csv file at {}".format(output))
    with open(output, 'w') as out:
        out.write('source_name\ttarget_name\tPatientName\tStudyID\n')


def get_scan_list_contents(scans_csv):
    with open(scans_csv, "r") as scan_entries:
        contents = scan_entries.readlines()

    processed_files = defaultdict(list)
    # Skip first line because it's a header
    for line in contents[1:]:
        scan_entry = line.strip().split()
        if not scan_entry:
            # Skip blank lines
            continue
        try:
            scan_name = scan_entry[0]
        except IndexError:
            raise IndexError("Malformed scan entry: {}".format(line))
        processed_files[scan_name].append(line)

    return processed_files


def make_new_entries(processed_scans, zip_files, EntryClass):
    new_entries = []
    for zip_file in zip_files:
        if not zip_file.endswith('.zip'):
            continue

        zip_name = os.path.basename(zip_file).replace(".zip", "")
        if zip_name in processed_scans:
            continue

        try:
            entry = EntryClass(zip_file)
        except Exception as e:
            logger.error("Cant make an entry for {}. Reason: {}".format(
                                                        zip_file,
                                                        e))
            continue

        new_entries.append(str(entry))

    return new_entries


def update_scans_csv(output, new_entries):
    with open(output, 'a') as scan_csv:
        scan_csv.writelines(new_entries)


class ScanEntryABC(object, metaclass=ABCMeta):

    def __init__(self, scan_path):
        self.source_name = os.path.basename(scan_path).replace('.zip', '')
        try:
            header = list(get_archive_headers(scan_path,
                                              stop_after_first=True).values()
                          )[0]
        except IndexError:
            logger.debug("{} does not contain dicoms. "
                         "Creating 'ignore' entry.".format(scan_path))
            self.patient_name = "<ignore>"
            self.study_id = "<ignore>"
            self.header = None
        else:
            self.header = header
            self.patient_name = str(header.get('PatientName'))
            self.study_id = str(header.get('StudyID'))

    @abstractmethod
    def get_target_name(self):
        pass

    def __str__(self):
        return "\t".join([self.source_name, self.get_target_name(),
                          self.patient_name, self.study_id + "\n"])
