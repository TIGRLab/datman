#!/usr/bin/env python
"""
Defaces anatomical data in a BIDS dataset.

DEPENDENCIES
    FSL 6.0.1

"""

import json
import logging
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
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

    g_bids = parser.add_argument_group("Options for filtering BIDS queries")
    g_bids.add_argument(
        "-s",
        "--suffix-id",
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

    layout = BIDSLayout(
        bids_dir,
        validate=args.skip_bids_validation,
        database_path=args.bids_database_dir,
    )

    anat_list = layout.get(suffix=args.suffix_id, extension=[".nii", ".nii.gz"])
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

        entities = {
            key: anat.entities.get(key, None) for key in keys_to_extract
        }
        if (
            entities["acquisition"] is not None
            and "defaced" in entities["acquisition"]
        ):
            continue
        if entities["acquisition"] is not None:
            entities["acquisition"] = entities["acquisition"] + "defaced"
        else:
            entities["acquisition"] = "defaced"

        output_file = Path(bids_dir, layout.build_path(entities))

        if not output_file.exists():
            if args.dry_run:
                logger.info(
                    f"DRYRUN would have executed defacing on <{anat.path}> "
                    f"and output to <{output_file}>"
                )
                continue

            try:
                deface_image(infile=anat.path, outfile=str(output_file))
            except Exception as e:
                logger.error(
                    f"Defacing failed to run on <{anat.path}> for "
                    f"reason {e}"
                )
                return

            anat_metadata = anat.get_metadata()
            anat_metadata["DefaceSoftware"] = "pydeface"
            with open(str(output_file).replace(".nii.gz", ".json"), "w+") as f:
                json.dump(anat_metadata, f, indent=4)


if __name__ == "__main__":
    main()
