#!/usr/bin/env python
"""
Updates the inventory with problematic exported exam series. 

Usage: 
    update-inventory.py [options] <archivedir>...

Arguments:
    <archivedir>            Path to scan folder within the XNAT archive

Options: 
    --datadir DIR         Parent folder data is extract to 
                          [default: ./data]

    --exportinfo FILE     Export info file (see xnat-export.py)
                          [default: metadata/protocols.csv]

    --inventory FILE      File to update/output inventory to 
                          [default: metadata/inventory.csv]

    --formats LIST        Formats to check (as a comma separated list) 
                          [default: all]

DETAILS
    Problematic exports can happen in several ways: 

      1. The series is missing from the data directory, but it is listed in
         the export-info file as to be exported.

      2. More than the expected number series type are present in the data directory.
         This might mean that an acquisition was stopped prematurely and then
         restarted, The expected number of acquisitions for a type is declared
         in the export info file's "count" column. 

      3. A series that has been flagged as unusable in the inventory appears in
         the data folder.

    This program will scan the given archive for original exam acquistions, and
    and scan data directory for exported acquisitions, and then compares what
    is found with what is expected to be exported (as listed in the exportinfo
    and inventory files). 
"""
from docopt import docopt

if __name__ == '__main__':
    arguments = docopt(__doc__)
