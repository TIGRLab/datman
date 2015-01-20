"""
A collection of utilities for generally munging imaging data. 
"""
import os.path
import re
import dicom as dcm


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
    "T1"           : ["T1", "SPGR", "MPRAGE"],
    "T2"           : ["T2 DE"],
    "DTI-60"       : ["DTI 60"],
    "DTI-33-b1000" : [r"DTI 33\+2 b1000"],
    "DTI-33-b3000" : [r"DTI 33\+2 b3000"],
    "DTI-33-b4500" : [r"DTI 33\+2 b4500"],
    "N-BACK"       : ["N Back"],
    "REST"         : ["RestingState"],
    "FLAIR"        : ["FLAIR"],
    "IMITATE"      : ["Imitate"],
    "OBSERVE"      : ["Observe"],
    "OBSERVE"      : ["Observe"],
    "EA"           : ["EA Task"],
    "MRS-sgACC"    : ["MRS sgACC"],
    "MRS-DLPFC"    : ["MRS DLPFC"],
    "TE6.5"        : [r"TE6\.5"],  
    "TE8.5"        : [r"TE8\.5"],  
    "Aniso"        : ["Fractional Aniso"],  
    "Calibration"  : ["Calibration"],  
    "Localizer"    : ["3Plane Loc SSFSE"],  
} 

def guess_kind(description, kindmap = None): 
    """
    Given a series description return a list of series kinds this might be.
    
    By "series kind" we mean a short code like T1, DTI, etc.. that indicates
    more generally what the data is.

    <kindmap> is a dictionary that maps a series kind to a list of regexs that
    match the series description dicom header. If not specified this modules
    SERIES_KINDS_MAP is used. 
    """

    if not kindmap: kindmap = SERIES_KINDS_MAP 

    # lookup matching kind based on description
    return [kind for kind,regexs in kindmap.iteritems() if
        any([re.search(regex,description) for regex in regexs])]

def mangle(string): 
    """Mangles a string to conform with the naming scheme.

    Mangling is roughly: convert runs of non-alphanumeric characters to a dash.
    """
    return re.sub(r"[^a-zA-Z0-9.+]+","-",string)

def get_extension(path): 
    """Get the filename extension on this path. 

    This is a slightly more sophisticated version of os.path.splitext in that
    this will correctly return the extension for '.tar.gz' files. :D
    """
    if path.endswith('.tar.gz'): 
        return '.tar.gz'
    else:
        return os.path.splitext(path)[1]

def get_dicom_series(root): 
    """
    Given a root folder return a list of subfolders holding dicom series.
       
    This function descends from <root> looking for folders containing dicom
    files. Any such folder is taken to hold a single series.

    The return value is a list of tuples, each tuple describing a series. The
    tuple contains three things: 
        - a pydicom header object for an arbitrary file in the series
        - the path to the series folder
        - the extension of the file the headers came from (e.g. ".dcm")
    """
    series = [] 
    for seriesdir, dirnames, filenames in os.walk(root):
        for filename in filenames:
            dicom_path = os.path.join(seriesdir,filename)
            try:
                headers = dcm.read_file(dicom_path)
                ext     = get_extension(dicom_path)
                series.append((headers,seriesdir,ext))
                break 
            except dcm.filereader.InvalidDicomError, e:
                continue
    return series
