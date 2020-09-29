#!/usr/bin/env python
"""
Parse the Go-NoGo eprime text files to BIDS tsv

Usage:
  parse_eprime_GNGo.py [options] <inputfile>

Arguments:
    <inputfile>             The location of the text file to parse.

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

arguments = docopt(__doc__)
inputfile = arguments["<inputfile>"]
resultsfile = arguments["--output"]
DEBUG = arguments["--debug"]
DRYRUN = arguments["--dry-run"]

if DEBUG:
    print(arguments)

# Loop over the inputfiles
if DEBUG:
    print("\n file: {}".format(inputfile))

try:
    with open(inputfile, "r", encoding="utf-16") as myfile:
        filetext = myfile.read()
except myfile.DoesNotExist:
    print("ERROR opening file")
    quit()

# Find and replace this weird text string that show up between every character
filetext = filetext.replace("\x00", "")
filetext = filetext.replace("\r\n", "\n")

# Split all the text into individual trials using "LogFrame End" text string
# This string is printed to the log at the conclusion of everytrial
trials = filetext.split("LogFrame End")

# Create a list to store dictionaries
message_df_dict = []

# Loop over individual trials
trial_count = 0
for trial in trials:
    # For each trial collect the CorrectResponse, Subject's Response and
    # the Reaction Time
    CorrectResponse = int()
    ReactionTime = int()
    SubjectResponse = int()
    TrialType = str()
    StimFile = str()

    for line in trial.split("\n\t"):
        if "type:" in line:
            TrialType = line.split(":")[1].replace(" ", "")
        if ("ImageDisplay1.RT:" in line) and (
            "ImageDisplay1.RTTime:" not in line
        ):
            ReactionTime = line.split(":")[1].replace(" ", "")
        if "ImageDisplay1.RESP:" in line:
            SubjectResponse = line.split(":")[1].replace(" ", "")
        if "ImageDisplay1.CRESP:" in line:
            CorrectResponse = line.split(":")[1].replace(" ", "")
        if "image:" in line:
            StimFile = line.split(":")[1].replace(" ", "")
    # Skip if list type
    if TrialType == "":
        continue
    trial_count += 1

    # Form trial dictionary
    trial_dict = {
        "trial_type": TrialType,
        "correct_response": CorrectResponse,
        "participant_response": SubjectResponse,
        "response_time": ReactionTime,
        "stim_file": StimFile,
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
    message_df["trial_type"].str[-1].apply(lambda x: int_to_type[(x.lower())])
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
except df_onset.DoesNotExist:
    print("ERROR opening onset time file")
    quit()

# Attach the onset column to the original DataFrame
# Reorder the columns
message_df = message_df.join(df_onset["onset"])
cols = message_df.columns.tolist()
cols = cols[-1:] + cols[:-1]
message_df = message_df[cols]
# Output the tsv file
message_df.to_csv(resultsfile, sep="\t", index=False)
