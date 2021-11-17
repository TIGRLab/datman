#!/usr/bin/env python
"""
Defaces anatomical data in the BIDS folder.

DEPENDENCIES
    FSL 6.0.1
    pydeface

"""

from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
import json
import logging
import subprocess
from pathlib import Path

from bids import BIDSLayout

import datman.config

logging.basicConfig(
    level=logging.WARN, format="[%(name)s %(levelname)s: %(message)s"
)
logger = logging.getLogger(Path(__file__).name)


def main():
    parser = ArgumentParser(
        description="Deface anatomical data in the BIDS folder",
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
        type=lambda x: Path(x).isdir(),
        help="The root folder of the BIDS dataset to process",
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
        metavar="DIR",
        type=lambda x: Path(x).isdir(),
        help="Path to a PyBIDS database folder for faster indexing",
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

    if not args.bids_dir:
        config = datman.config.config(study=args.study)
        bids_dir = config.get_path("bids")

    layout = BIDSLayout(
        bids_dir,
        validate=args.skip_bids_validation,
        database_path=args.bids_database_dir,
    )

    anat_list = layout.get(suffix=args.suffix_id, extension=[".nii.gz"])
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
            deface_cmd = f"pydeface {anat.path} --outfile {str(output_file)}"

            if args.dry_run:
                logger.info(f"DRYRUN would have executed <{deface_cmd}>")
                continue

            subprocess.call(deface_cmd, shell=True)

            anat_metadata = anat.get_metadata()
            anat_metadata["DefaceCmd"] = deface_cmd
            with open(str(output_file).replace(".nii.gz", ".json"), "w+") as f:
                json.dump(anat_metadata, f, indent=4)


if __name__ == "__main__":
    main()
