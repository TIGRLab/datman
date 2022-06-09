#!/usr/bin/env python
"""
Defaces anatomical data in a BIDS dataset.

This script is a wrapper around pydeface
(https://github.com/poldracklab/pydeface).

DEPENDENCIES
    FSL 6.0.1

"""

import json
import logging
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from collections import OrderedDict
from pathlib import Path

from bids import BIDSLayout
from pydeface.utils import deface_image

import datman.config

logging.basicConfig(
    level=logging.WARN, format="[%(name)s %(levelname)s: %(message)s"
)
logger = logging.getLogger(Path(__file__).name)


def _is_dir(path, parser):
    """Ensure a given directory exists."""
    if path is None or not Path(path).is_dir():
        raise parser.error(f"Directory does not exist: <{path}>")
    return Path(path).absolute()


def get_to_deface(layout, suffix_list):
    scan_list = layout.get(suffix=suffix_list, extension=[".nii", ".nii.gz"])
    defaced_list = layout.get(
        suffix=suffix_list,
        Defaced=True,
        extension=[".nii", ".nii.gz"],
        invalid_filters="allows",
    )
    to_deface = list(set(scan_list) - set(defaced_list))
    return to_deface


def get_metadata(scan_sidecar):
    with open(scan_sidecar, "r+") as f:
        metadata = OrderedDict(json.load(f))
    return metadata


def define_output_file(scan, layout, clobber):
    if clobber:
        return (scan.path, scan.path.replace(".nii.gz", ".json"))
    else:
        keys_to_extract = [
            "subject",
            "session",
            "acquisition",
            "ceagent",
            "reconstruction",
            "run",
            "suffix",
        ]

        entities = {
            key: scan.entities.get(key, None) for key in keys_to_extract
        }
        if entities["acquisition"] is not None:
            entities["acquisition"] = entities["acquisition"] + "defaced"
        else:
            entities["acquisition"] = "defaced"
        output_file = str(Path(layout.root, layout.build_path(entities)))
        return (output_file, output_file.replace(".nii.gz", ".json"))


def update_metadata(metadata):
    metadata["Defaced"] = True
    metadata.move_to_end("ConversionSoftware")
    metadata.move_to_end("ConversionSoftwareVersion")
    return metadata


def write_json(metadata, output_file):
    with open(output_file, "w+") as f:
        json.dump(metadata, f, indent=4)


def main():
    parser = ArgumentParser(
        description="Defaces anatomical data in a BIDS dataset",
        formatter_class=ArgumentDefaultsHelpFormatter,
    )

    g_required = parser.add_mutually_exclusive_group(required=True)
    g_required.add_argument(
        "--study", action="store", help="Nickname of the study to process"
    )
    g_required.add_argument(
        "--bids-dir",
        action="store",
        metavar="DIR",
        type=lambda x: _is_dir(x, parser),
        help="The root directory of the BIDS dataset to process",
    )

    parser.add_argument(
        "--separate",
        action="store_false",
        default=True,
        help="Replace the original images with the defaced images",
    )

    g_bids = parser.add_argument_group("Options for filtering BIDS queries")
    g_bids.add_argument(
        "-s",
        "--suffix_id",
        action="store",
        nargs="+",
        default=["T1w"],
        help="Select a specific BIDS suffix to be processed",
    )
    g_bids.add_argument(
        "--skip-bids-validation",
        action="store_true",
        default=False,
        help="Assume the input dataset is BIDS compatible and skip validation",
    )
    g_bids.add_argument(
        "--bids-database-dir",
        action="store",
        type=lambda x: _is_dir(x, parser),
        help="Path to a PyBIDS database directory for faster indexing",
    )

    g_perfm = parser.add_argument_group("Options for logging and debugging")
    g_perfm.add_argument(
        "--quiet", action="store_true", default=False, help="Minimal logging"
    )
    g_perfm.add_argument(
        "--verbose", action="store_true", default=False, help="Maximal logging"
    )
    g_perfm.add_argument(
        "--dry-run", action="store_true", default=False, help="Do nothing"
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.INFO)
    if args.quiet:
        logger.setLevel(logging.ERROR)

    if args.study:
        config = datman.config.config(study=args.study)
        bids_dir = config.get_path("bids")
    else:
        bids_dir = args.bids_dir

    clobber = args.separate

    layout = BIDSLayout(
        bids_dir,
        validate=args.skip_bids_validation,
        database_path=args.bids_database_dir,
    )

    suffix_list = args.suffix_id

    to_deface = get_to_deface(layout, suffix_list)

    for scan in to_deface:
        scan_sidecar = scan.path.replace(".nii.gz", ".json")
        scan_metadata = get_metadata(scan_sidecar)
        output_file, output_sidecar = define_output_file(scan, layout, clobber)

        if args.dry_run:
            logger.info(
                f"DRYRUN would have executed defacing on <{scan.path}> "
                f"and output to <{output_file}>"
            )
            continue

        try:
            deface_image(infile=scan.path, outfile=output_file, force=clobber)
        except Exception as e:
            logger.error(
                f"Defacing failed to run on <{scan.path}> for reason {e}"
            )
            return

        new_scan_metadata = update_metadata(scan_metadata)
        write_json(new_scan_metadata, output_sidecar)


if __name__ == "__main__":
    main()
