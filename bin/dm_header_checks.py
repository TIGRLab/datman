#!/usr/bin/env python
"""
Usage:
    dm_header_checks.py [options] [--ignore=<STR>]... <series> <standard>

Arguments:
    <series>                Full path to the series JSON file being examined
    <standard>              Full path to the standards JSON file to compare
                            against

Options:
    --output <PATH>         Full path to store output as a file
    --ignore <STR>          A dicom header field to ignore. Can be specified
                            more than once. Can be used along with the
                            --ignore-file option
    --ignore-file <PATH>    Full path to a text file of header fields to ignore
                            with each field name on a new line. Can be used
                            alongside the --ignore option
    --tolerance <PATH>      Full path to a json file mapping field names to a
                            tolerance for that field
    --dti                   Include a bval check. If enabled, it is expected
                            that there will be a .bval file in the same dir
                            as the series (or gold standard) with the
                            same file name as the series (or gold standard)
    --ignore-db             Disable attempts to update database
"""
import os
import json

from numpy import isclose
from docopt import docopt

def main():
    args = docopt(__doc__)
    series_json = args['<series>']
    standard_json = args['<standard>']
    output = args['--output']
    ignored_fields = args['--ignore']
    ignore_file = args['--ignore-file']
    tolerances = args['--tolerance']
    ignore_db = args['--ignore-db']
    dti = args['--dti']

    if ignore_file:
        ignored_fields.extend(parse_file(ignore_file))

    if tolerances:
        tolerances = read_json(tolerances)

    diffs = construct_diffs(series_json, standard_json, ignored_fields,
            tolerances, dti)

    if not diffs:
        return

    if output:
        write_diff_log(diffs, output)

    if ignore_db:
        return

    # Will add later
    # update_database(series_json, diffs)

def parse_file(file_path):
    try:
        with open(file_path, "r") as fh:
            contents = fh.readlines()
    except Exception as e:
        raise type(e)("Couldnt read file of field names to ignore. "
                "{}".format(str(e)))
    return [line.strip() for line in contents]

def construct_diffs(series_json, standard_json, ignored_fields=None,
            tolerances=None, dti=False):
    series = read_json(series_json)
    standard = read_json(standard_json)

    diffs = compare_headers(series, standard, ignore=ignored_fields,
            tolerance=tolerances)

    if dti:
        bval_diffs = check_bvals(series_json, standard_json)
        if bval_diffs:
            diffs['bvals'] = bval_diffs

    return diffs

def read_json(json_file):
    with open(json_file, "r") as fp:
        contents = json.load(fp)
    return contents

def compare_headers(series, standard, ignore=None, tolerance=None):
    if ignore:
        remove_fields(standard, ignore)
    if not tolerance:
        tolerance = {}

    diffs = {}
    for field in standard:
        try:
            value = series[field]
        except KeyError:
            diffs.setdefault('missing', []).append(field)
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
    diffs = {'expected': expected, 'actual': value}

    if not tolerance:
        return diffs

    if isclose(value, expected, atol=tolerance):
        return {}

    diffs['tolerance'] = tolerance
    return diffs

def check_bvals(series_path, standard_path):
    try:
        series_bval = find_bvals(series_path)
        standard_bval = find_bvals(standard_path)
    except IOError as e:
        return {'Error - {}'.format(e)}
    if series_bval != standard_bval:
        return {'expected': standard_bval, 'actual': series_bval}
    return {}

def find_bvals(json_path):
    bval_path = json_path.replace('json', 'bval')
    if not os.path.isfile(bval_path):
        raise IOError("bval for {} does not exist".format(json_path))
    try:
        with open(bval_path, "r") as bval_fh:
            bvals = bval_fh.readlines()[0]
    except:
        raise IOError("Unable to read bval file {}".format(bval_path))
    return bvals

def write_diff_log(diffs, output_path):
    with open(output_path, 'w') as dest:
        json.dump(diffs, dest)

# def update_database(series, diffs):
#     return

if __name__ == "__main__":
    main()
