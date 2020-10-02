#!/usr/bin/env python
"""
Parse the N-back eprime text files into BIDS tsvs

Usage:
  parse_eprime_Nback.py [options] <input_file>

Arguments:
    <input_file>            The location of the ePRIME text file to parse.

Options:
  -o, --output FILE        Name of output tsv file
                           [default: Nback_results.tsv]
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run
  --help                   Print help

DETAILS
Parse the N-back eprime text files for RTMS in the of scanner.
Written by Erin W Dickie, November 18 2015
Modified to extract event timings by Jerry Jeyachandra, November 2018
Modified to parse task file to bids tsv format by Thomas Tan, Aug 2020
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

    corr = {"c": 1, "0": 0, "1": 1, "3": 1}

    # loop over the inputfiles
    if DEBUG:
        print("\n file: {}".format(input_file))

    with open(input_file, "r", encoding="utf-16") as my_file:
        file_text = my_file.read()

    # find and replace this weird text string that show up between every character
    file_text = file_text.replace("\x00", "")
    file_text = file_text.replace("\r\n", "\n")  # a windows formatting thing..

    # split all the text into individual trials using "LogFrame End" text string
    # this string is printed to the log at the conclusion of everytrial
    trials = file_text.split("LogFrame End")

    # Create a list to store dictionaries
    message_df_dict = []

    # loop over individual trials
    trial_count = 0
    for trial in trials:
        # for each trial collect CorrectResponse, Subject's Response
        #  and the Reaction Time
        Correct_Response = int()
        Reaction_Time = int()
        Subject_Response = int()
        Trial_Type = str()
        Trial_Time = int()
        for line in trial.split("\n\t"):
            if "Running:" in line:
                Trial_Type = line.split(":")[1].replace(" ", "")
            if "letterdisp.OnsetTime:" in line:
                Trial_Time = line.split(":")[1].replace(" ", "")
            if (
                ("resp:" in line)
                and ("letterdisp.RESP" not in line)
                and ("letterdisp.CRESP" not in line)
            ):
                Correct_Response = line.split(":")[1].replace(" ", "")
            if ("letterdisp.RT" in line) and ("letterdisp.RTTime" not in line):
                Reaction_Time = line.split(":")[1].replace(" ", "")
            if "letterdisp.RESP" in line:
                Subject_Response = line.split(":")[1].replace(" ", "")

        # Skip if list type
        if (Trial_Type == "List1") or (Trial_Type == ""):
            continue
        trial_count += 1

        # Form trial dictionary
        trial_dict = {
            "onset": Trial_Time,
            "duration": 0,
            "trial_type": Trial_Type,
            "correct_response": corr[str(Correct_Response)],
            "participant_response": 1 if Subject_Response else 0,
            "response_time": Reaction_Time,
        }
        # Stack dictionaries
        message_df_dict.append(trial_dict)

    # Create a dataframe comprised of the list of messages containing
    #  the information we need
    message_df = pd.DataFrame.from_dict(message_df_dict)

    # Map blocks and trial type to new columns
    message_df["block"] = message_df["trial_type"].str[-1]
    message_df["trial_type"] = message_df["trial_type"].str[:-1]

    # Map response time to new columns in seconds
    message_df["response_time"] = message_df["response_time"].astype(int)
    message_df["response_time"] = message_df["response_time"].apply(
        lambda x: x / 1000
    )

    # Convert the onset time to seconds
    # Account for 4 TR drops and first trial start time is 15 - 8
    message_df["onset"] = message_df["onset"].astype(int)
    message_df["onset"] = (
        message_df["onset"].sub(message_df.iloc[0, :]["onset"]) / 1000 + 15 - 8
    )

    # Create a dataframe comprised of onset of blocks and duration
    df1 = (
        message_df.iloc[0::20]
        .assign(
            duration=lambda x: x["duration"] + 60,
            trial_type=lambda x: x["trial_type"] + "block",
        )
        .rename(lambda x: x - 0.5)
    )
    # Concatenate the new dataframe into the original dataframe
    message_df_final = (
        pd.concat([message_df, df1], sort=False)
        .sort_index()
        .reset_index(drop=True)
    )
    # Map the correct response, participant response,
    # and reponse time columns back to n/a
    cols = ["correct_response", "participant_response", "response_time"]
    message_df_final.loc[0::21, (cols)] = message_df_final.loc[
        0::21, (cols)
    ].replace(0, "n/a")

    # Output the dataframe output as tsv file
    message_df_final.to_csv(results_file, sep="\t", index=False)


if __name__ == "__main__":
    main()
