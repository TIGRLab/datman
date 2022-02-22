#!/usr/bin/env python
"""ABCD Nback Task Parser

Converts eprime text file for ABCD Nback task into BIDS .tsv files.

Usage:
    dm_parse_Nback_abcd.py [options] <study>
    dm_parse_Nback_abcd.py [options] <study> [<session>]...

Arguments:
    <study>     Name of the study to process e.g. OPT
    <session>   Datman name of session to process e.g. OPT01_UP1_UP10044_02_01

Options:
    --output-dir OUT_DIR    Specify an alternate output directory
                            [Default:
                            $DATMAN_PROJECTSDIR/{study}/data/nii/{session}]
    --verbose               Set log level to display INFO messages
    --debug                 Set log level to debug
    --quiet                 Do not output logging messages
    --dry-run               Perform a run but do not create outputs

Outputs the trial number, onset time, accurracy, and reaction time values
for each trial.
"""

from docopt import docopt
import codecs
import logging
import pandas as pd
import numpy as np
import re
import os
import glob

import datman.config
import datman.scanid

logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))


def read_eprime(eprimefile):
    '''
    Read in ePrime file with appropriate encoding
    '''
    encodings = ['utf-16', 'utf-16-be', 'utf-16-le']

    for enc in encodings:
        try:
            eprime = codecs.open(eprimefile, "r", encoding=enc, errors="strict")
            lines = []
            for line in eprime:
                lines.append(str(line))
            if lines and 'Header Start' in lines[0]:
                return lines
        except UnicodeError:
            logging.info(f"Failed to read {eprimefile} with {enc} encoding.")
            continue

    raise UnicodeError('Unable to find appropriate encoding')


def find_all_data(eprime, tag):
    '''
    Identify line numbers and content containing {tag}
    '''
    dataset = [(i, s) for i, s in enumerate(eprime) if tag in s]
    return dataset


def findnum(ln):
    try:
        txtnum = re.findall('(\d+)\r\n', ln)  # noqa: W605
        return float(txtnum[0])
    except ValueError:
        return txtnum[0]
    except IndexError:
        logger.error("Found unexpected empty line in ePrime file!")
        logger.error(
            "Please check ePrime file for corrupted and/or empty lines!")
        raise


def findalphanum(ln):

    if event_is_empty(ln):
        return np.nan
    try:
        txtnum = re.findall('(?<=: )[A-Za-z0-9]+', ln)[0]
    except IndexError:
        logger.error("Expected alphanumeric values!")
        logger.error(f"Value found is unexpected!: {ln}")
        raise
    return txtnum


def get_event_value(eprime, event):

    events = find_all_data(eprime, event)
    if not events:
        return np.nan
    elif len(events) > 1:
        logger.error("Was expecting only one event, but received multiple!")
        raise ValueError

    return findalphanum(events[0][1])


def get_event_response(eprime, rsp_event):
    resp = get_event_value(eprime, rsp_event)
    return map_response(resp)


def event_is_empty(e):
    return e.strip().endswith(':')


def map_response(x):
    '''
    Some ABCD Nback task files use "a", "b", "c" and "d" instead of 1,2,3,4
    '''

    if pd.isnull(x):
        return x

    if x.isdigit():
        return x

    mapdict = {'a': 1, 'b': 2, 'c': 3, 'd': 4}
    try:
        res = int(mapdict[x])
    except KeyError:
        logger.error(f"Value \'{x}\' is neither numeric nor matches 'a-d'")

    return res


def main():

    arguments = docopt(__doc__)
    out_dir = arguments['--output-dir']
    sessions = arguments['<session>']
    study = arguments['<study>']
    verbose = arguments["--verbose"]
    debug = arguments["--debug"]
    quiet = arguments["--quiet"]
    dryrun = arguments["--dry-run"]

    if verbose:
        logger.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)
    if quiet:
        logger.setLevel(logging.ERROR)

    if dryrun:
        logger.info("Dry run - will not write any output")

    config = datman.config.config(study=study)

    task_path = config.get_path("task")
    nii_path = config.get_path("nii")

    if not sessions:
        sessions = os.listdir(task_path)
    elif not isinstance(sessions, list):
        sessions = [sessions]

    logger.debug(f"Running ABCD Nback parser for {len(sessions)} session(s):")
    logger.debug(f"Out dir: {out_dir}")

    for ses in sessions:
        logger.info(f"Parsing {ses}...")

        try:
            ident = datman.scanid.parse(ses)
        except datman.scanid.ParseException:
            logger.error(f"Skipping task folder with malformed ID {ses}")
            continue
        ses_path = os.path.join(task_path, ses)

        task_files = glob.glob(ses_path + '/*.txt')
        if not task_files:
            logger.warning(f"No .txt files found for {ses}, skipping.")
            continue

        for eprimefile in task_files:
            logger.info(f"Found file: {eprimefile}")
            try:
                eprime = read_eprime(eprimefile)
            except UnicodeError as e:
                logger.error(f"Cannot parse {eprimefile}: {e}")
                continue

            init_tag = find_all_data(eprime, "Procedure: InitialTR\r\n")
            init_start = np.empty([len(init_tag)], dtype=int)
            init_end = np.empty([len(init_tag)], dtype=int)

            for i, ind_init in enumerate(init_tag):
                if i < len(init_tag) - 1:
                    init_end[i] = init_tag[i + 1][0]
                elif i == len(init_tag) - 1:
                    init_end[i] = len(eprime) - 1
                init_start[i] = ind_init[0]

            # tag the trials to obtain the data for each trial
            taglist = find_all_data(eprime, "Procedure: TrialsPROC\r\n")

            if not taglist:
                logger.error(f"No trials found for {ses} - skipping")
                continue

            trial_start = np.empty([len(taglist)], dtype=int)
            trial_end = np.empty([len(taglist)], dtype=int)

            for i, ind_trial_proc in enumerate(taglist):
                if (i < (len(taglist)) - 1):
                    trial_end[i] = taglist[i + 1][0]
                elif (i == (len(taglist)) - 1):
                    trial_end[i] = len(eprime) - 1

                trial_start[i] = ind_trial_proc[0]

            trial_blocks = [
                eprime[s:e] for s, e in zip(trial_start, trial_end)
            ]

            entries = []
            for b in trial_blocks:
                stimOT = get_event_value(b, 'Stim.OnsetTime:')
                # Convert from ms to seconds
                rel_stimOT = float(stimOT) / 1000
                duration = float(get_event_value(
                    b, 'Stim.OnsetToOnsetTime:')) / 1000
                response_time = float(get_event_value(b, 'Stim.RT:')) / 1000
                entries.append({
                    'onset':
                    rel_stimOT,
                    'duration':
                    duration,
                    'run_type':
                    'Run1' if 'Run1' in str(b) else 'Run2' if 'Run2' in str(b)
                        else np.nan,
                    'trial_type':
                    get_event_value(b, "BlockType:"),
                    'response_time':
                    response_time,
                    'accuracy':
                    get_event_value(b, 'Stim.ACC:'),
                    'correct_response':
                    map_response(get_event_value(b, 'CorrectResponse:')),
                    'participant_response':
                    map_response(get_event_value(b, 'Stim.RESP:'))
                })

            data = pd.DataFrame.from_dict(entries)\
                .astype({
                    "onset": np.float64,
                    "duration": np.float64,
                    "response_time": np.float64,
                    "accuracy": np.float64,
                    "correct_response": np.float64,
                    "participant_response": np.float64
                })\
                .astype({
                    "correct_response": "Int64",
                    "participant_response": "Int64",
                    "accuracy": "Int64"
                })

            data['run_type'].fillna(method='ffill', inplace=True)

            if not out_dir:
                out_path = os.path.join(
                    nii_path, ident.get_full_subjectid_with_timepoint())
            else:
                out_path = out_dir

            file_name = os.path.join(out_path, f"{ses}_Nback_abcd.tsv")

            if not dryrun:
                logger.info(f"Saving output to {file_name}")
                os.makedirs(os.path.dirname(file_name), exist_ok=True)
                data.to_csv(file_name, sep='\t', index=False)
            else:
                logger.info(f"Dry run - would save to {file_name}")


if __name__ == '__main__':
    main()
