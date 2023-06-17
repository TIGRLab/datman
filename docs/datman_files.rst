.. include:: links.rst

---------------------
Other important files
---------------------

This page describes some additional configuration files that Datman scripts
may use.

.. _dmfiles dcm2bids:

dcm2bids.json
*************

**Used by**: ``dm_xnat_extract.py``

**Location**: the ``meta`` folder. By default this will be ``${STUDY}/metadata``.

This config file is used by dcm2bids to export raw dicom data to nifti format
in the bids file structure. It should contain one entry for each scan that must
be exported to nii format.

For more information see the `dcm2bids official documentation <https://unfmontreal.github.io/Dcm2Bids/docs/how-to/create-config-file/>`_

Example
^^^^^^^
This is a subset of the settings from one of our config files.

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

.. _dmfiles Scans:

scans.csv
*********

**Used By**: ``dm_link.py``

**Location**: the ``meta`` folder. By default this will be ``${STUDY}/metadata``.

This file helps Datman apply a correctly formatted ID to scan zip files when the
dicom headers do not contain a correct ID. Any scan zip file listed in scans.csv
will have the name from the 'target_name' column applied instead of whatever
has been entered into the dicom headers.

The 'PatientName' and 'StudyID' columns should be populated by their values from
the dicom headers to help reduce the risk of trying to rename the wrong file.
You can find these values with tools like `dcmdump` can retrieve these values.

Example
^^^^^^^

.. code-block:: csv

    source_name      target_name      PatientName         StudyID
    orig_zip_name1   intended_name1   dicom_PatientName1  dicom_StudyID1
    ...
    orig_zip_nameN   intended_nameN   dicom_PatientNameN  dicom_StudyIDN

.. _dmfiles Blacklist:

blacklist.csv
*************

**Used By**: ``dm_blacklist_rm.py``

**Location**: the ``meta`` folder. By default this will be ``${STUDY}/metadata``.

**NOTE**: This file is not used if the `QC Dashboard <https://imaging-genetics.camh.ca/datman-dashboard/>`_ is
installed. The dashboard's database stores this info instead.

This file holds the list of blacklisted scans for a study. It helps Datman identify
scans which should not be processed.

The file should contain two comma-separated columns. The header should read
'series,reason'. Each QC entry should go on it's own line and should contain
the scan's root name (the file name, minus the series description and file
extension) and the user's comment about why the scan was
blacklisted.

A scan root name appearing in this file indicates that it has been blacklisted
and should not be used. That is, you should *NOT* add an entry for scans that
pass QC, and you should **NOT** include these files when running processing
pipelines.

Example
^^^^^^^

.. code-block:: csv

    series,reason
    STUDY_SITE_0000_01_01_TAG_00,user comment goes here

.. _dmfiles Checklist:

checklist.csv
*************

**Used By**: Multiple Datman pre-processing pipelines.

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

Example
^^^^^^^

.. code-block:: csv

    qc_STUDY_CMH_0000_01.html CB
    qc_STUDY_CMH_0001_01.html AA


.. _dmfiles External:

external-links.csv
******************

**Used By**: ``dm_link_shared_ids.py``

**Location**: the ``meta`` folder. By default this will be ``${STUDY}/metadata``.

This file documents sessions that are shared with other studies. The first
column contains the ID for the session within the current study and the second
column contains the ID for a second study that the data belongs to. Multiple
entries for an ID may exist if the same session is used by multiple studies.

An optional third column can be used to specify a subset of scan types that
should be shared.

Example
^^^^^^^

.. code-block:: csv

    subject                  target_subject
    STUDY1_SITE_0000_01_01   STUDY2_SITE_0000_01_01
    STUDY1_SITE_0000_01_01   STUDY3_SITE_0000_01_01   RST
    STUDY1_SITE_0001_01_01   STUDY2_SITE_0001_01_01   T1,RST,FLAIR