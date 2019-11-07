#!/usr/bin/env python
"""
Finds phantoms on XNAT and renames them to our new naming scheme:
STUDY_SITE_PHA_TYPEYYYYMMDD. It will also remove any copies of the phantom
under the old name from the file system.

This will find phantoms even if they dont adhere to the datman scheme at all,
as long as either the patient name or patient ID field contains one of the
search following terms:
    - '-pha-'
    - '_pha_'
    - 'phantom'
    - 'agar'.
The search is case insensitive.

Usage:
    dm_pha_rename.py [options] <study>

Arguments:
    <study>             The datman study that should be worked on

Options:
    --write <csv_output>            Dont rename anything, but instead dump all
                                    name changes that would have been made to a
                                    csv named <output>, formatted as
                                    'old_name,new_name' with one entry per
                                    line.

    --read <csv_input>              Dont search for phantoms, instead read name
                                    changes from the csv <input>, formatted as
                                    'old_name,new_name' with one entry per
                                    line.

    --track-history <csv_record>    Use this option for repeated runs of the
                                    script. Every subject in the study will
                                    be entered into the list after it has
                                    been seen once. Unchanged subjects will
                                    be entered with the same name in each
                                    column, changed ones will have their
                                    original ID in the first column and their
                                    'post-rename' ID in the second column. Any
                                    XNAT session matching an ID in the second
                                    column will be ignored in every subsequent
                                    run of this script.

    --debug,d
    --verbose,v
    --quiet,q

"""

from docopt import docopt

import datman.config
import datman.scanid
import datman.xnat
import dm_xnat_rename as rename
from datman.scanid import ParseException

def main():
    arguments = docopt(__doc__)

    # set log level (dont forget xnat_rename logger level)

    # If track history, set global flag
    # If read or track changes parse the csv and turn into dict of old -> new

    # Get xnat project names for the given study
    # for xnat project in projects:
    #   Get all xnat sessions (Use the dict, if it exists, to remove entries)
    #           -> If read, remove entries that DONT match dict keys
    #           -> If track-history, remove entries that DO match dict values
    #   For xnat session in session list:
    #       If is_phantom:
    #           Add to list of phantoms to rename
    #       else continue

    # Use list of phantoms + 'generate_id' function to get dict of orig_name -> new_name

    # If write, format into csv and end

    # Use xnat_rename to rename all, and report failed renames +
    # if track history remove failed renames from list before csv write

    # If track history, add to existing csv and continue


def get_xnat_projects(study):
    return


def get_xnat(server, user, password):
    if not server:
        config = datman.config.config()
        server = datman.xnat.get_server(config)
    if not user or not password:
        user, password = datman.xnat.get_auth()
    return datman.xnat.xnat(server, user, password)

studies = ['OPT01_UT', 'OPT01_LA', 'OPT01_UP', 'OPT01_CU', 'OPT01_WU']

study = "OPT01_UT"

xnat = get_xnat(None, None, None)
sessions = xnat.get_sessions(study)


def is_phantom(xnat_sess):
    try:
        ident = datman.scanid.parse(xnat_sess.name)
    except ParseException:
        pass
    else:
        return datman.scanid.is_phantom(ident)
    patient_id = xnat_sess.experiment['data_fields']['dcmPatientId'].lower()
    patient_name = xnat_sess.experiment['data_fields']['dcmPatientName'].lower()
    if '-pha-' in patient_id or '-pha-' in patient_name:
        return True
    if '_pha_' in patient_id or '_pha_' in patient_name:
        return True
    if 'phantom' in patient_id or 'phantom' in patient_name:
        return True
    if 'agar' in patient_id or 'agar' in patient_name:
        return True
    return False
