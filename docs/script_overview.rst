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
| **Additional Config Files**|                                              |
+----------------------------+----------------------------------------------+
| **Additional Software**    | None                                         |
| **Dependencies**           |                                              |
+----------------------------+----------------------------------------------+

dm_sftp
*******
+----------------------------+----------------------------------------------+
| **Description**            | Downloads scan zip files from an FTP Server. |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | None                                         |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`Paths (zips, meta) <config Paths>`   |
|                            | * :ref:`FTP Config <config FTP>`             |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| None                                         |
+----------------------------+----------------------------------------------+
| **Additional Software**    |                                              |
| **Dependencies**           | None                                         |
+----------------------------+----------------------------------------------+

dm_link
*******
dicom, zips,
+----------------------------+----------------------------------------------+
| **Description**            | Apply the Datman naming convention to the    |
|                            | raw zip files. Makes correctly-named         |
|                            | symlinks in the 'dicom' folder pointing              |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | None                                         |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`Paths (zips, meta) <config Paths>`   |
|                            | * :ref:`FTP Config <config FTP>`             |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| None                                         |
+----------------------------+----------------------------------------------+
| **Additional Software**    |                                              |
| **Dependencies**           | None                                         |
+----------------------------+----------------------------------------------+

dm_xnat_upload
**************
+----------------------------+----------------------------------------------+
| **Description**            | Apply the Datman naming convention to the    |
|                            | raw zip files. Makes correctly-named         |
|                            | symlinks in the 'dicom' folder pointing              |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | None                                         |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`Paths (zips, meta) <config Paths>`   |
|                            | * :ref:`FTP Config <config FTP>`             |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| None                                         |
+----------------------------+----------------------------------------------+
| **Additional Software**    |                                              |
| **Dependencies**           | None                                         |
+----------------------------+----------------------------------------------+

dm_xnat_extract
***************
+----------------------------+----------------------------------------------+
| **Description**            | Apply the Datman naming convention to the    |
|                            | raw zip files. Makes correctly-named         |
|                            | symlinks in the 'dicom' folder pointing              |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | None                                         |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`Paths (zips, meta) <config Paths>`   |
|                            | * :ref:`FTP Config <config FTP>`             |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| None                                         |
+----------------------------+----------------------------------------------+
| **Additional Software**    |                                              |
| **Dependencies**           | None                                         |
+----------------------------+----------------------------------------------+

dm_link_shared_ids
******************
+----------------------------+----------------------------------------------+
| **Description**            | Apply the Datman naming convention to the    |
|                            | raw zip files. Makes correctly-named         |
|                            | symlinks in the 'dicom' folder pointing              |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | None                                         |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`Paths (zips, meta) <config Paths>`   |
|                            | * :ref:`FTP Config <config FTP>`             |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| None                                         |
+----------------------------+----------------------------------------------+
| **Additional Software**    |                                              |
| **Dependencies**           | None                                         |
+----------------------------+----------------------------------------------+

dm_qc_report
************
+----------------------------+----------------------------------------------+
| **Description**            | Apply the Datman naming convention to the    |
|                            | raw zip files. Makes correctly-named         |
|                            | symlinks in the 'dicom' folder pointing              |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | None                                         |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`Paths (zips, meta) <config Paths>`   |
|                            | * :ref:`FTP Config <config FTP>`             |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| None                                         |
+----------------------------+----------------------------------------------+
| **Additional Software**    |                                              |
| **Dependencies**           | None                                         |
+----------------------------+----------------------------------------------+

dm_redcap_scan_completed
************************
+----------------------------+----------------------------------------------+
| **Description**            | Apply the Datman naming convention to the    |
|                            | raw zip files. Makes correctly-named         |
|                            | symlinks in the 'dicom' folder pointing              |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | None                                         |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`Paths (zips, meta) <config Paths>`   |
|                            | * :ref:`FTP Config <config FTP>`             |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| None                                         |
+----------------------------+----------------------------------------------+
| **Additional Software**    |                                              |
| **Dependencies**           | None                                         |
+----------------------------+----------------------------------------------+

xnat_fetch_sessions
*******************
+----------------------------+----------------------------------------------+
| **Description**            | Apply the Datman naming convention to the    |
|                            | raw zip files. Makes correctly-named         |
|                            | symlinks in the 'dicom' folder pointing              |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | None                                         |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`Paths (zips, meta) <config Paths>`   |
|                            | * :ref:`FTP Config <config FTP>`             |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| None                                         |
+----------------------------+----------------------------------------------+
| **Additional Software**    |                                              |
| **Dependencies**           | None                                         |
+----------------------------+----------------------------------------------+

dm_task_files
*************
+----------------------------+----------------------------------------------+
| **Description**            | Apply the Datman naming convention to the    |
|                            | raw zip files. Makes correctly-named         |
|                            | symlinks in the 'dicom' folder pointing              |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | None                                         |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`Paths (zips, meta) <config Paths>`   |
|                            | * :ref:`FTP Config <config FTP>`             |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| None                                         |
+----------------------------+----------------------------------------------+
| **Additional Software**    |                                              |
| **Dependencies**           | None                                         |
+----------------------------+----------------------------------------------+

dm_parse_faces
**************
+----------------------------+----------------------------------------------+
| **Description**            | Apply the Datman naming convention to the    |
|                            | raw zip files. Makes correctly-named         |
|                            | symlinks in the 'dicom' folder pointing              |
+----------------------------+----------------------------------------------+
| **Environment Variables**  | None                                         |
+----------------------------+----------------------------------------------+
| **Config Settings**        | * :ref:`Paths (zips, meta) <config Paths>`   |
|                            | * :ref:`FTP Config <config FTP>`             |
+----------------------------+----------------------------------------------+
| **Additional Config Files**| None                                         |
+----------------------------+----------------------------------------------+
| **Additional Software**    |                                              |
| **Dependencies**           | None                                         |
+----------------------------+----------------------------------------------+