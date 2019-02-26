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
    --ignore-db             Disable attempts to update database
"""
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

    if ignore_file:
        ignored_fields.extend(parse_file(ignore_file))

    series = read_json(series_json)
    standard = read_json(standard_json)
    if tolerances:
        tolerances = read_json(tolerances)

    diffs = compare_headers(series, standard, ignore=ignored_fields,
            tolerance=tolerances)

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

def write_diff_log(diffs, output_path):
    with open(output_path, 'w') as dest:
        json.dump(diffs, dest)

# def update_database(series, diffs):
#     return

if __name__ == "__main__":
    main()
