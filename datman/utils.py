"""
A collection of utilities for generally munging imaging data. 
"""
import os.path
import re
import dicom as dcm
import zipfile
import tarfile
import io
import glob

SERIES_TAGS_MAP = {
"T1"         :  "T1",
"T2"         :  "T2",
"DTI"        :  "DTI",
"Back"       :  "NBACK",
"Rest"       :  "REST",
"FLAIR"      :  "FLAIR",
"Imitat"     :  "IMI",
"Observ"     :  "OBS",
"EA.Task"    :  "EA",
"MRS.sgACC"  :  "MRS-sgACC",
"MRS.DLPFC"  :  "MRS-DLPFC",
"TE6.5"      :  "TE6.5",
"TE8.5"      :  "TE8.5",
"Frac"       :  "ANI",
"Cal"        :  "CAL",
"Loc"        :  "LOC",
} 

def guess_tag(description, tagmap = SERIES_TAGS_MAP): 
    """
    Given a series description return a list of series tags this might be.
    
    By "series tag" we mean a short code like T1, DTI, etc.. that indicates
    more generally what the data is (usually the DICOM header
    SeriesDescription).

    <tagmap> is a dictionary that maps a regex to a series tag, where the regex
    matches the series description dicom header. If not specified this modules
    SERIES_TAGS_MAP is used. 
    """
    matches = [tag for p,tag in tagmap.iteritems() if re.search(p,description)]
    if len(matches) == 0: return None
    if len(matches) == 1: return matches[0]
    return matches

def mangle(string): 
    """Mangles a string to conform with the naming scheme.

    Mangling is roughly: convert runs of non-alphanumeric characters to a dash.
    """
    return re.sub(r"[^a-zA-Z0-9.+]+","-",string)

def get_extension(path): 
    """
    Get the filename extension on this path. 

    This is a slightly more sophisticated version of os.path.splitext in that
    this will correctly return the extension for '.tar.gz' files, for example.
    :D
    """
    if path.endswith('.tar.gz'): 
        return '.tar.gz'
    if path.endswith('.nii.gz'): 
        return '.nii.gz'
    else:
        return os.path.splitext(path)[1]

def get_archive_headers(path, stop_after_first = False): 
    """
    Get dicom headers from a scan archive.

    Path can be a path to a tarball or zip of dicom folders, or a folder. It is
    assumed that this archive contains the dicoms from a single exam, organized
    into folders for each series.

    The entire archive is scanned and dicom headers from a single file in each
    folder are returned as a dictionary that maps path->headers.
    
    If stop_after_first == True only a single set of dicom headers are
    returned for the entire archive, which is useful if you only care about the
    exam details.
    """
    if os.path.isdir(path): 
        return get_folder_headers(path, stop_after_first)
    elif zipfile.is_zipfile(path):
        return get_zipfile_headers(path, stop_after_first)
    elif os.path.isfile(path) and path.endswith('.tar.gz'):
        return get_tarfile_headers(path, stop_after_first)
    else: 
	raise Exception("{} must be a file (zip/tar) or folder.".format(exam))

def get_tarfile_headers(path, stop_after_first = False): 
    """
    Get headers for dicom files within a tarball
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
            if stop_after_first: break
        except dcm.filereader.InvalidDicomError, e:
            continue
    return manifest 

def get_zipfile_headers(path, stop_after_first = False): 
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
            if stop_after_first: break
        except dcm.filereader.InvalidDicomError, e:
            continue
    return manifest 

def get_folder_headers(path, stop_after_first = False): 
    """
    Generate a dictionary of subfolders and dicom headers.
    """

    manifest = {}

    # for each dir, we want to inspect files inside of it until we find a dicom
    # file that has header information 
    subdirs = []
    for filename in os.listdir(path):
        filepath = os.path.join(path,filename)
        try:
            if os.path.isdir(filepath): 
                subdirs.append(filepath)
                continue
            manifest[path] = dcm.read_file(filepath)
            break
        except dcm.filereader.InvalidDicomError, e:
            pass

    if stop_after_first: return manifest

    # recurse
    for subdir in subdirs: 
        manifest.update(get_folder_headers(subdir, stop_after_first))
    return manifest

def get_all_headers_in_folder(path, recurse = False): 
    """
    Get DICOM headers for all files in the given path. 

    Returns a dictionary mapping path->headers for *all* files (headers == None
    for files that are not dicoms).
    """

    manifest = {}
    for dirname, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirname,filename)
            headers = None
            try:
                headers = dcm.read_file(filepath)
            except dcm.filereader.InvalidDicomError, e:
                continue
            manifest[filepath] = headers 
        if not recurse: break
    return manifest

def col(arr, colname):
    """
    Return the named column of an ndarray. 

    Column names are given by the first row in the ndarray
    """
    idx = np.where(arr[0,] == colname)[0]
    return arr[1:,idx][:,0]
