.. include:: links.rst

---------------------
Other important files
---------------------

This page describes some additional configuration files that Datman scripts
may use.

.. _dm-files dcm2bids:

dcm2bids.json
*************

**Location**: the ``meta`` folder. By default this will be ``${STUDY}/metadata``.

This config file is used by dcm2bids to export raw dicom data to nifti format
in the bids file structure. It should contain one entry for each scan that must
be exported to nii format.

For more information see the `dcm2bids official documentation <https://unfmontreal.github.io/Dcm2Bids/docs/how-to/create-config-file/>`_

File Format
^^^^^^^^^^^
This is an example config file used by one of our studies (PREDICTS).

.. code-block:: json

    {"descriptions": [
        {
            "dataType": "anat",
            "modalityLabel": "T1w",
            "criteria": {
                "SeriesDescription": "*Sag_MPRAGE_T1*"
            }
        },
        {
            "dataType": "anat",
            "modalityLabel": "ideal",
            "criteria": {
                "SeriesDescription": "*3D*Ax*IDEAL*IQ*BH*"
            }
        },
        {
            "dataType": "anat",
            "modalityLabel": "LAVA",
            "criteria": {
                "SeriesDescription": "*3D*Ax*LAVA*BH*"
            }
        },
        {
            "dataType": "func",
            "modalityLabel": "bold",
            "customLabels": "task-rest",
            "criteria": {
                "SeriesDescription": "*RS_fMRI_Run*"
            },
            "sidecarChanges": {
                "B0FieldIdentifier": "pepolar_rest_fmap"
            }
        },
        {
            "dataType": "dwi",
            "modalityLabel": "dwi",
            "criteria": {
                "SeriesDescription": "DTI"
            },
            "sidecarChanges": {
                "B0FieldIdentifier": "pepolar_dwi_fmap"
            }
        },
        {
            "dataType": "fmap",
            "modalityLabel": "epi",
            "customLabels": "acq-rest_dir-AP",
            "criteria": {
                "SeriesDescription": "*fMRI_FieldMap",
                "PhaseEncodingDirection": "j-"
            },
            "sidecarChanges": {
                "B0FieldSource": "pepolar_rest_fmap"
            }
        },
        {
            "dataType": "fmap",
            "modalityLabel": "epi",
            "customLabels": "acq-rest_dir-PA",
            "criteria": {
                "SeriesDescription": "*fMRI_FieldMap",
                "PhaseEncodingDirection": "j"
            },
            "sidecarChanges": {
                "B0FieldSource": "pepolar_rest_fmap"
            }
        },
        {
            "dataType": "fmap",
            "modalityLabel": "epi",
            "customLabels": "acq-dwi_dir-AP",
            "criteria": {
                "SeriesDescription": "DTI_FieldMap",
                "PhaseEncodingDirection": "j-"
            },
            "sidecarChanges": {
                "B0FieldSource": "pepolar_dwi_fmap"
            }
        }
    ]}

.. _dm-files Blacklist:

blacklist.csv
*************

**Location**: the ``meta`` folder. By default this will be ``${STUDY}/metadata``.

**NOTE**: This file is not used if the `QC Dashboard <https://imaging-genetics.camh.ca/datman-dashboard/>`_ is
installed. The dashboard's database stores this info instead.

This file holds the list of blacklisted scans for a study. It helps Datman identify
scans which should not be processed.

File Format
^^^^^^^^^^^
This file should contain two comma-separated columns. The header should read
'series,reason'. Each QC entry should go on it's own line and should contain
the scan's root name and the user's comment about why the scan was
blacklisted.

The scan's root name is the scan file name with the series-description and
file extension truncated.

A scan root name appearing in this file indicates that it has been blacklisted
and should not be used. That is, you should *NOT* add an entry for scans that
pass QC.

.. code-block:: csv

    series,reason
    STUDY_SITE_0000_01_01_TAG_00,user comment goes here

scans.csv
*********

**Location**: the ``meta`` folder. By default this will be ``${STUDY}/metadata``.

This file helps Datman apply a correctly formatted ID to scan zip files when the
dicom headers do not contain a correct ID. It's read by ``dm_scans.py``. Any
scan zip file listed in scans.csv will have the name from the 'target_name'
column applied instead of whatever has been entered into the dicom headers.

The 'PatientName' and 'StudyID' columns should be populated by their values from
the dicom headers to help reduce the risk of trying to rename the wrong file.
You can find these values with tools like `dcmdump` can retrieve these values.

File Format
^^^^^^^^^^^

.. code-block:: csv

    source_name      target_name      PatientName         StudyID
    orig_zip_name1   intended_name1   dicom_PatientName1  dicom_StudyID1
    ...
    orig_zip_nameN   intended_nameN   dicom_PatientNameN  dicom_StudyIDN


checklist.csv
*************

**Location**: the ``meta`` folder. By default this will be ``${STUDY}/metadata``.

**NOTE**: This file is not used if the `QC Dashboard <https://imaging-genetics.camh.ca/datman-dashboard/>`_ is
installed. The dashboard's database stores this info instead.

This file holds a record of which sessions have had Quality Control (QC)
performed. For some Datman scripts a session must undergo QC before the
session will be processed.

When Datman generates a QC page for a session the name of the QC page gets
added to checklist.csv. When a user is finished reviewing the data, they
should add their initials in a space separated column to indicate it has been
reviewed.

File Format
^^^^^^^^^^^

.. code-block:: csv

    qc_STUDY_CMH_0000_01.html CB
    qc_STUDY_CMH_0001_01.html AA
