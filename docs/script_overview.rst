.. include:: links.rst

---------------
Script Overview
---------------

This page documents some important scripts that are installed with Datman, as
well as how to use and configure them. All scripts discussed here can be
found in Datman's 'bin' folder.

dm_blacklist_rm
***************
+----------------------------+----------------------------------------------+
| **Description**            | Delete any files that have been blacklisted. |
|                            | Only removes data from the directories       |
|                            | configured by ``BlacklistDel``.              |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | None                                         |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`BlacklistDel <config BlacklistDel>`  |
|                            | * :ref:`Paths <config Paths>`                |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| * :ref:`Blacklist <dmfiles Blacklist>`       |
+----------------------------+----------------------------------------------+
| **Additional Software**    | None                                         |
| **Dependencies**           |                                              |
+----------------------------+----------------------------------------------+


dm_sftp
*******
+----------------------------+----------------------------------------------+
| **Description**            | Downloads scan zip files from an FTP Server. |
|                            |                                              |
|                            | **Note**: The user running this script must  |
|                            | have the sftp server in their 'known_hosts'  |
|                            | file.                                        |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | None                                         |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`Paths (zips, meta) <config Paths>`   |
|                            | * :ref:`FTP <config FTP>`                    |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| None                                         |
+----------------------------+----------------------------------------------+
| **Additional Software**    |                                              |
| **Dependencies**           | None                                         |
+----------------------------+----------------------------------------------+

dm_link
*******
+----------------------------+----------------------------------------------------+
| **Description**            | Apply the Datman naming convention to the          |
|                            | raw zip files. Makes correctly-named               |
|                            | symlinks in the 'dicom' folder that point to       |
|                            | the original zip files in the 'zips' folder.       |
+----------------------------+----------------------------------------------------+
| **Environment Variables**  | None                                               |
+----------------------------+----------------------------------------------------+
| **Config Settings**        | * :ref:`Paths (dicom, zips, meta) <config Paths>`  |
+----------------------------+----------------------------------------------------+
| **Additional Config Files**| * :ref:`scans.csv <dmfiles Scans>`                 |
+----------------------------+----------------------------------------------------+
| **Additional Software**    |                                                    |
| **Dependencies**           | None                                               |
+----------------------------+----------------------------------------------------+

dm_xnat_upload
**************
+----------------------------+----------------------------------------------+
| **Description**            | Uploads scan zip files from Datman's 'dicom' |
|                            | directory to the configured XNAT server.     |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | * XNAT_PASS: The XNAT user password.         |
|                            |   Overrides the config file if set.          |
|                            | * XNAT_USER: The XNAT username.              |
|                            |   Overrides the config file if set.          |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`Paths (dicom, meta) <config Paths>`  |
|                            | * :ref:`XNAT <config XNAT>`                  |
|                            | * :ref:`IdMap (Optional) <config Idmap>`     |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| None                                         |
+----------------------------+----------------------------------------------+
| **Additional Software**    |                                              |
| **Dependencies**           | None                                         |
+----------------------------+----------------------------------------------+

dm_xnat_extract
***************
+----------------------------+-------------------------------------------------------------------------------------+
| **Description**            | Downloads scan data from the configured                                             |
|                            | XNAT server and converts it to all                                                  |
|                            | configured file types.                                                              |
+----------------------------+-------------------------------------------------------------------------------------+
| **Environment Variables**  | * XNAT_PASS: The XNAT user password.                                                |
|                            |   Overrides the config file if set.                                                 |
|                            | * XNAT_USER: The XNAT username.                                                     |
|                            |   Overrides the config file if set.                                                 |
+----------------------------+-------------------------------------------------------------------------------------+
| **Config Settings**        | * :ref:`Paths <config Paths>`                                                       |
|                            | * :ref:`ExportInfo <config Export>`                                                 |
|                            | * :ref:`XNAT <config XNAT>`                                                         |
|                            | * :ref:`IdMap (Optional) <config Idmap>`                                            |
+----------------------------+-------------------------------------------------------------------------------------+
| **Additional Config Files**| * :ref:`dcm2bids config <dmfiles dcm2bids>`                                         |
+----------------------------+-------------------------------------------------------------------------------------+
| **Additional Software**    | * `dcm2niix (for nii/bids) <https://github.com/rordenlab/dcm2niix>`_                |
| **Dependencies**           | * `dcm2bids (for bids) <https://unfmontreal.github.io/Dcm2Bids/>`_                  |
|                            | * `Slicer  (for nrrd) <https://www.slicer.org/>`_                                   |
|                            | * `MINC Tool Kit (for minc) <https://www.mcgill.ca/bic/software/minc/minctoolkit>`_ |
+----------------------------+-------------------------------------------------------------------------------------+

dm_link_shared_ids
******************
+----------------------------+----------------------------------------------+
| **Description**            | Links sessions from different studies as     |
|                            | belonging to the same participant, based on  |
|                            | the contents of a REDCap survey              |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | * ``REDCAP_TOKEN``: The redcap token to use  |
|                            |   for authentication. Ignored if defined in  |
|                            |   config files.                              |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`REDCap <config Redcap>`              |
|                            | * :ref:`IdMap (Optional) <config Idmap>`     |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| * :ref:`external-links <dmfiles External>`   |
+----------------------------+----------------------------------------------+
| **Additional Software**    |                                              |
| **Dependencies**           | None                                         |
+----------------------------+----------------------------------------------+

dm_qc_report
************
+----------------------------+------------------------------------------------------+
| **Description**            | Generate QC metrics for the data in the              |
|                            | study's 'nii' folder. These will be put in           |
|                            | the study's 'qc' folder and can be displayed         |
|                            | by the QC dashboard if it is installed.              |
+----------------------------+------------------------------------------------------+
| **Environment Variables**  | None                                                 |
+----------------------------+------------------------------------------------------+
| **Config Settings**        | * :ref:`Paths (nii, qc, std, meta) <config Paths>`   |
|                            | * :ref:`Logging (Optional) <config Logs>`            |
|                            | * :ref:`Gold Standards <config Standards>`           |
+----------------------------+------------------------------------------------------+
| **Additional Config Files**| * :ref:`Checklist <config Checklist>`                |
+----------------------------+------------------------------------------------------+
| **Additional Software**    | * Matlab (R2014a)                                    |
| **Dependencies**           | * AFNI (2014)                                        |
|                            | * FSL (5.0.10)                                       |
|                            |                                                      |
|                            | Newer versions may work, but no guarantees.          |
+----------------------------+------------------------------------------------------+

dm_redcap_scan_completed
************************
+----------------------------+----------------------------------------------+
| **Description**            | Retrieve redcap 'scan completed' survey data |
|                            | from a redcap server and push it to Datman's |
|                            | QC dashboard database.                       |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | None                                         |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`Paths (meta) <config Paths>`         |
|                            | * :ref:`REDCap <config Redcap>`              |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| None                                         |
+----------------------------+----------------------------------------------+
| **Additional Software**    |                                              |
| **Dependencies**           | None                                         |
+----------------------------+----------------------------------------------+

xnat_fetch_sessions
*******************
+----------------------------+----------------------------------------------+
| **Description**            | Download XNAT sessions as raw scan zip       |
|                            | files and deposit them in the study's 'zip'  |
|                            | folder.                                      |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | None                                         |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`Paths (zips, meta) <config Paths>`   |
|                            | * :ref:`XNAT <config XNAT>`, only settings   |
|                            |   with the 'XnatSource' prefix               |
|                            | * :ref:`Logging (Optional) <config Logs>`    |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| None                                         |
+----------------------------+----------------------------------------------+
| **Additional Software**    |                                              |
| **Dependencies**           | None                                         |
+----------------------------+----------------------------------------------+

dm_task_files
*************
+----------------------------+---------------------------------------------------+
| **Description**            | Finds task files in the study's 'resources'       |
|                            | folder and symlinks them into the study's         |
|                            | 'tasks' folder with a standard name scheme.       |
+----------------------------+---------------------------------------------------+
| **Environment Variables**  | None                                              |
+----------------------------+---------------------------------------------------+
| **Config Settings**        | * :ref:`Paths (task, resources) <config Paths>`   |
|                            | * :ref:`Tasks <config Tasks>`                     |
+----------------------------+---------------------------------------------------+
| **Additional Config Files**| None                                              |
+----------------------------+---------------------------------------------------+
| **Additional Software**    |                                                   |
| **Dependencies**           | None                                              |
+----------------------------+---------------------------------------------------+

dm_parse_faces
**************
+----------------------------+----------------------------------------------+
| **Description**            | Converts eprime text files for the FACES     |
|                            | task into BIDS format .tsv files.            |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | None                                         |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`Paths (task, nii) <config Paths>`    |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| None                                         |
+----------------------------+----------------------------------------------+
| **Additional Software**    |                                              |
| **Dependencies**           | None                                         |
+----------------------------+----------------------------------------------+