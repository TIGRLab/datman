#!/usr/bin/env python

"""
Extracts data in a zipped set of dicoms into the supported formats.

Usage:
    dm-dcm-zip.py [options] <archivedir>

Arguments:
    <archivedir>            Path to the folder (e.g. data/dicom)

Options:
    --datadir DIR           Parent folder to extract to [default: ./data]
    --exportinfo FILE       Table listing acquisitions to export by format
                            [default: ./metadata/exportinfo.csv]
    --blacklist FILE        Table listing series to ignore
    -v, --verbose           Show intermediate steps
    --debug                 Show debug messages
    -n, --dry-run           Do nothing

INPUT FOLDERS
    The <archivedir> is the directory containing the zipped dicom archives
    (e.g.: data/dicom). Each zipped dicom archive should be named according
    to our data naming scheme. For example,

        /archive/data-2.0/ANDT/data/dicom/ANDT_CMH_101_01_01.zip

OUTPUT FOLDERS
    Each dicom series will be converted and placed into a subfolder of the
    datadir named according to the converted filetype and subject ID, e.g.

        data/
            nifti/
                ANDT_CMH_101_01/
                    (all nifti acquisitions for this subject-timepoint)

OUTPUT FILE NAMING
    Each dicom series will be and named according to the following schema:

        <scanid>_<tag>_<series#>_<description>.<ext>

    Where,
        <scanid>  = the scan id from the file name, eg. DTI_CMH_H001_01_01
        <tag>     = a short code indicating the data type (e.g. T1, DTI, etc..)
        <series#> = the dicom series number in the exam
        <descr>   = the dicom series description
        <ext>     = appropriate filetype extension

    For example, a T1 in nifti format might be named:

        DTI_CMH_H001_01_01_T1_11_Sag-T1-BRAVO.nii.gz

    The <tag> field is looked up in the export info table (e.g.
    protocols.csv), see below.

EXPORT TABLE FORMAT
    This export table (specified by --exportinfo) file should contain a lookup
    table that supplies a pattern to match against the DICOM SeriesDescription
    header and corresponding tag name. Additionally, the export table should
    contain a column for each export filetype with "yes" if the series should
    be exported to that format.

    For example:

    pattern       tag     export_mnc  export_nii  export_nrrd  count
    Localiser     LOC     no          no          no           1
    Calibration   CAL     no          no          no           1
    Aniso         ANI     no          no          no           1
    HOS           HOS     no          no          no           1
    T1            T1      yes         yes         yes          1
    T2            T2      yes         yes         yes          1
    FLAIR         FLAIR   yes         yes         yes          1
    Resting       RES     no          yes         no           1
    Observe       OBS     no          yes         no           1
    Imitate       IMI     no          yes         no           1
    DTI-60        DTI-60  no          yes         yes          3
    DTI-33-b4500  b4500   no          yes         yes          1
    DTI-33-b3000  b3000   no          yes         yes          1
    DTI-33-b1000  b1000   no          yes         yes          1

NON-DICOM DATA
    Any non-DICOM data in the zipped archive will be moved into the RESOURCES
    folder in the data directory and placed in a subfolder named
    resources/<scanid>. For example:

            data/RESOURCES/ANDT_CMH_101_01_01/

EXAMPLES

    dm-dcm-zip.py /archive/data-2.0/ANDT/data/dicom/ANDT_CMH_101_01_01.zip

"""
from docopt import docopt
import pandas as pd
import datman as dm
import datman.utils
import datman.scanid
import os.path
import sys
import subprocess as proc
import tempfile
import glob
import shutil

DEBUG  = False
VERBOSE= False
DRYRUN = False

def log(message):
    print message
    sys.stdout.flush()

def error(message):
    log("ERROR: " + message)

def main():
    global DEBUG
    global DRYRUN
    global VERBOSE
    arguments = docopt(__doc__)
    archives       = arguments['<archivedir>']
    exportinfofile = arguments['--exportinfo']
    datadir        = arguments['--datadir']
    blacklist      = arguments['--blacklist'] or []
    VERBOSE        = arguments['--verbose']
    DEBUG          = arguments['--debug']
    DRYRUN         = arguments['--dry-run']

    exportinfo = pd.read_table(exportinfofile, sep='\s*', engine="python")

    fmts = get_formats_from_exportinfo(exportinfo)
    unknown_fmts = [fmt for fmt in fmts if fmt not in exporters]

    if len(unknown_fmts) > 0:
        error("Unknown formats requested: {}. " \
              "Skipping.".format(",".join(unknown_fmts)))
        fmts = list(set(fmts) - set(unknown_fmts))

    exports = parse_table(exportinfo, fmts)




def parse_table(exportinfo, fmts):
    """
    Creates a dictionary with each format as the key and a list of patterns
    to export as the value.
    """
    exports = {}
    for fmt in fmts:
        col = 'export_' + str(fmt)
        extract = dict(zip(exportinfo['pattern'].tolist(),
                        exportinfo[col].tolist()))
        exports[fmt] = []
        for pat in extract:
            if extract[pat] == 'yes':
                exports[fmt].append(pat)

    return exports


def get_formats_from_exportinfo(dataframe):
    """
    Gets the export formats from the column names in an exportinfo table.

    Columns that begin with "export_" are extracted, and the format identifier
    from each column is returned, as a list.
    """

    columns = dataframe.columns.values.tolist()
    formats = [c.split("_")[1] for c in columns if c.startswith("export_")]
    return formats

exporters = {
    "mnc" : "Placeholder",
    "nii" : "Placeholder",
    "nrrd" : "Placeholder",
    "dcm" : "Placeholder",
}

if __name__ == '__main__':
    main()
