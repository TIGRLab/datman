"""
A collection of utilities for generally munging imaging data. 
"""
import os.path
import re
import dicom as dcm
import zipfile
import tarfile
import io

# A dictionary that maps the series kinds to possible regexs of dicom
# description headers used in the MR Unit. 
#
# A series kind is a short, one word indication of the type of acquisition (e.g.
# T1, T2, etc..)
#
# This dictionary is formatted like so: 
#    kind -> list of description regex 
#
SERIES_KINDS_MAP = {
    "T1"           : "T1",
    "T2"           : "T2 DE",
    "DTI-60"       : "DTI 60",
    "DTI-33-b1000" : r"DTI 33\+2 b1000",
    "DTI-33-b3000" : r"DTI 33\+2 b3000",
    "DTI-33-b4500" : r"DTI 33\+2 b4500",
    "N-BACK"       : "N Back",
    "REST"         : "RestingState",
    "FLAIR"        : "FLAIR",
    "IMITATE"      : "Imitate",
    "OBSERVE"      : "Observe",
    "EA"           : "EA Task",
    "MRS-sgACC"    : "MRS sgACC",
    "MRS-DLPFC"    : "MRS DLPFC",
    "TE6.5"        : r"TE6\.5",  
    "TE8.5"        : r"TE8\.5",  
    "Aniso"        : "Fractional Aniso",  
    "Calibration"  : "Calibration",  
    "Localizer"    : "3Plane Loc SSFSE",  
} 

def guess_kind(description, kindmap = None): 
    """
    Given a series description return a list of series kinds this might be.
    
    By "series kind" we mean a short code like T1, DTI, etc.. that indicates
    more generally what the data is.

    <kindmap> is a dictionary that maps a series kind to a regex that match the
    series description dicom header. If not specified this modules
    SERIES_KINDS_MAP is used. 
    """

    if not kindmap: kindmap = SERIES_KINDS_MAP 

    # lookup matching kind based on description
    return [kind for kind,regex in kindmap.iteritems() if
            re.search(regex,description)]

def mangle(string): 
    """Mangles a string to conform with the naming scheme.

    Mangling is roughly: convert runs of non-alphanumeric characters to a dash.
    """

    return re.sub(r"[^a-zA-Z0-9.+]+","-",string)

def get_extension(path): 
    """Get the filename extension on this path. 

    This is a slightly more sophisticated version of os.path.splitext in that
    this will correctly return the extension for '.tar.gz' files, for example. :D
    """
    if path.endswith('.tar.gz'): 
        return '.tar.gz'
    if path.endswith('.nii.gz'): 
        return '.nii.gz'
    else:
        return os.path.splitext(path)[1]

def get_archive_headers(path, complete = False): 
    """
    Get dicom headers from a scan archive.

    Path can be a path to a tarball or zip of dicom folders, or a folder. It is
    assumed that this archive contains the dicoms from a single exam, organized
    into folders for each series.
    
    If complete = True, the entire archive is scanned and dicom headers from
    each folder are returned, otherwise only a single set of dicom headers are
    returned (useful if you only care about the exam details).

    Returns a dictionary that maps the folder within the archive to dicom
    headers for a file in that folder.
    """
    if zipfile.is_zipfile(path):
        return get_zipfile_headers(path, complete)
    if os.path.isfile(path) and path.endswith('.tar.gz'):
        return get_tarfile_headers(path, complete)
    elif os.path.isdir(path): 
        return get_folder_headers(path, complete)
    else: 
        raise Exception("{} must be a file or folder.".format(exam))

def get_tarfile_headers(path, complete = False): 
    """
    Get headers for a dicom file within a tarball
    """
    tar = tarfile.open(path)
    members = tar.getmembers()

    manifest = {}
    # for each dir, we want to inspect files inside of it until we find a dicom
    # file that has header information
    for f in filter(lambda x: x.isfile(), members):
        dirname = os.path.dirname(f.name)
        if dirname in manifest: continue
        try:
            manifest[dirname] = dcm.read_file(tar.extractfile(f))
            if not complete: break
        except dcm.filereader.InvalidDicomError, e:
            continue
    return manifest 

def get_zipfile_headers(path, complete = False): 
    """
    Get headers for a dicom file within a zipfile
    """
    zf = zipfile.ZipFile(path)
    
    manifest = {}
    for f in zf.namelist():
        dirname = os.path.dirname(f)
        if dirname in manifest: continue
        try:
            manifest[dirname] = dcm.read_file(io.BytesIO(zf.read(f)))
            if not complete: break
        except dcm.filereader.InvalidDicomError, e:
            continue
    return manifest 

def get_folder_headers(path, complete = False): 
    """
    Generate a dictionary of subfolders and dicom headers.
    """

    manifest = {}

    # for each dir, we want to inspect files inside of it until we find a dicom
    # file that has header information 
    for dirname, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirname,filename)
            try:
                manifest[dirname] = dcm.read_file(filepath)
                break
            except dcm.filereader.InvalidDicomError, e:
                continue
        if not complete and manifest: break
    return manifest
