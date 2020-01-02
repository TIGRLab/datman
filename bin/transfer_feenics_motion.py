#!/usr/bin/env python

"""
Helper script for transferring motion files generated from feenics over to
fMRIPREP (version >= 1.3.2)

Usage:
    transfer_feenics_motion.py [options] [-s SUBJECT]...  <study> <output_dir>

Arguments:
        <study>                  DATMAN study ID
        <output_dir>             Directory to output
                                 new confounds files

Optional:
    -s, --subject SUBJECT        Repeatable list of subjects
    -f, --fmriprep FMRIPREP      fMRIPREP derivatives directory
                                 (default is PROJECT_DIR/pipelines/feenics)
    -d, --debug                  Debug level logging
    -v, --verbose                Verbose level logging
    -q, --quiet                  Quiet mode
"""

from datman.config import config as dm_cfg
from datman import scanid
from bids import BIDSLayout
from docopt import docopt
import numpy as np
import pandas as pd
import os
from shutil import copyfile
import logging


logging.basicConfig(level=logging.WARN, format="[%(name)s %(levelname)s :\
                                                %(message)s]")
logger = logging.getLogger(os.path.basename(__file__))


def combine_sprl_motion(sprl_in, sprl_out):

    motion_in = np.genfromtxt(sprl_in)
    motion_out = np.genfromtxt(sprl_out)

    motion_comb = (motion_in + motion_out) / 2
    return motion_comb


def proc_subject(s, pipeline_dir):
    """
    Given a subject locate FeenICS confounds in pipeline directory
    """

    # Get motion files
    sub_dir = os.path.join(pipeline_dir, s)
    sprl_in = os.path.join(sub_dir, "sprlIN", "motion_corr.par")
    sprl_out = os.path.join(sub_dir, "sprlOUT", "motion_corr.par")

    # Average the motion traces
    motion_comb = combine_sprl_motion(sprl_in, sprl_out)

    return motion_comb


def combine_confounds(confound, motion):
    """
    Given a confound file and motion array:
        - Replace the existing translation/rotation parameters
            in confounds with those in motion
        - Return a pandas dataframe containing the final dataframe
            to be outputted

    Should support both versions of fMRIPREP...=>1.3.2 first
    """

    # Get columns to replace
    dirs = ["x", "y", "z"]
    trans = ["trans_{}".format(d) for d in dirs]
    rots = ["rot_{}".format(d) for d in dirs]
    cols = rots + trans

    # Load in confounds
    df = pd.read_csv(confound, delimiter="\t")

    # Drop columns to be replaced
    df.drop(cols, axis=1, inplace=True)
    df.drop("framewise_displacement", axis=1, inplace=True)

    # Replace with motion information
    motion_df = pd.DataFrame(motion, columns=cols)

    # Calculate new FD
    def fd(x):
        return x.abs().sum()

    motion_df["framewise_displacement"] = motion_df[cols].apply(fd, axis=1)

    # Append to dataframe
    df = df.join(motion_df)

    # Return dataframe
    return df


def filter_for_sprl(c):
    """
    Given a BIDSFile object, filter for sprl type file
    """

    try:
        val = "sprlcombined" in c.entities["acquisition"]
    except KeyError:
        return False
    else:
        return val


def configure_logger(quiet, verbose, debug):
    """
    Configure logger settings for script session
    """

    if quiet:
        logger.setLevel(logging.ERROR)
    elif verbose:
        logger.setLevel(logging.INFO)
    elif debug:
        logger.setLevel(logging.DEBUG)

    return


def main():

    arguments = docopt(__doc__)
    study = arguments["<study>"]
    output = arguments["<output_dir>"]

    # Default directories
    cfg = dm_cfg(study=study)
    feenics_dir = cfg.get_path("feenics")

    fmriprep = arguments["--fmriprep"] or cfg.get_path("fmriprep")
    subjects = arguments["--subject"]

    debug = arguments["--debug"]
    verbose = arguments["--verbose"]
    quiet = arguments["--quiet"]

    configure_logger(quiet, verbose, debug)

    # Step 1: Loop through subjects available in the feenics pipeline directory
    if not subjects:
        subjects = [
            s
            for s in os.listdir(feenics_dir)
            if os.path.isdir(os.path.join(feenics_dir, s))
        ]

    # Step 1a: Get BIDS subjects
    layout = BIDSLayout(fmriprep, validate=False)
    confounds = layout.get(suffix=["confounds", "regressors"], extension="tsv")
    confounds = [c for c in confounds if filter_for_sprl(c)]

    # Create dictionary to deal with summary mean FD tables
    sub2meanfd = []

    # Process each subject
    for s in subjects:

        # Get subject BIDS name and session
        logger.info("Processing {}".format(s))

        ident = scanid.parse(s)
        bids = ident.get_bids_name()
        ses = ident.timepoint

        # Get confound file if exists
        try:
            confound = [
                c.path
                for c in confounds
                if (c.entities["subject"] == bids) and
                (c.entities["session"] == ses)
            ][0]
        except IndexError:
            logger.info("Could not find confound file for {}".format(bids))
            continue

        # Transfer confound
        confound_out = os.path.join(output, os.path.basename(confound))
        try:
            motion_comb = proc_subject(s, feenics_dir)
        except IOError:
            # Copy over
            logger.info(
                "Missing FeenICS motion confound files,\
                        using fmriprep confound: {}".format(
                    bids
                )
            )
            copyfile(confound, confound_out)
            confound_df = pd.read_csv(confound, delimiter="\t")
        else:
            # Write dataframe to output
            logger.info("Found FeenICS motion confound for: {}".format(bids))
            confound_df = combine_confounds(confound, motion_comb)
            confound_df.to_csv(confound_out, index=False, sep="\t")
        finally:
            # Store mean framewise displacement
            scan_name = os.path.basename(confound)\
                               .replace('desc-confounds_regressors.tsv',
                                        'bold')
            sub2meanfd.append(
                {
                    "bids_name": scan_name,
                    "mean_fd": confound_df["framewise_displacement"].mean(),
                }
            )

    # Generate mean FD dataframe
    meanfd_file = os.path.join(output, "mean_FD.tsv")
    meanfd_df = pd.DataFrame.from_dict(sub2meanfd)
    meanfd_df.set_index("bids_name", drop=True, inplace=True)
    meanfd_df.to_csv(meanfd_file, sep="\t", index_label="bids_name")


if __name__ == "__main__":
    main()
