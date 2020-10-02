#!/usr/bin/env python
"""
Parse the Go-NoGo eprime text files to BIDS tsv

Usage:
  parse_eprime_GNGo.py [options] <input_file>

Arguments:
    <input_file>           The location of the text file to parse.

Options:
  -o, --output FILE        Name of output tsv file
                           [default: GNGo_results.tsv]
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run
  --help                   Print help

DETAILS
Parse the N-back eprime text files for RTMS in the of scanner.
Written by Erin W Dickie, November 18 2015
Modified to extract event timings by Jerry Jeyachandra, November 2018
Modified to parse task file into tsv bid-format by Thomas Tan, August 22,2020
"""

import pandas as pd
from docopt import docopt


def main():
    arguments = docopt(__doc__)
    input_file = arguments["<input_file>"]
    results_file = arguments["--output"]
    DEBUG = arguments["--debug"]
    if DEBUG:
        print(arguments)
    # Loop over the inputfiles
    if DEBUG:
        print("\n file: {}".format(input_file))

    try:
        with open(input_file, "r", encoding="utf-16") as my_file:
            file_text = my_file.read()
    except FileNotFoundError:
        print("ERROR opening file")
        quit()

    # Find and replace this weird text string that show up between every character
    file_text = file_text.replace("\x00", "")
    file_text = file_text.replace("\r\n", "\n")

    # Split all the text into individual trials using "LogFrame End" text string
    # This string is printed to the log at the conclusion of everytrial
    trials = file_text.split("LogFrame End")

    # Create a list to store dictionaries
    message_df_dict = []

    # Loop over individual trials
    trial_count = 0
    for trial in trials:
        # For each trial collect the CorrectResponse, Subject's Response and
        # the Reaction Time
        Correct_Response = int()
        Reaction_Time = int()
        Subject_Response = int()
        Trial_Type = str()
        Stim_File = str()

        for line in trial.split("\n\t"):
            if "type:" in line:
                Trial_Type = line.split(":")[1].replace(" ", "")
            if ("ImageDisplay1.RT:" in line) and (
                "ImageDisplay1.RTTime:" not in line
            ):
                Reaction_Time = line.split(":")[1].replace(" ", "")
            if "ImageDisplay1.RESP:" in line:
                Subject_Response = line.split(":")[1].replace(" ", "")
            if "ImageDisplay1.CRESP:" in line:
                Correct_Response = line.split(":")[1].replace(" ", "")
            if "image:" in line:
                Stim_File = line.split(":")[1].replace(" ", "")
        # Skip if list type
        if Trial_Type == "":
            continue
        trial_count += 1

        # Form trial dictionary
        trial_dict = {
            "trial_type": Trial_Type,
            "correct_response": Correct_Response,
            "participant_response": Subject_Response,
            "response_time": Reaction_Time,
            "stim_file": Stim_File,
            "duration": 0,
        }

        # Stack dictionaries
        message_df_dict.append(trial_dict)

    # Create a dataframe comprised of the list of messages
    # containing the information we need
    message_df = pd.DataFrame.from_dict(message_df_dict)

    # Map trial type to new columns using string
    int_to_type = {"1": "go", "2": "nogo"}
    message_df["trial_type"] = (
        message_df["trial_type"]
        .str[-1]
        .apply(lambda x: int_to_type[(x.lower())])
    )

    # Map response time to new columns using integers
    # Convert response time to seconds
    message_df["response_time"] = message_df["response_time"].astype(int)
    message_df["response_time"] = message_df["response_time"].apply(
        lambda x: x / 1000
    )

    # Load in the gngo onset time csv file
    try:
        df_onset = pd.read_csv("gng_event_timing.csv")
    except FileNotFoundError:
        print("ERROR opening onset time file")
        quit()

    # Attach the onset column to the original DataFrame
    # Reorder the columns
    message_df = message_df.join(df_onset["onset"])
    cols = message_df.columns.tolist()
    cols = cols[-1:] + cols[:-1]
    message_df = message_df[cols]

    # Output the tsv file
    message_df.to_csv(results_file, sep="\t", index=False)


if __name__ == "__main__":
    main()
