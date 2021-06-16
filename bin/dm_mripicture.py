#!/usr/bin/env python
"""
Creates MRI axial pictures for custom T-shirt.

Usage:
    mripicture.py [options] <study>
    mripicture.py [options] <study> [-s <subject>]...
    mripicture.py [options] <study> [-s <subject>]... [-t <tag>]

Arguments:
    <study>             Nickname of the study to process

Options:
    -s --subject        Subjects
    -o --output=FOLDER  Output directory (default: /archive/data/{study}/data/tshirt)
    -t --tag=TAG        Scan tag [default: T1]
    -f --force          Force overwrite of output files [default: False]
    -h --help           Show this screen
    -q, --quiet         Show minimal output
    -d, --debug         Show debug messages
    -v, --verbose       Show intermediate steps
"""

import os
import glob
import logging
from nilearn import plotting
import numpy as np
from docopt import docopt

import datman.config
import datman.scan


logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))


def get_all_subjects(config):
    nii_dir = config.get_path("nii")
    subject_nii_dirs = glob.glob(os.path.join(nii_dir, "*"))
    all_subs = [os.path.basename(path) for path in subject_nii_dirs]
    return all_subs


def main():
    arguments = docopt(__doc__)
    study = arguments["<study>"]
    outdir = arguments["--output"]
    subs = arguments["<subject>"]
    tag = arguments["--tag"]
    force = arguments["--force"]
    quiet = arguments["--quiet"]
    debug = arguments["--debug"]
    verbose = arguments["--verbose"]
    config = datman.config.config(study=study)

    # setup logging
    if quiet:
        logger.setLevel(logging.ERROR)
    if verbose:
        logger.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)

    if subs:
        logger.info(
            f"Creating pictures for subjects [ {', '.join(subs)} ] from "
            f"{study} project using {tag} scans."
        )
    else:
        subs = get_all_subjects(config)
        logger.info(
            f"Creating pictures for all {len(subs)} subjects from {study} "
            f"project using {tag} scans."
        )

    if not outdir:
        outdir = os.path.join(config.get_path("data"), "tshirt")

    os.makedirs(outdir, exist_ok=True)
    logger.debug(f"Output location set to: {outdir}")

    if force:
        logger.info("Overwriting existing files")

    for subject in subs:

        scan = datman.scan.Scan(subject, config)
        tagged_scan = scan.get_tagged_nii(tag)
        idx = np.argmax([ss.series_num for ss in tagged_scan])

        # Set Path
        imgpath = tagged_scan[idx].path
        outpath = os.path.join(outdir, subject + "_T1.pdf")

        if os.path.isfile(outpath) and not force:
            logger.debug(f"Skipping subject {subject} as files already exist.")

        else:
            # Output Image
            t1_pic = plotting.plot_anat(
                imgpath,
                cut_coords=(-20, -10, 2),
                display_mode="x",
                annotate=False,
                draw_cross=False,
                vmin=100,
                vmax=1100,
                threshold="auto",
            )
            t1_pic.savefig(outpath, dpi=1000)
            logger.debug(
                f"Created new brain pictures for subject {subject} from file "
                f"{imgpath} and saved as {outpath}"
            )

    logger.info(f"Saved all output to: {outdir}")


if __name__ == "__main__":
    main()
