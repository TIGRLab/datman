#!/usr/bin/env python
"""Split a toni scan folder produced when the scanner had to restart.

When the ToNI scanner stops and restarts it tends to end up throwing all the
scans into the same output folder. This causes:

    1. Duplicate series numbers in the session.
    2. Multiple series merged into a single folder, when runs have the same
       series number and series description.

This script will split the session into separate folders based on when the
restarts happened.

For example, if a session was scanned like so:
    - 5: localizer
    - 7: T1
    - Scanner Restart
    - 5: localizer
    - 7: epi_2x2x4xtr2_ea_task1
    - Scanner Restart
    - 5: localizer
    - 8: dmri

The zip file pulled from the toni server would look something like:
    - 5_localizer (contains dcms from all three runs in same folder)
    - 7_t1
    - 7_epi_2x2x4xtr2_ea_task1
    - 8_dmri

Which will cause xnat issues (non-numeric series numbers) and dcm2bids
export issues. This script would split it into three separate folders that
can then be treated as separate datman 'repeats' (i.e. "01_01", "01_02",
"01_03").

Note that after splitting the scan, the scans.csv file must be updated to
ignore the original zip file and to apply the proper names to the output
zip file(s).
"""

import logging
import os
import shutil
import zipfile
from argparse import ArgumentParser

import pydicom

import datman.utils

logger = logging.getLogger(os.path.basename(__file__))


def get_args():
    """Parse user commandline arguments.
    """
    parser = ArgumentParser(
        description="Split a toni scan that suffered 1+ scanner restarts."
    )
    parser.add_argument(
        "input_session",
        action="store",
        help="The path to the zip file or folder of the toni session to split."
    )
    parser.add_argument(
        "output_dir",
        action="store",
        help="The path to the output location."
    )
    return parser.parse_args()


def read_contents(scan_path):
    """Sort dicom files by their scan time.
    """
    contents = {}
    resources = []
    for path, _, files in os.walk(scan_path):
        if not files:
            continue
        for item in files:
            item_path = os.path.join(path, item)
            try:
                header = pydicom.read_file(item_path)
            except pydicom.errors.InvalidDicomError:
                resources.append(item_path)
                continue
            scan_time = float(header.get("SeriesTime"))
            contents.setdefault(scan_time, []).append(item_path)

    return contents, resources


def collect_repeat(contents, start_time):
    """Get all dicoms from start_time until a scanner restart or finish
    """
    if start_time == -1:
        return {}, -1

    scan_times = sorted(contents.keys())
    repeat = {}
    found_series = set()
    for time in scan_times:

        if time < start_time:
            continue

        scans = contents[time]
        header = pydicom.read_file(scans[0])
        num = header.get("SeriesNumber")

        if num in found_series:
            return repeat, time

        found_series.add(num)
        repeat[num] = scans

    return repeat, -1


def move_files(output_path, input_session, file_list):
    """Move a set of files to the output location.
    """
    if not file_list:
        logger.debug("No files to move.")
        return

    try:
        os.makedirs(output_path)
    except FileExistsError:
        pass

    for item in file_list:
        subdir = os.path.split(os.path.relpath(item, input_session))[0]
        dest_dir = os.path.join(output_path, subdir)

        try:
            os.makedirs(dest_dir)
        except FileExistsError:
            pass

        try:
            shutil.move(item, dest_dir)
        except shutil.Error as e:
            logger.error(
                f"Failed to move scan {item} to {dest_dir} - {e}"
            )


def unzip_session(in_path, out_path):
    """Unzip a scan session.
    """
    with zipfile.ZipFile(in_path, "r") as zh:
        zh.extractall(out_path)
    output_dirs = os.listdir(out_path)
    if len(output_dirs) == 1:
        return os.path.join(out_path, output_dirs[0])
    return out_path


def zip_session(in_path, out_path):
    """Zip a folder of scans.
    """
    shutil.make_archive(
        os.path.join(out_path, os.path.basename(in_path)),
        "zip",
        in_path
    )


def main(tmp):
    args = get_args()

    if zipfile.is_zipfile(args.input_session):
        input_session = unzip_session(args.input_session, tmp)
    else:
        input_session = args.input_session

    contents, resources = read_contents(input_session)

    start_time = 0
    repeat = 1
    while start_time >= 0:
        tmp_path = os.path.join(
            tmp,
            os.path.basename(input_session) + f"_part{repeat}"
        )

        if resources and repeat == 1:
            move_files(tmp_path, input_session, resources)

        found_scans, start_time = collect_repeat(contents, start_time)

        for series in found_scans:
            move_files(tmp_path, input_session, found_scans[series])

        zip_session(tmp_path, args.output_dir)
        repeat += 1


if __name__ == "__main__":
    with datman.utils.make_temp_directory(prefix="split_scan") as tmp:
        main(tmp)
