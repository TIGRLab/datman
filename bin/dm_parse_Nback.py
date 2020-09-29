#!/usr/bin/env python
"""
Parse the N-back eprime text files into BIDS tsvs

Usage:
  parse_eprime_Nback.py [options] <inputfile>

Arguments:
    <inputfile>            The location of the ePRIME text file to parse.

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

arguments = docopt(__doc__)
inputfile = arguments["<inputfile>"]
resultsfile = arguments["--output"]
DEBUG = arguments["--debug"]
DRYRUN = arguments["--dry-run"]

if DEBUG:
    print(arguments)

corr = {"c": 1, "0": 0, "1": 1, "3": 1}

# loop over the inputfiles
if DEBUG:
    print("\n file: {}".format(inputfile))

with open(inputfile, "r", encoding="utf-16") as myfile:
    filetext = myfile.read()

# find and replace this weird text string that show up between every character
filetext = filetext.replace("\x00", "")
filetext = filetext.replace("\r\n", "\n")  # a windows formatting thing..

# split all the text into individual trials using "LogFrame End" text string
# this string is printed to the log at the conclusion of everytrial
trials = filetext.split("LogFrame End")

# Create a list to store dictionaries
message_df_dict = []

# loop over individual trials
trial_count = 0
for trial in trials:
    # for each trial collect CorrectResponse, Subject's Response
    #  and the Reaction Time
    CorrectResponse = int()
    ReactionTime = int()
    SubjectResponse = int()
    TrialType = str()
    TrialTime = int()
    for line in trial.split("\n\t"):
        if "Running:" in line:
            TrialType = line.split(":")[1].replace(" ", "")
        if "letterdisp.OnsetTime:" in line:
            TrialTime = line.split(":")[1].replace(" ", "")
        if (
            ("resp:" in line)
            and ("letterdisp.RESP" not in line)
            and ("letterdisp.CRESP" not in line)
        ):
            CorrectResponse = line.split(":")[1].replace(" ", "")
        if ("letterdisp.RT" in line) and ("letterdisp.RTTime" not in line):
            ReactionTime = line.split(":")[1].replace(" ", "")
        if "letterdisp.RESP" in line:
            SubjectResponse = line.split(":")[1].replace(" ", "")

    # Skip if list type
    if (TrialType == "List1") or (TrialType == ""):
        continue
    trial_count += 1

    # Form trial dictionary
    trial_dict = {
        "onset": TrialTime,
        "duration": 0,
        "trial_type": TrialType,
        "correct_response": corr[str(CorrectResponse)],
        "participant_response": 1 if SubjectResponse else 0,
        "response_time": ReactionTime,
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
    pd.concat([message_df, df1], sort=False).sort_index().reset_index(drop=True)
)
# Map the correct response, participant response,
# and reponse time columns back to n/a
cols = ["correct_response", "participant_response", "response_time"]
message_df_final.loc[0::21, (cols)] = message_df_final.loc[
    0::21, (cols)
].replace(0, "n/a")

# Output the dataframe output as tsv file
message_df_final.to_csv(resultsfile, sep="\t", index=False)
