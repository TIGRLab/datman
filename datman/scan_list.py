#!/usr/bin/env python
"""
This script contains code to generate a scans.csv for instances where the
subject ID in the dicom headers is wrong in a systematic way. That is,
this script can be used when the dicom headers and/or file name contains enough
information to derive a correct datman ID, but the PatientName field is not
already formatted that way.

To make use of this script, a ScanEntry class must be created.
"""
import os
import cPickle
import logging

# import datman.config
# import datman.utils

logger = logging.getLogger(os.path.basename(__file__))

# This program saves the previous state (if any) for faster execution later on
# It will show up as a hidden file in the destination folder
PREV_STATE = ".scans_renamed.pickle"

# def main():
#     arguments = docopt(__doc__)
#     dest_dir = arguments['--out']
#     verbose = arguments['--verbose']
#     debug = arguments['--debug']
#
#     if verbose:
#         logger.setLevel(logging.INFO)
#     if debug:
#         logger.setLevel(logging.DEBUG)
#
#     config = datman.config.config(study=STUDY)
#
#     if not dest_dir:
#         dest_dir = config.get_path('meta')
#
#     output = os.path.join(dest_dir, 'scans.csv')
#
#     if not os.path.exists(output):
#         start_new_scan_list(output)
#
#     try:
#         processed_scans = get_processed_data(dest_dir)
#     except Exception as e:
#         logger.error("Can't read saved state. Reason: {}".format(e.message))
#         processed_scans = {}
#
#     add_new_scans(output, processed_scans, config)

def start_new_scan_list(output):
    logger.info("Starting new scans.csv file at {}".format(output))
    with open(output, 'w') as out:
        out.write('source_name\ttarget_name\tPatientName\tStudyID\n')

def get_processed_data(dest_dir):
    saved_state = os.path.join(dest_dir, PREV_STATE)
    if not os.path.exists(saved_state):
        logger.debug("No saved state to read. Processing all scans.")
        return {}

    logger.info("Loading list of processed scans from {}".format(saved_state))
    with open(saved_state, 'rb') as contents:
        processed_data = cPickle.load(contents)

    return processed_data

def add_new_scans(output, processed_scans, config):
    zip_dir = config.get_path('zips')

    new_entries = []
    for fname in os.listdir(zip_dir):
        if not fname.endswith('.zip'):
            continue

        zip_file = os.path.join(zip_dir, fname)
        if zip_file in processed_scans:
            continue

        try:
            entry = ScanEntry(zip_file)
        except IndexError:
            logger.error("{} does not contain dicoms. Setting scans.csv "
                    "to ignore file.".format(zip_file))
            cols = [os.path.basename(zip_file).replace('.zip', ''), '<ignore>',
                    '<ignore>', '<ignore>', '\n']
            entry = None
        except Exception as e:
            logger.error("Cant make an entry for {}. Reason: {}".format(zip_file,
                    e.message))
            continue
        else:
            cols = [entry.source_name, entry.get_target_name(),
                    entry.patient_name, entry.study_id + '\n']

        new_entries.append('\t'.join(cols))
        processed_scans[zip_file] = entry

    logger.debug("Writing {} new entries to scans file".format(len(new_entries)))
    if new_entries:
        update_scans_csv(output, new_entries)
        save_state(processed_scans, output)

    return processed_scans

def update_scans_csv(output, new_entries):
    with open(output, 'a') as scan_csv:
        scan_csv.writelines(new_entries)

def save_state(processed_scans, output):
    output_loc = os.path.dirname(output)
    state_file = os.path.join(output_loc, PREV_STATE)
    logger.debug("Saving state to {}".format(state_file))
    with open(state_file, 'wb') as output:
        cPickle.dump(processed_scans, output)

class ScanEntry(object):

    def __init__(self, scan_path):
        header = datman.utils.get_archive_headers(scan_path,
                stop_after_first=True).values()[0]
        self.site = self._get_site(header.get('InstitutionName'))
        self.source_name = os.path.basename(scan_path).replace('.zip', '')
        self.patient_name = header.get('PatientName')
        self.id = self._get_id(self.patient_name)
        self.study_id = header.get('StudyID')

    def get_target_name(self):
        return "_".join(['NEUR', self.site, self.id, '01', '01'])

    def _get_site(self, ins_name):
        if ins_name == 'CAMH':
            return 'CMH'
        if ins_name is not None and 'York' in ins_name:
            return 'YU'
        raise RuntimeError("Can't identify site from institution name: "
            "{}".format(ins_name))

    def _get_id(self, patient_name):
        if self.site == 'CMH':
            return patient_name
        try:
            # Patient name for York seems to be "id_date", so gotta split it
            p_id = patient_name.split('_')[0]
        except IndexError:
            p_id = patient_name
        try:
            int(p_id)
        except ValueError:
            # If the field has 'HCT' or 'SCZ' prepended it'll raise an exception
            # and can be used as is
            pass
        else:
            # Prepend the correct group
            first_digit = str(p_id)[0]
            if first_digit == '1':
                p_id = 'SCZ' + str(p_id)
            elif first_digit == '2':
                p_id = 'HCT' + str(p_id)
            else:
                logger.info("Cannot determine group from patient name: "
                        "{}. Setting ID to: {}".format(patient_name, p_id))
        return p_id

# if __name__ == "__main__":
#     main()
