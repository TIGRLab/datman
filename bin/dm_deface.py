#!/usr/bin/env python
"""
Defaces anatomical data in the BIDS folder.

Usage:
    dm_deface.py [options] <study> [--bids-filter-suffix <bids_suffix>]... [--skip-bids-validation]
    dm_deface.py [options] <bids_dir> [--bids-filter-suffix <bids_suffix>]... [--bids-database-dir <bids_db>] [--skip-bids-validation=<BOOL>]

Arguments:
    <study>                  Nickname of the study to process
    <bids_dir>               BIDS folder to process

Options:
    -v --verbose             Show intermediate steps
    -d --debug               Show debug messages
    -q --quiet               Show minimal output
    -n --dry-run             Do nothing
    ---bids-filter-suffix bids_suffix,...         List of scan tags to download
    --bids-database-dir      Path to a PyBids database folder for faster indexing
    --skip-bids-validation=BOOL   Assumes the input dataset is BIDS compliant and skip validation [default: False]

DEPENDENCIES
    FSL 6.0.1
    pydeface

"""

import json
import logging
import subprocess
from pathlib import Path

from bids import BIDSLayout
from docopt import docopt

import datman.config

logging.basicConfig(level=logging.WARN, format="[%(name)s %(levelname)s: %(message)s")
logger = logging.getLogger(Path(__file__).name)

DRYRUN = False
bids_dir = None
bids_db = None
bids_suffix = ["T1w"]
skip_validation=False


def main():
    global DRYRUN
    global bids_dir
    global bids_db
    global bids_suffix
    global skip_validation

    arguments = docopt(__doc__)
    study = arguments["<study"]
    bids_dir = arguments["<bids_dir>"]
    bids_db = arguments["--bids-database-dir"]
    bids_suffix=arguments["--bids-filter-suffix"]
    skip_validation=arguments["--skip-bids-validation"]
    verbose = arguments["--verbose"]
    debug = arguments["--debug"]
    quiet = arguments["--quiet"]
    DRYRUN = arguments["--dry-run"]

    if verbose:
        logger.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)
    if quiet:
        logger.setLevel(logging.ERROR)

    if not bids_dir:
        config = datman.config.config(study=study)
        bids_dir = config.get_path("bids")

    layout = BIDSLayout(bids_dir, validate=skip_validation, database_path=bids_db)

    anat_list = layout.get(suffix=bids_suffix, extension=[".nii.gz"])
    keys_to_extract = [
        "subject",
        "session",
        "acquisition",
        "ceagent",
        "reconstruction",
        "run",
        "suffix",
    ]

    for anat in anat_list:

        entities = {key: anat.entities.get(key, None) for key in keys_to_extract}
        if entities["acquisition"] is not None and "defaced" in entities["acquisition"]:
            continue
        if entities["acquisition"] is not None:
            entities["acquisition"] = entities["acquisition"] + "defaced"
        else:
            entities["acquisition"] = "defaced"

        output_file = Path(bids_dir, layout.build_path(entities))

        if not output_file.exists():
            anat_metadata = anat.get_metadata()
            deface_cmd = f"pydeface {anat.path} --outfile {output_file.path}"

            if DRYRUN:
                logger.info(f"DRYRUN would have executed <{deface_cmd}>")
                continue

            anat_metadata["DefaceCmd"] = deface_cmd
            subprocess.call(deface_cmd, shell=True)
            with open(str(output_file).replace(".nii.gz", ".json")) as f:
                json.dump(anat_metadata, f)
