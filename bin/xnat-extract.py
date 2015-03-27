#!/usr/bin/env python
"""
Extracts data from xnat archive folders into a few well-known formats.

Usage: 
    extract.py [options] <archivedir>...

Arguments:
    <archivedir>            Path to scan folder within the XNAT archive

Options: 
    --targetdir DIR         Parent folder to extract to [default: ./data]
    --exportinfo FILE       Table listing acquisitions to export by format
                            [default: ./metadata/protocols.csv]
    --verbose               Verbose logging

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
    --targetdir named according to the converted filetype and subject ID, e.g. 

        data/
            nifti/
                SPN01_CMH_0001/
                    (all nifti acquisitions for this subject)
    
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

       studycode  series_pattern  tag     export_mnc  export_nifti  export_nrrd
       DTIG1MR    Localiser       LOC     no          no            no
       DTIG1MR    Calibration     CAL     no          no            no
       DTIG1MR    Aniso           ANI     no          no            no
       DTIG1MR    HOS             HOS     no          no            no
       DTIG1MR    T1              T1      yes         yes           yes
       DTIG1MR    T2              T2      yes         yes           yes
       DTIG1MR    FLAIR           FLAIR   yes         yes           yes
       DTIG1MR    Resting         RES     no          yes           no
       DTIG1MR    Observe         OBS     no          yes           no
       DTIG1MR    Imitate         IMI     no          yes           no
       DTIG1MR    DTI-60          DTI-60  no          yes           yes
       DTIG1MR    DTI-33-b4500    b4500   no          yes           yes
       DTIG1MR    DTI-33-b3000    b3000   no          yes           yes
       DTIG1MR    DTI-33-b1000    b1000   no          yes           yes

NON-DICOM DATA
    XNAT puts "other" (i.e. non-DICOM data) into the RESOURCES folder. This
    data will be copied to a subfolder of the target directory named
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
