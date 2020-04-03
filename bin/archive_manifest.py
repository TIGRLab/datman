#!/usr/bin/env python
"""
Prints a list of the series in an MRI exam archive tarball or directory

Usage:
    archive_manifest.py [options] <archive>...

Arguments:
    <archive>            Exam archive (zip, tarball, or folder)

Options:
     --headers=LIST      Comma separated list of dicom header names to print.
     --oneseries         Only show one series (useful for just exam info)
     --showheaders       Just list all of the headers for each archive
"""

from docopt import docopt
import pandas as pd

import datman
import datman.utils

default_headers = [
    'StudyDescription',
    'StudyID',
    'PatientName',
    'SeriesNumber',
    'SeriesDescription']


def main():
    arguments = docopt(__doc__)

    if arguments['--showheaders']:
        for archive in arguments['<archive>']:
            manifest = datman.utils.get_archive_headers(archive,
                                                        stop_after_first=False)
            filepath, headers = list(manifest.items())[0]
            print(",".join([archive, filepath]))
            print("\t" + "\n\t".join(headers.dir()))
        return

    headers = (arguments['--headers'] and arguments['--headers'].split(',')) \
        or default_headers[:]
    headers.insert(0, "Path")

    rows = []
    for archive in arguments["<archive>"]:
        manifest = datman.utils.get_archive_headers(archive)
        sortedseries = sorted(manifest.items(),
                              key=lambda x: x[1].get('SeriesNumber'))
        for path, dataset in sortedseries:
            row = {header: dataset.get(header, "") for header in headers}
            row['Path'] = path
            rows.append(row)
            if arguments['--oneseries']:
                break

    data = pd.DataFrame(rows)
    print(data.to_csv(index=False))


if __name__ == "__main__":
    main()
