#!/usr/bin/env python
"""
Extracts data from xnat archive folders into a few well-known formats.

Usage: 
    extract.py [options] <archivedir>...

Arguments:
    <archivedir>            Path to scan folder within the XNAT archive

Options: 
    --datadir DIR           Parent folder to extract to [default: ./data]
    --exportinfo FILE       Table listing acquisitions to export by format
                            [default: ./metadata/exportinfo.csv]
    -v, --verbose           Show intermediate steps
    --debug                 Show debug messages
    -n, --dry-run           Do nothing

INPUT FOLDERS
    The <archivedir> is the XNAT archive directory to extract from. This should
    point to a single scan folder, and the folder should be named according to
    our data naming scheme. For example, 

        /xnat/spred/archive/SPINS/arc001/SPN01_CMH_0001_01_01

    This folder is expected to have the following subfolders: 

    SPN01_CMH_0001_01_01/
      RESOURCES/                    (optional)
        *                           (optional non-dicom data)
      SCANS/
        001/                        (series #)
          DICOM/       
            *                       (dicom files, usually named *.dcm) 
            scan_001_catalog.xml
        002/
        ...

OUTPUT FOLDERS
    Each dicom series will be converted and placed into a subfolder of the
    datadir named according to the converted filetype and subject ID, e.g. 

        data/
            nifti/
                SPN01_CMH_0001_01/
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
    This export table (specified by --exportinfo) file should contain lookup
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
    XNAT puts "other" (i.e. non-DICOM data) into the RESOURCES folder. This
    data will be copied to a subfolder of the data directory named
    resources/<scanid>, for example: 

        resources/SPN01_CMH_0001_01_01/
    
    In addition to the data in RESOURCES, the *_catalog.xml file from each scan
    series will be placed in the resources folder with the output file naming
    listed above, e.g. 

        resources/SPN01_CMH_0001_01_01/
            SPN01_CMH_0001_01_01_CAT_001_catalog.xml
            SPN01_CMH_0001_01_01_CAT_002_catalog.xml
            ... 

EXAMPLES

    xnat-extract.py /xnat/spred/archive/SPINS/arc001/SPN01_CMH_0001_01_01

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

def verbose(message): 
    if not(VERBOSE or DEBUG): return
    log(message)

def debug(message): 
    if not DEBUG: return
    log("DEBUG: " + message)

def makedirs(path):
    debug("makedirs: {}".format(path))
    if not DRYRUN: os.makedirs(path)

def run(cmd):
    debug("exec: {}".format(cmd))
    if not DRYRUN: 
        p = proc.Popen(cmd, shell=True, stdout=proc.PIPE, stderr=proc.PIPE)
        out, err = p.communicate() 
        if p.returncode != 0: 
            log("Error {} while executing: {}".format(p.returncode, cmd))
            out and log("stdout: \n>\t{}".format(out.replace('\n','\n>\t')))
            err and log("stderr: \n>\t{}".format(err.replace('\n','\n>\t')))
        else:
            debug("rtnval: {}".format(p.returncode))
            out and debug("stdout: \n>\t{}".format(out.replace('\n','\n>\t')))
            err and debug("stderr: \n>\t{}".format(err.replace('\n','\n>\t')))

def main():
    global DEBUG 
    global DRYRUN
    global VERBOSE
    arguments = docopt(__doc__)
    archives       = arguments['<archivedir>']
    exportinfofile = arguments['--exportinfo']
    datadir        = arguments['--datadir']
    VERBOSE        = arguments['--verbose']
    DEBUG          = arguments['--debug']
    DRYRUN         = arguments['--dry-run']

    exportinfo = pd.read_table(exportinfofile, sep='\s*', engine="python")

    for archivepath in archives:
        log("Exporting {}".format(archivepath))
        extract_archive(exportinfo, archivepath, datadir)


def extract_archive(exportinfo, archivepath, exportdir):
    """
    Exports an XNAT archive to various file formats.

    The <archivepath> is the XNAT archive directory to extract from. This
    should point to a single scan folder, and the folder should be named
    according to our data naming scheme. 

    This function searches through the SCANS subfolder (archivepath) for series
    and converts each series, placing them in an appropriately named folder
    under exportdir. 
    """

    archivepath = os.path.normpath(archivepath)
    basename    = os.path.basename(archivepath)

    try:
        scanid = datman.scanid.parse(basename)
    except datman.scanid.ParseException, e:
        error("{} folder is not named according to the data naming policy. " \
              "Skipping".format(archivepath))
        return

    scanspath = os.path.join(archivepath,'SCANS')
    if not os.path.isdir(scanspath):
        error("{} doesn't exist. Not an XNAT archive. "\
              "Skipping.".format(scanspath))
        return

    fmts         = get_formats_from_exportinfo(exportinfo)
    unknown_fmts = [fmt for fmt in fmts if fmt not in exporters]

    if len(unknown_fmts) > 0: 
        error("Unknown formats requested for export of {}: {}. " \
              "Skipping.".format(archivepath, ",".join(unknown_fmts)))
        return

    # export each series to datadir/fmt/subject/
    timepoint = scanid.get_full_subjectid_with_timepoint()

    stem  = str(scanid)
    for src, header in dm.utils.get_archive_headers(archivepath).items():
        export_series(exportinfo, src, header, fmts, timepoint, stem, exportdir)

    # export non dicom resources
    export_resources(archivepath, exportdir, scanid)

def export_series(exportinfo, src, header, formats, timepoint, stem, exportdir):
    """
    Exports the given DICOM folder into the given formats.
    """
    description   = header.get("SeriesDescription")
    mangled_descr = dm.utils.mangle(description)
    series        = str(header.get("SeriesNumber")).zfill(2)
    tagmap        = dict(zip(exportinfo['pattern'].tolist(),
                             exportinfo['tag'].tolist()))
    tag           = dm.utils.guess_tag(mangled_descr, tagmap)

    debug("{}: description = {}, series = {}, tag = {}".format(
        src, description, series, tag))

    if not tag or type(tag) is list: 
        error("{}: Unknown series tag for description: {}, tag = {}".format(
            src, description, tag))
        return

    tag_exportinfo = exportinfo[exportinfo['tag'] == tag]

    # update the filestem with _tag_series_description
    stem  += "_" + "_".join([tag,series,mangled_descr]) 

    for fmt in formats:
        if all(tag_exportinfo['export_'+fmt] == 'no'):
            debug("{}: export_{} set to 'no' for tag {} so skipping".format(
                src, fmt, tag))
            continue

        outputdir  = os.path.join(exportdir,fmt,timepoint)
        if not os.path.exists(outputdir): makedirs(outputdir)

        exporters[fmt](src,outputdir,stem)

def get_formats_from_exportinfo(dataframe):
    """
    Gets the export formats from the column names in an exportinfo table.

    Columns that begin with "export_" are extracted, and the format identifier
    from each column is returned, as a list. 
    """

    columns = dataframe.columns.values.tolist()
    formats = [c.split("_")[1] for c in columns if c.startswith("export_")]
    return formats

def export_resources(archivepath, exportdir, scanid):
    """
    Exports all the non-dicom resources for an exam archive.
    """
    sourcedir = os.path.join(archivepath, "RESOURCES")

    if not os.path.isdir(sourcedir):
        debug("{} isn't a directory, so won't export resources".format(
            sourcedir))
        return

    debug("Exporting non-dicom stuff from {}".format(archivepath))
    outputdir = os.path.join(exportdir,"RESOURCES",str(scanid))
    if not os.path.exists(outputdir): makedirs(outputdir)
    run("rsync -r {}/ {}/".format(sourcedir, outputdir))

def export_mnc_command(seriesdir,outputdir,stem):
    """
    Converts a DICOM series to MINC format
    """
    outputfile = os.path.join(outputdir,stem) + ".mnc"

    if os.path.exists(outputfile):
        debug("{}: output {} exists. skipping.".format(
            seriesdir, outputfile))
        return

    verbose("Exporting series {} to {}".format(seriesdir, outputfile))
    cmd = 'dcm2mnc -fname {} -dname "" {}/* {}'.format(
            stem,seriesdir,outputdir)
    run(cmd)

def export_nii_command(seriesdir,outputdir,stem):
    """
    Converts a DICOM series to NifTi format
    """
    outputfile = os.path.join(outputdir,stem) + ".nii.gz"

    if os.path.exists(outputfile):
        debug("{}: output {} exists. skipping.".format(
            seriesdir, outputfile))
        return

    verbose("Exporting series {} to {}".format(seriesdir, outputfile))

    # convert into tempdir
    tmpdir = tempfile.mkdtemp()
    run('dcm2nii -x n -g y  -o {} {}'.format(tmpdir,seriesdir))

    # move nii in tempdir to proper location
    for f in glob.glob("{}/*".format(tmpdir)):
        bn = os.path.basename(f)
        ext = dm.utils.get_extension(f)
        if bn.startswith("o") or bn.startswith("co"): 
            continue
        else:
            run("mv {} {}/{}{}".format(f, outputdir, stem, ext))
    shutil.rmtree(tmpdir)

def export_nrrd_command(seriesdir,outputdir,stem):
    """
    Converts a DICOM series to NRRD format
    """
    outputfile = os.path.join(outputdir,stem) + ".nrrd"

    if os.path.exists(outputfile):
        debug("{}: output {} exists. skipping.".format(
            seriesdir, outputfile))
        return

    verbose("Exporting series {} to {}".format(seriesdir, outputfile))

    cmd = 'DWIConvert -i {} --conversionMode DicomToNrrd -o {}.nrrd ' \
          '--outputDirectory {}'.format(seriesdir,stem,outputdir)

    run(cmd)

exporters = {
    "mnc" : export_mnc_command,
    "nii" : export_nii_command,
    "nrrd": export_nrrd_command,
}

if __name__ == '__main__':
    main()

# vim: ts=4 sw=4:
