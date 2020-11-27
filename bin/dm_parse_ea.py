#!/usr/bin/env python

"""
Parses SPINS' EA log files into BIDS tsvs.

Usage:
    dm_parse_ea.py [options] <study>

Arguments:
    <study>                     A datman study to parse task data for.

Options:
    --timings <timing_path>     The full path to the EA timings file.
                                Defaults to the 'EA-timing.csv' file in
                                the assets folder.
    --lengths <lengths_path>    The full path to the file containing the
                                EA vid lengths. Defaults to the
                                'EA-vid-lengths.csv' in the assets folder.
    --regex <regex>             The regex to use to find the log files to
                                parse. [default: *UCLAEmpAcc*]
"""


import re
import os
import glob
import logging

import pandas as pd
import numpy as np
from docopt import docopt

import datman.config
import datman.scanid

logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))


# reads in log file and subtracts the initial TRs/MRI startup time
def read_in_logfile(path):
    log_file = pd.read_csv(path, sep='\t', skiprows=3)

    time_to_subtract = int(log_file.Duration[log_file.Code == 'MRI_start'])

    # subtracts mri start times from all onset times
    log_file.Time = log_file.Time - time_to_subtract

    return log_file


# Grabs the starts of blocks and returns rows for them
def get_blocks(log, vid_info):
    # identifies the video trial types (as opposed to button press events etc)
    mask = ["vid" in log['Code'][i] for i in range(0, log.shape[0])]

    # creates the dataframe with onset times and event types
    df = pd.DataFrame({
        'onset': log.loc[mask]['Time'],
        'trial_type': log.loc[mask]['Event Type'],
        'movie_name': log.loc[mask]['Code']})
    # adds trial type info
    df['trial_type'] = df['movie_name'].apply(
        lambda x: "circle_block" if "cvid" in x else "EA_block")
    # add durations and convert them into the units used here
    df['duration'] = df['movie_name'].apply(
        lambda x: int(vid_info[x]['duration']) * 10000 if
        x in vid_info else "n/a")
    # adds names of stim_files, according to the vid_info spreadsheet
    df['stim_file'] = df['movie_name'].apply(
        lambda x: vid_info[x]['stim_file'] if x in vid_info else "n/a")
    # adds an end column to the beginning of blocks (it's useful for
    # processing but will remove later)
    df['end'] = df['onset'] + df['duration']
    return df


# grabs stimulus metadata
def format_vid_info(vid):
    vid.columns = [c.lower() for c in vid.columns]
    # grabs the file name and the durations from the info file
    vid = vid.rename(index={0: "stim_file", 1: "duration"})
    vid = vid.to_dict()
    return(vid)


# Reads in gold standard answers
def read_in_standard(timing_path):
    df = pd.read_csv(timing_path).astype(str)
    df.columns = [c.lower() for c in df.columns]
    # drops the video name
    df_dict = df.drop([0, 0]).reset_index(drop=True).to_dict(orient='list')
    return(df_dict)


# grabs gold standards as a series
def get_series_standard(gold_standard, block_name):
    return([float(x) for x in gold_standard[block_name] if x != 'nan'])


# grabs partcipant ratings
def get_ratings(log):

    rating_mask = ["rating" in log['Code'][i] for i in range(0, log.shape[0])]

    # gives the time and value of the partiicipant rating
    df = pd.DataFrame({
        'onset': log['Time'].loc[rating_mask].values,
        'participant_value': log.loc[rating_mask]['Code'].values,
        'event_type': 'button_press',
        'duration': 0})

    # gets rating substring from participant numbers
    df['participant_value'] = df['participant_value'].str.strip().str[-1]

    return(df)


# combines the block rows with the ratings rows and sorts them
def combine_dfs(blocks, ratings):
    combo = blocks.append(ratings).sort_values("onset").reset_index(drop=True)
    mask = pd.notnull(combo['trial_type'])
    combo['space_b4_prev'] = combo['onset'].diff(periods=1)
    combo['first_button_press'] = combo['duration'].shift() > 0
    combo2 = combo.drop(combo[
        (combo['space_b4_prev'] < 1000) & (combo['first_button_press'] is True)
    ].index).reset_index(drop=True)

    mask = pd.notnull(combo2['trial_type'])

    block_start_locs = combo2[mask].index.values

    last_block = combo2.iloc[block_start_locs[len(block_start_locs) - 1]]

    end_row = {
        'onset': last_block.end,
        'rating_duration': 0,
        'event_type': 'last_row',
        'duration': 0,
        'participant_value': last_block.participant_value}

    combo2 = combo2.append(end_row, ignore_index=True).reset_index(drop=True)

    mask = pd.notnull(combo2['trial_type'])

    block_start_locs = combo2[mask].index.values

    combo2['rating_duration'] = (
        combo2['onset'].shift(-1) - combo2['onset'].where(mask is False))

    # this ends up not assigning a value for the final button press - there
    # must be a more elegant way to do all this
    for i in range(len(block_start_locs)):
        if block_start_locs[i] != 0:
            # maybe i should calculate these vars separately for clarity
            combo2.rating_duration[block_start_locs[i - 1]] = (
                combo2.end[block_start_locs[i - 1]] -
                combo2.onset[block_start_locs[i - 1]])

    # adds rows that contain the 5 second at the beginning default value
    for i in block_start_locs:
        new_row = {
            'onset': combo2.onset[i],
            'rating_duration': combo2.onset[i + 1] - combo2.onset[i],
            'event_type': 'default_rating',
            'duration': 0,
            'participant_value': 5}
        combo2 = combo2.append(new_row, ignore_index=True)

    # combo=combo.drop(combo[combo['event_type']=='last_row'].index)
    combo2 = combo2.sort_values(
        by=["onset", "event_type"], na_position='first').reset_index(drop=True)

    return(combo2)


# calculates pearsons r by comparing participant ratings w a gold standard
def block_scores(ratings_dict, combo):
    list_of_rows = []
    summary_vals = {}
    # selects the beginning of trials/trial headers
    # i feel like im recalculating that in lots of places, seems bad maybe
    mask = pd.notnull(combo['trial_type'])
    block_start_locs = combo[mask].index.values
    block_start_locs = np.append(
        block_start_locs, combo.tail(1).index.values, axis=None)

    for idx in range(1, len(block_start_locs)):
        # df['trial_type']=df['movie_name'].apply(
        # lambda x: "circle_block" if "cvid" in x else "EA_block")

        block_start = combo.onset[block_start_locs[idx - 1]]
        block_end = combo.end[block_start_locs[idx - 1]]

        # selects the rows between the start and the end that contain button
        # presses should just change this to select the rows, idk why not lol

        block = combo.iloc[block_start_locs[idx - 1]:block_start_locs[idx]][
            pd.notnull(combo.event_type)]  # between is inclusive by default
        block_name = combo.movie_name.iloc[
            block_start_locs[idx - 1]:block_start_locs[idx]][
            pd.notnull(combo.movie_name)].reset_index(drop=True).astype(
            str).get(0)

        gold = get_series_standard(ratings_dict, block_name)

        if "cvid" in block_name:
            interval = np.arange(combo.onset[block_start_locs[idx - 1]],
                                 combo.end[block_start_locs[idx - 1]],
                                 step=40000)
        else:
            interval = np.arange(combo.onset[block_start_locs[idx - 1]],
                                 combo.end[block_start_locs[idx - 1]],
                                 step=20000)

        if len(gold) < len(interval):
            interval = interval[:len(gold)]
            logger.warning("gold standard is shorter than the number of pt "
                           "ratings. pt ratings truncated",
                           block_name)

        if len(interval) < len(gold):
            gold = gold[:len(interval)]
            logger.warning("number of pt ratings is shorter than the number "
                           "of gold std, gold std truncated",
                           block_name)
        # this is to append for the remaining fraction of a second (so that
        # the loop goes to the end i guess...)- maybe i dont need to do this
        interval = np.append(interval, block_end)

        two_s_avg = []
        for x in range(len(interval) - 1):
            start = interval[x]
            end = interval[x + 1]
            # things that start within the time interval plus the one that
            # starts during the time interval
            sub_block = (block[block['onset'].between(start, end) |
                         block['onset'].between(start, end).shift(-1)])
            block_length = end - start
            if len(sub_block) != 0:
                ratings = []
                for index, row in sub_block.iterrows():
                    # for rows that are in the thing
                    if (row.onset < start):
                        numerator = (row.onset + row.rating_duration) - start
                    else:
                        # if row.onset>=start and row.onset<end:
                        # ooo should i do row.onset<end for everything??
                        if (row.onset + row.rating_duration) <= end:
                            numerator = row.rating_duration
                        elif (row.onset + row.rating_duration) > end:
                            numerator = end - row.onset
                        else:
                            numerator = 999999  # add error here

                    if (row.event_type != 'last_row'):
                        ratings.append(
                            {'start': start,
                             'end': end,
                             'row_time': row.rating_duration,
                             'row_start': row.onset,
                             'block_length': block_length,
                             'rating': row.participant_value,
                             'time_held': numerator}
                        )

                        # participant rating
                        nums = [float(d['rating']) for d in ratings]

                        times = [float(d['time_held']) / block_length
                                 for d in ratings]

                        avg = np.sum(np.multiply(nums, times))

                    last_row = row.participant_value
            else:
                avg = last_row

            # okay so i want to change this to actually create the beginnings
            # of an important row in our df!
            two_s_avg.append(float(avg))
            list_of_rows.append(
                {'event_type': 'running_avg',
                 'participant_value': float(avg),
                 'onset': start,
                 'duration': end - start,
                 'gold_std': gold[x]}
            )
            # removed block_name from above

        n_button_press = len(block[block.event_type == 'button_press'].index)
        block_score = np.corrcoef(gold, two_s_avg)[1][0]
        key = str(block_name)
        summary_vals.update(
            {key: {'n_button_press': int(n_button_press),
                   'block_score': block_score,
                   'onset': block_start,
                   'duration': block_end - block_start}}
        )

    return list_of_rows, summary_vals


def outputs_exist(log_file, output_path):
    if not os.path.exists(output_path):
        return False

    if os.path.getmtime(output_path) < os.path.getmtime(log_file):
        logger.error('Output file is less recently modified than its task file'
                     f' {log_file}. Output will be deleted and regenerated.')
        try:
            os.remove(output_path)
        except Exception as e:
            logger.error(f'Failed to remove output file {output_path}, cannot '
                         f'regenerate. Reason - {e}')
            return True  # To abort attempts to recreate
        return False

    return True


def get_output_path(ident, log_file, dest_dir):
    try:
        os.makedirs(dest_dir)
    except FileExistsError:
        pass

    part = re.findall(r'(part\d).log', log_file)
    if not part:
        logger.error(f"Can't detect which part task file {log_file} "
                     "corresponds to. Ignoring file.")
        return
    else:
        part = part[0]

    return os.path.join(dest_dir, f'{ident}_EAtask_{part}.tsv')


def parse_task(ident, log_file, dest_dir, length_file, timing_file):
    output_path = get_output_path(ident, log_file, dest_dir)

    if outputs_exist(log_file, output_path):
        return

    # Reads in the log, skipping the first three preamble lines
    log = read_in_logfile(log_file)
    # reads in metadata about video stimuli
    vid_in = pd.read_csv(length_file)
    # formats video metadata
    vid_info = format_vid_info(vid_in)
    # finds block onsets and categorizes as ea or circles
    blocks = get_blocks(log, vid_info)
    # grabs all participant button-presses
    ratings = get_ratings(log)

    # add the ratings and the block values together, then sort them and make
    # the index numbers sequential
    combo = combine_dfs(blocks, ratings)
    # more metadata, this time about the gold standard
    ratings_dict = read_in_standard(timing_file)
    # creates the rolling 2s average time series for the participant&gold
    # standard, calculates pearsons r for EA score
    two_s_chunks, scores = block_scores(ratings_dict, combo)

    combo['block_score'] = np.nan
    combo['n_button_press'] = np.nan

    combo = combo.append(two_s_chunks).sort_values("onset").reset_index(
        drop=True)

    test = combo.ix[pd.notnull(combo.stim_file)]
    # adds in scores, button presses, etc
    for index, row in test.iterrows():
        combo.block_score.ix[index] = scores[row['movie_name']]['block_score']
        combo.n_button_press.ix[index] = (
            scores[row['movie_name']]['n_button_press'])
        combo.event_type.ix[index] = 'block_summary'

    cols = ['onset', 'duration', 'trial_type', 'event_type',
            'participant_value', 'gold_std', 'block_score', 'n_button_press',
            'stim_file']
    combo = combo[cols]
    # converts timestamps to seconds
    combo['onset'] = combo.onset / 10000.0
    combo.duration = combo.duration / 10000.0
    # by sorting it makes the fill down accurate instead of mis-labeling
    # (should possibly do this in a better way in future)
    combo.stim_file = combo.stim_file.ffill(axis=0)
    combo = combo.sort_values(by=['onset', 'event_type'])
    # gets rid of that helper row
    combo = combo[combo.event_type != "final_row"]
    combo.to_csv(output_path, sep='\t', na_rep='n/a', index=False)


def main():
    arguments = docopt(__doc__)
    study = arguments['<study>']
    length_file = arguments['--lengths']
    timing_file = arguments['--timings']
    task_regex = arguments['--regex']

    if not length_file:
        length_file = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            '../assets/EA-vid-lengths.csv'
        )

    if not timing_file:
        timing_file = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            '../assets/EA-timing.csv'
        )

    config = datman.config.config(study=study)

    task_path = config.get_path('task')
    nii_path = config.get_path('nii')

    for subject in os.listdir(task_path):
        try:
            ident = datman.scanid.parse(subject)
        except datman.scanid.ParseException:
            logger.error(f"Skipping task folder with malformed ID {subject}")
            continue

        sub_dir = os.path.join(task_path, subject)
        sub_nii = os.path.join(
            nii_path,
            ident.get_full_subjectid_with_timepoint()
        )

        if not os.path.isdir(sub_dir):
            continue

        for task_file in glob.glob(os.path.join(sub_dir, task_regex)):
            parse_task(ident, task_file, sub_nii, length_file, timing_file)


if __name__ == "__main__":
    main()
