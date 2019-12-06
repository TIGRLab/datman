#!/usr/bin/env python

"""
Usage:
    dm_update_standards.py [options] <study>

Arguments:
    <study>                 DATMAN study ID
Optional:
    -d, --debug             Verbose logging for direct DBAPI logs

Description:
    Utility script to update dashboard gold standards with what's currently
    available in a given study's metadata/standards directory.
"""

import os
from docopt import docopt

import datman.scanid
import datman.scan
import datman.dashboard
import datman.config
from dashboard.exceptions import InvalidDataException
import logging

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(levelname)s: \
                                                %(message)s")
logger = logging.getLogger(os.path.basename(__file__))


def main():

    arguments = docopt(__doc__)
    study = arguments["<study>"]
    debug = arguments["--debug"]

    if debug:
        logger.info("Logging in DEBUG mode")
        logger.setLevel(logging.DEBUG)

    # Get standards and database study
    cfg = datman.config.config(study=study)
    standards_path = cfg.get_path("std")
    standards = [f for f in os.listdir(standards_path) if ".json" in f]
    db_study = datman.dashboard.get_project(name=study)

    # Add standards to database
    for s in standards:

        try:
            db_study.add_gold_standard(os.path.join(standards_path, s))
        except InvalidDataException as e:
            logger.error("Standard {} already exists in the Dashboard!"
                         .format(s))
            logger.debug("Returned error: {}".format(e))
            continue
        else:
            logger.info("Successfully added {} to gold_standards".format(s))


if __name__ == "__main__":
    main()
