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
"""
from docopt import docopt

from datman import header_checks

def main():
    args = docopt(__doc__)
    series_json = args['<series>']
    standard_json = args['<standard>']
    output = args['--output']
    ignored_fields = args['--ignore']
    ignore_file = args['--ignore-file']
    tolerances = args['--tolerance']
    dti = args['--dti']

    if ignore_file:
        ignored_fields.extend(parse_file(ignore_file))

    if tolerances:
        tolerances = read_json(tolerances)

    diffs = header_checks.construct_diffs(series_json, standard_json,
            ignored_fields, tolerances, dti)

    if not diffs:
        return

    if output:
        header_checks.write_diff_log(diffs, output)

if __name__ == "__main__":
    main()
