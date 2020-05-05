"""
Utility functions for comparing nifti json header files to json gold standard
files.
"""
import json
import os

from numpy import bool_, isclose


def parse_file(file_path):
    try:
        with open(file_path, "r") as fh:
            contents = fh.readlines()
    except Exception as e:
        raise type(e)(f"Couldn't read file of field names to ignore. {str(e)}")
    return [line.strip() for line in contents]


def construct_diffs(
    series_json, standard_json, ignored_fields=None, tolerances=None, dti=False
):
    series = read_json(series_json)
    standard = read_json(standard_json)

    diffs = compare_headers(
        series, standard, ignore=ignored_fields, tolerance=tolerances
    )

    if dti:
        diffs["bvals"] = check_bvals(series_json, standard_json)

    return diffs


def read_json(json_file):
    with open(json_file, "r") as fp:
        contents = json.load(fp)
    return contents


def compare_headers(series, standard, ignore=None, tolerance=None):
    if not series or not standard:
        raise Exception(
            "Must provide JSON contents for series and gold standard"
        )

    if ignore:
        remove_fields(standard, ignore)
    if not tolerance:
        tolerance = {}

    diffs = {}
    for field in standard:
        try:
            value = series[field]
        except KeyError:
            diffs.setdefault("missing", []).append(field)
            continue
        if value != standard[field]:
            result = handle_diff(value, standard[field], tolerance.get(field))
            if result:
                diffs[field] = result
    return diffs


def remove_fields(json_contents, fields):
    for item in fields:
        try:
            del json_contents[item]
        except KeyError:
            pass


def handle_diff(value, expected, tolerance=None):
    diffs = {"expected": expected, "actual": value}

    if not tolerance:
        return diffs

    try:
        close_enough = isclose(value, expected, atol=tolerance)
    except ValueError:
        close_enough = bool_(False)

    if type(close_enough) != bool_:
        if all(close_enough):
            return {}
    elif close_enough:
        return {}

    diffs["tolerance"] = tolerance
    return diffs


def check_bvals(series_path, standard_path):
    try:
        series_bval = find_bvals(series_path)
        standard_bval = find_bvals(standard_path)
    except IOError as e:
        return {"error": f"{e}"}
    if series_bval != standard_bval:
        return {"expected": standard_bval, "actual": series_bval}
    return {}


def find_bvals(json_path):
    bval_path = json_path.replace("json", "bval")
    if not os.path.isfile(bval_path):
        raise IOError(f"bval for {json_path} does not exist")
    try:
        with open(bval_path, "r") as bval_fh:
            bvals = bval_fh.readlines()[0]
    except Exception:
        raise IOError(f"Unable to read bval file {bval_path}")
    return bvals


def write_diff_log(diffs, output_path):
    with open(output_path, "w") as dest:
        json.dump(diffs, dest)
