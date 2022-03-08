#!/usr/bin/env python
"""
Parses SPINS' EA log files into BIDS tsvs.

Usage:
    dm_parse_ea.py [options] <study>

Arguments:
    <study>                     A datman study to parse task data for.

Options:
    --experiment <experiment>   Single datman session to generate TSVs for
    --timings <timing_path>     The full path to the EA timings file.
                                Defaults to the 'EA-timing.csv' file in
                                the assets folder.
    --lengths <lengths_path>    The full path to the file containing the
                                EA vid lengths. Defaults to the
                                'EA-vid-lengths.csv' in the assets folder.
    --regex <regex>             The regex to use to find the log files to
                                parse. [default: *UCLAEmpAcc*]
    --debug                     Set log level to debug
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
    log_file = pd.read_csv(path, sep="\t", skiprows=3)

    time_to_subtract = int(log_file.Duration[log_file.Code == "MRI_start"])
    log_file.Time = log_file.Time - time_to_subtract

    return log_file


def is_rating_after_response(current_row, previous_row):

    SCAN_RESPONSE = ["101", "104"]
    try:
        is_rating = "rating" in current_row.Code
    except TypeError:
        is_rating = False

    after_scan_resp = any(resp in previous_row.Code for resp in SCAN_RESPONSE)

    return is_rating and after_scan_resp


def remove_scan_response_ratings(log_file, indices_behind):
    '''
    Check if the current rating is after a scan response
    which occurs <indices_behind> rows prior to the rating code
    '''

    drop_indices = []
    for index, row in log_file.iterrows():

        try:
            previous_row = log_file.loc[index - indices_behind]
        except KeyError:
            continue

        # Drop rating and scan response
        if is_rating_after_response(row, previous_row):
            drop_indices.append(index)
            drop_indices.append(index - indices_behind)

    if len(drop_indices) == 0:
        log_file_cleaned = log_file
    else:
        log_file_cleaned = log_file.drop(log_file.index[drop_indices])
        log_file_cleaned = log_file_cleaned.reset_index(drop=True)

    return log_file_cleaned, len(drop_indices) / 2


# Remove the rating when there is a scanner response
# during the task instead of just at the start
def clean_logfile(log_file):

    # 1st list of indexes to remove scan responses and ratings in the dataframe
    """
    Remove the rating that come after the scan response when there
    is a 102/103 response right before or after. Also remove the rating
    that come after scan response and carry over to the next video
    The rating is always registered two indexes after the scan response
    """
    log_file, indices_dropped = remove_scan_response_ratings(log_file, 2)
    if indices_dropped > 0:
        logger.warning(f"Removed {indices_dropped} registered "
                       "rating occurred before or after actual rating")

    log_file, indices_dropped = remove_scan_response_ratings(log_file, 1)
    if indices_dropped > 0:
        logger.warning(f"Removed {indices_dropped} rating registered "
                       "followed scanner responses")

    last_entry = log_file.loc[log_file.shape[0] - 1]
    if last_entry['Event Type'] == 'Quit':
        log_file = log_file.drop(last_entry)
        logger.error("Quit signal detected in log file! "
                     "Task may have ended early!")

    return log_file


# Grabs the starts of blocks and returns rows for them
def get_blocks(log, vid_info):
    # identifies the video trial types (as opposed to button press events etc)
    mask = ["vid" in log["Code"][i] for i in range(0, log.shape[0])]

    df = pd.DataFrame({
        "onset": log.loc[mask]["Time"],
        "trial_type": log.loc[mask]["Event Type"],
        "movie_name": log.loc[mask]["Code"],
    })

    df["trial_type"] = df["movie_name"].apply(lambda x: "circle_block"
                                              if "cvid" in x else "EA_block")
    df["duration"] = df["movie_name"].apply(lambda x: int(vid_info[x][
        "duration"]) * 10000 if x in vid_info else pd.NA)

    df["stim_file"] = df["movie_name"].apply(lambda x: vid_info[x]["stim_file"]
                                             if x in vid_info else pd.NA)
    df["end"] = df["onset"] + df["duration"]
    return df


def format_vid_info(vid):
    vid.columns = [c.lower() for c in vid.columns]
    vid = vid.rename(index={0: "stim_file", 1: "duration"})
    vid = vid.to_dict()
    return vid


def read_in_standard(timing_path):
    df = pd.read_csv(timing_path).astype(str)
    df.columns = [c.lower() for c in df.columns]
    df_dict = df.drop([0, 0]).reset_index(drop=True).to_dict(orient="list")
    return df_dict


def get_series_standard(gold_standard, block_name):
    return [float(x) for x in gold_standard[block_name] if x != "nan"]


def get_ratings(log):

    rating_mask = ["rating" in log["Code"][i] for i in range(0, log.shape[0])]

    df = pd.DataFrame({
        "onset": log["Time"].loc[rating_mask].values,
        "participant_value": log.loc[rating_mask]["Code"].values,
        "event_type": "button_press",
        "duration": 0,
    })

    # Pull rating value from formatted string
    df["participant_value"] = df["participant_value"].str.strip().str[-1]

    return df


def combine_dfs(blocks, ratings):
    # combines the block rows with the ratings rows and sorts them

    combo = blocks.append(ratings).sort_values("onset").reset_index(drop=True)
    mask = pd.notnull(combo["trial_type"])
    combo["space_b4_prev"] = combo["onset"].diff(periods=1)
    combo["first_button_press"] = combo["duration"].shift() > 0
    combo2 = combo.drop(
        combo[(combo["space_b4_prev"] < 1000)
              & (combo["first_button_press"] == True)].index).reset_index(
                  drop=True)

    mask = pd.notnull(combo2["trial_type"])

    block_start_locs = combo2[mask].index.values

    last_block = combo2.iloc[block_start_locs[len(block_start_locs) - 1]]

    end_row = {
        "onset": last_block.end,
        "rating_duration": 0,
        "event_type": "last_row",
        "duration": 0,
        "participant_value": last_block.participant_value,
    }

    combo2 = combo2.append(end_row, ignore_index=True).reset_index(drop=True)

    mask = pd.notnull(combo2["trial_type"])

    block_start_locs = combo2[mask].index.values

    combo2["rating_duration"] = combo2["onset"].shift(
        -1) - combo2["onset"].where(mask == False)  # noqa: E712

    for i in range(len(block_start_locs)):
        if block_start_locs[i] != 0:

            combo2.rating_duration[block_start_locs[i - 1]] = (
                combo2.end[block_start_locs[i - 1]] -
                combo2.onset[block_start_locs[i - 1]])

    for i in block_start_locs:
        new_row = {
            "onset": combo2.onset[i],
            "rating_duration": combo2.onset[i + 1] - combo2.onset[i],
            "event_type": "default_rating",
            "duration": 0,
            "participant_value": 5,
        }
        combo2 = combo2.append(new_row, ignore_index=True)

    combo2 = combo2.sort_values(by=["onset", "event_type"],
                                na_position="first").reset_index(drop=True)

    return combo2


def block_scores(ratings_dict, combo):
    """
    Compute Pearson correlation between gold standard ratings
    and participant ratings
    """
    list_of_rows = []
    summary_vals = {}

    mask = pd.notnull(combo["trial_type"])
    block_start_locs = combo[mask].index.values
    block_start_locs = np.append(block_start_locs,
                                 combo.tail(1).index.values,
                                 axis=None)

    for idx in range(1, len(block_start_locs)):

        block_start = combo.onset[block_start_locs[idx - 1]]
        block_end = combo.end[block_start_locs[idx - 1]]

        block = combo.iloc[block_start_locs[idx - 1]:block_start_locs[idx]][
            pd.notnull(combo.event_type)]
        block_name = (
            combo.movie_name.iloc[block_start_locs[idx -
                                                   1]:block_start_locs[idx]]
            [pd.notnull(
                combo.movie_name)].reset_index(drop=True).astype(str).get(0))

        gold = get_series_standard(ratings_dict, block_name)

        if "cvid" in block_name:
            interval = np.arange(
                combo.onset[block_start_locs[idx - 1]],
                combo.end[block_start_locs[idx - 1]],
                step=40000,
            )
        else:
            interval = np.arange(
                combo.onset[block_start_locs[idx - 1]],
                combo.end[block_start_locs[idx - 1]],
                step=20000,
            )

        if len(gold) < len(interval):
            interval = interval[:len(gold)]
            logger.warning(
                "gold standard is shorter than the number of pt "
                f"ratings. pt ratings truncated, block: {block_name}", )

        if len(interval) < len(gold):
            gold = gold[:len(interval)]
            logger.warning(
                "number of pt ratings is shorter than the number "
                f"of gold std, gold std truncated, block: {block_name}", )

        # this is to append for the remaining fraction of a second (so that
        # the loop goes to the end i guess...)- maybe i dont need to do this
        interval = np.append(interval, block_end)

        two_s_avg = []
        for x in range(len(interval) - 1):
            start = interval[x]
            end = interval[x + 1]
            sub_block = block[block["onset"].between(start, end)
                              | block["onset"].between(start, end).shift(-1)]
            block_length = end - start
            if len(sub_block) != 0:
                ratings = []
                for index, row in sub_block.iterrows():
                    if row.onset < start:
                        numerator = (row.onset + row.rating_duration) - start
                    else:
                        if (row.onset + row.rating_duration) <= end:
                            numerator = row.rating_duration
                        elif (row.onset + row.rating_duration) > end:
                            numerator = end - row.onset
                        else:
                            numerator = 999999  # add error here

                    if row.event_type != "last_row":
                        ratings.append({
                            "start": start,
                            "end": end,
                            "row_time": row.rating_duration,
                            "row_start": row.onset,
                            "block_length": block_length,
                            "rating": row.participant_value,
                            "time_held": numerator,
                        })

                        nums = [float(d["rating"]) for d in ratings]

                        times = [
                            float(d["time_held"]) / block_length
                            for d in ratings
                        ]

                        avg = np.sum(np.multiply(nums, times))

                    last_row = row.participant_value
            else:
                avg = last_row

            two_s_avg.append(float(avg))
            list_of_rows.append({
                "event_type": "running_avg",
                "participant_value": float(avg),
                "onset": start,
                "duration": end - start,
                "gold_std": gold[x],
            })

        n_button_press = len(block[block.event_type == "button_press"].index)
        block_score = np.corrcoef(gold, two_s_avg)[1][0]
        key = str(block_name)
        summary_vals.update({
            key: {
                "n_button_press": int(n_button_press),
                "block_score": block_score,
                "onset": block_start,
                "duration": block_end - block_start,
            }
        })

    return list_of_rows, summary_vals


def outputs_exist(log_file, output_path):
    if not os.path.exists(output_path):
        return False

    if os.path.getmtime(output_path) < os.path.getmtime(log_file):
        logger.error("Output file is less recently modified than its task file"
                     f" {log_file}. Output will be deleted and regenerated.")
        try:
            os.remove(output_path)
        except Exception as e:
            logger.error(f"Failed to remove output file {output_path}, cannot "
                         f"regenerate. Reason - {e}")
            return True
        return False

    return True


def get_output_path(ident, log_file, dest_dir):
    try:
        os.makedirs(dest_dir)
    except FileExistsError:
        pass

    part = re.findall(r"((?:part|RUN)\d).log", log_file)
    if not part:
        logger.error(f"Can't detect which part task file {log_file} "
                     "corresponds to. Ignoring file.")
        return
    else:
        part = part[0]

    return os.path.join(dest_dir, f"{ident}_EAtask_{part}.tsv")


def parse_task(ident, log_file, dest_dir, length_file, timing_file):
    output_path = get_output_path(ident, log_file, dest_dir)

    if outputs_exist(log_file, output_path):
        return

    # Reads in and clean the log, skipping the first three preamble lines
    try:
        log = read_in_logfile(log_file)
        log_cleaned = clean_logfile(log)
    except Exception as e:
        logger.error(f"Error raised with message: {e}")
        logger.error(
            f"Cannot parse {log_file}! File maybe corrupted! Skipping")
        return

    vid_in = pd.read_csv(length_file)
    vid_info = format_vid_info(vid_in)
    blocks = get_blocks(log_cleaned, vid_info)
    ratings = get_ratings(log_cleaned)

    combo = combine_dfs(blocks, ratings)
    ratings_dict = read_in_standard(timing_file)
    two_s_chunks, scores = block_scores(ratings_dict, combo)

    combo["block_score"] = np.nan
    combo["n_button_press"] = np.nan

    combo = (combo.append(two_s_chunks).sort_values("onset").reset_index(
        drop=True))

    test = combo.loc[pd.notnull(combo["stim_file"])]

    # adds in scores, button presses, etc
    for index, row in test.iterrows():
        combo.loc[index,
                  "block_score"] = scores[row["movie_name"]]["block_score"]
        combo.loc[index, "n_button_press"] = scores[
            row["movie_name"]]["n_button_press"]
        combo.loc[index, "event_type"] = "block_summary"

    cols = [
        "onset",
        "duration",
        "trial_type",
        "event_type",
        "participant_value",
        "gold_std",
        "block_score",
        "n_button_press",
        "stim_file",
    ]
    combo = combo[cols]

    # converts timestamps to seconds
    combo["onset"] = combo.onset / 10000.0
    combo.duration = combo.duration / 10000.0
    combo = combo.sort_values(by=["onset", "event_type"])
    combo.stim_file = combo.stim_file.ffill(axis=0)
    combo = combo[combo.event_type != "final_row"]
    combo.to_csv(output_path, sep="\t", na_rep="n/a", index=False)


def main():
    arguments = docopt(__doc__)
    study = arguments["<study>"]
    experiment = arguments["--experiment"]
    length_file = arguments["--lengths"]
    timing_file = arguments["--timings"]
    task_regex = arguments["--regex"]
    debug = arguments["--debug"]

    if debug:
        logger.setLevel(logging.DEBUG)

    if not length_file:
        length_file = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../assets/EA-vid-lengths.csv",
        )

    if not timing_file:
        timing_file = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../assets/EA-timing.csv",
        )

    config = datman.config.config(study=study)

    task_path = config.get_path("task")
    nii_path = config.get_path("nii")

    if not experiment:
        experiments = os.listdir(task_path)
    else:
        experiments = [experiment]
        logger.info(f"Running EA parsing for {experiment}")

    for experiment in experiments:
        logger.info(f"Parsing {experiment}...")
        try:
            ident = datman.scanid.parse(experiment)
        except datman.scanid.ParseException:
            logger.error(
                f"Skipping task folder with malformed ID {experiment}")
            continue

        exp_task_dir = os.path.join(task_path, experiment)
        sub_nii = os.path.join(nii_path,
                               ident.get_full_subjectid_with_timepoint())

        if not os.path.isdir(exp_task_dir):
            logger.warning(
                f"{experiment} has no task directory {exp_task_dir}, skipping")
            continue

        for task_file in glob.glob(os.path.join(exp_task_dir, task_regex)):
            parse_task(ident, task_file, sub_nii, length_file, timing_file)


if __name__ == "__main__":
    main()
