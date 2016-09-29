#!/usr/bin/env python
"""
Extracts data from xnat archive folders into a few well-known formats.

Usage:
    xnat-extract.py [options] <config>

Arguments:
    <config>            Project configuration file.

Options:
    --blacklist FILE    Table listing series to ignore
    -v, --verbose       Show intermediate steps
    --debug             Show debug messages
    -n, --dry-run       Do nothing

INPUT FOLDERS
    The <archivedir> is the XNAT archive directory to extract from. This is
    defined in site:XNAT_Archive.

    This folder is expected to have the following subfolders:

    SPN01_CMH_0001_01_01/           (subject name following DATMAN convention)
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

    The <tag> is determined from project_settings.yml

NON-DICOM DATA
    XNAT puts "other" (i.e. non-DICOM data) into the RESOURCES folder, defined
    in paths:resources.

    data will be copied to a subfolder of the data directory named
    paths:resources/<scanid>, for example:

        /path/to/resources/SPN01_CMH_0001_01_01/

DEPENDENCIES
    dcm2nii

"""
from docopt import docopt
import dicom
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
import yaml

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


def extract_archive(exportinfo, archivepath, config, blacklist=None):
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
        error("{} folder is not named according to the data naming policy. Skipping".format(archivepath))
        return

    scanspath = os.path.join(archivepath,'SCANS')
    if not os.path.isdir(scanspath):
        error("{} doesn't exist. Not an XNAT archive. Skipping.".format(scanspath))
        return

    # export data to datadir/fmt/subject/
    timepoint = scanid.get_full_subjectid_with_timepoint()

    stem  = str(scanid)
    for src, header in dm.utils.get_archive_headers(archivepath).items():
        export_series(exportinfo, src, header, timepoint, stem, config, blacklist)

    # export non dicom resources
    export_resources(archivepath, config, scanid)

def export_series(exportinfo, src, header, timepoint, stem, config, blacklist):
    """
    Exports the given DICOM folder into the given formats.
    """
    description   = header.get("SeriesDescription")
    mangled_descr = dm.utils.mangle(description)
    series        = str(header.get("SeriesNumber")).zfill(2)
    tag           = dm.utils.guess_tag(mangled_descr, exportinfo)

    debug("{}: description = {}, series = {}, tag = {}".format(src, description, series, tag))

    if not tag:
        verbose("No matching export pattern for {}, descr: {}. Skipping".format(src, description))
        return
    elif type(tag) is list:
        error("Multiple export patterns match for {}, descr: {}, tags: {}".format(src, description, tag))
        return

    # update the filestem with _tag_series_description
    stem  += "_" + "_".join([tag, series, mangled_descr])

    if blacklist:
        if stem in read_blacklist(blacklist):
            debug("{} in blacklist. Skipping.".format(stem))
            return

    nii_dir = dm.utils.define_folder(os.path.join(config['paths']['nii'], timepoint))
    dcm_dir = dm.utils.define_folder(os.path.join(config['paths']['dcm'], timepoint))

    exporters = {
        "mnc" : export_mnc_command,
        "nii" : export_nii_command,
        "nrrd": export_nrrd_command,
        "dcm" : export_dcm_command,
    }
    exporters['nii'](src, nii_dir, stem)
    exporters['dcm'](src, nii_dir, stem)

def read_blacklist(blacklist):
    """
    If --blacklist is set, reads the given csv and returns a list of series
    which are blacklisted. Otherwise returns an empty list.
    """
    try:
        blacklist = pd.read_table(blacklist, sep='\s*', engine="python")
        series_list = blacklist.columns.tolist()[0]
        blacklisted_series = blacklist[series_list].values.tolist()

        return blacklisted_series

    except IOError:
        debug("{} does not exist. Running on all series".format(blacklist))
    except ValueError:
        error("{} cannot be read. Check that no entries contain white space.".format(blacklist))

def export_resources(archivepath, config, scanid):
    """
    Exports all the non-dicom resources for an exam archive.
    """
    sourcedir = os.path.join(archivepath, "RESOURCES")

    if not os.path.isdir(sourcedir):
        debug("{} isn't a directory, so won't export resources".format(sourcedir))
        return

    debug("Exporting non-dicom stuff from {}".format(archivepath))
    resources_dir = dm.utils.define_folder(os.path.join(config['paths']['resources'], str(scanid)))
    run("rsync -a {}/ {}/".format(sourcedir, resources_dir))

def export_mnc_command(seriesdir, outputdir, stem):
    """
    Converts a DICOM series to MINC format
    """
    outputfile = os.path.join(outputdir,stem) + ".mnc"

    if os.path.exists(outputfile):
        debug("{}: output {} exists. skipping.".format(
            seriesdir, outputfile))
        return

    verbose("Exporting series {} to {}".format(seriesdir, outputfile))
    cmd = 'dcm2mnc -fname {} -dname "" {}/* {}'.format(stem, seriesdir, outputdir)
    run(cmd)

def export_nii_command(seriesdir, outputdir, stem):
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
    run('dcm2nii -x n -g y -o {} {}'.format(tmpdir,seriesdir))

    # move nii in tempdir to proper location
    for f in glob.glob("{}/*".format(tmpdir)):
        bn = os.path.basename(f)
        ext = dm.utils.get_extension(f)
        if bn.startswith("o") or bn.startswith("co"):
            continue
        else:
            run("mv {} {}/{}{}".format(f, outputdir, stem, ext))
    shutil.rmtree(tmpdir)

def export_nrrd_command(seriesdir, outputdir, stem):
    """
    Converts a DICOM series to NRRD format
    """
    outputfile = os.path.join(outputdir,stem) + ".nrrd"

    if os.path.exists(outputfile):
        debug("{}: output {} exists. skipping.".format(seriesdir, outputfile))
        return

    verbose("Exporting series {} to {}".format(seriesdir, outputfile))

    cmd = 'DWIConvert -i {} --conversionMode DicomToNrrd -o {}.nrrd --outputDirectory {}'.format(
        seriesdir,stem,outputdir)

    run(cmd)

def export_dcm_command(seriesdir, outputdir, stem):
    """
    Copies a single DICOM from the series.
    """
    outputfile = os.path.join(outputdir,stem) + ".dcm"
    if os.path.exists(outputfile):
        debug("{}: output {} exists. skipping.".format(
            seriesdir, outputfile))
        return

    dcmfile = None
    for path in glob.glob(seriesdir + '/*'):
        try:
            dicom.read_file(path)
            dcmfile = path
            break
        except dicom.filereader.InvalidDicomError, e:
            pass

    assert dcmfile is not None, "No dicom files found in {}".format(seriesdir)
    verbose("Exporting a dcm file from {} to {}".format(seriesdir, outputfile))
    cmd = 'cp {} {}'.format(dcmfile, outputfile)

    run(cmd)

def parse_exportinfo(exportinfo):
    """
    Takes the dictionary structure from project_settings.yaml and returns a
    pattern:tag dictionary.

    If multiple patterns are specified in the configuration file, these are
    joined with an '|' (OR) symbol.
    """
    tags = exportinfo.keys()
    patterns = [tagtype["Pattern"] for tagtype in exportinfo.values()]

    regex = []
    for pattern in patterns:
        if type(pattern) == list:
            regex.append(("|").join(pattern))
        else:
            regex.append(pattern)

    tagmap = dict(zip(regex, tags))

    return tagmap

def main():
    global DEBUG
    global DRYRUN
    global VERBOSE
    arguments = docopt(__doc__)
    config_file    = arguments['<config>']
    blacklist      = arguments['--blacklist']
    VERBOSE        = arguments['--verbose']
    DEBUG          = arguments['--debug']
    DRYRUN         = arguments['--dry-run']

    with open(config_file, 'r') as stream:
        config = yaml.load(stream)

    for k in ['dcm', 'nii', 'mnc', 'nrrd']:
        if k not in config['paths']:
            sys.exit("ERROR: paths:{} n t defined in {}".format(k, configfile))

    sites = config['Sites'].keys()

    for site in sites:
        archive_path = config['Sites'][site]['XNAT_Archive']
        exportinfo = parse_exportinfo(config['Sites'][site]['ExportInfo'])

        archives = glob.glob(os.path.join(archive_path, '*'))

        for archive in archives:
            verbose("Exporting {}".format(archive))
            extract_archive(exportinfo, archive,  config, blacklist=blacklist)

if __name__ == '__main__':
    main()

