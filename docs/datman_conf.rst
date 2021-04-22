.. include:: links.rst
.. _datman-conf:
-------------------
Configuration Files
-------------------

Datman requires a main configuration file to run. This can be constructed from
the template file ``main_config.yml`` found in datman's
``assets/config_templates/`` folder. Datman also requires a study config file
for each study it manages. You can use ``study_config.yml``, found in the same
folder, to construct these.

Points to keep in mind when configuring Datman:

1. The configuration files are all `yaml format <https://en.wikipedia.org/wiki/YAML>`_
2. Keys are case-sensitive
3. Keys are expected to be CamelCase
4. Every setting (except SystemSettings) can be overridden by a study or
   a scan site within a study. See `Overriding settings`_ for more info.


Overriding Settings
-------------------
Defining a setting in a 'more specific' context will override any setting
defined in a less specific block.

From **most** specific settings to **least** it goes:

1. Settings within a 'Sites' block in a study config file
2. Settings outside of all 'Sites' blocks in the same study config file
3. Settings within the main config file

As an example, assume you have a main config file with the following
xnat configuration:

.. code-block:: yaml

   XnatServer: xnat.com
   XnatArchive: MyProject

And you have StudyA with the following xnat configuration in its study
configuration file:

.. code-block:: yaml

   XnatArchive: StudyA


When you run xnat scripts (like dm_xnat_extract.py) on StudyA the scripts will
find 'xnat.com' for XnatServer and will use 'StudyA' for the XnatArchive
(instead of the default 'MyProject').

Assume you have another study, StudyB, with the following in its study
configuration file:

.. code-block:: yaml

   XnatArchive: StudyB

   Sites:
      CMH:
          XnatArchive: StudyB_CMH
      YRK:
          XnatServer: anotherxnat.com
      UTO:
          # This site exists for the example, but doesnt define any xnat settings

Running xnat scripts on StudyB will mean that the XNAT settings will
change depending on what site tag a scan has. The table below details
what settings are used for each of the three defined sites in StudyB.

+------------+-------------------------------+----------------------------+
| Site Tag   | XnatServer                    | XnatArchive                |
+============+===============================+============================+
| CMH        | xnat.com (main config)        | StudyB_CMH (site config)   |
+------------+-------------------------------+----------------------------+
| YRK        | anotherxnat.com (site config) | StudyB (study config)      |
+------------+-------------------------------+----------------------------+
| UTO        | xnat.com (main config)        | StudyB (study config)      |
+------------+-------------------------------+----------------------------+


Glossary
--------

## Misc. Settings
There are a few site wide settings that are not part of any configuration block and that are only needed for a few datman scripts. These are documented here, along with the name of the scripts that use these values.

* **REDCAPAPI**
  * Description: The full URL to the site's REDCap server where 'scan completed' forms are stored
  * Used by:
    * dm_link_shared_ids.py - Reads shared IDs / session aliases from this server







ExportSettings
**************
This block defines the expected scan tags. Each tag has its own dictionary of
config values that defines which formats to convert to, which QC function to
use for human data, which QC function to use for phantoms with that tag, and
any bids export settings (if converting to bids format).

**NOTE:** Any settings from this block can be overridden by the 'ExportInfo'
block in a study config file.



******************** REPLACE 'ExportInfo' WITH REFERENCE***************



Required
^^^^^^^^
The following settings must be defined to set defaults for each tag that exists

* **Formats**

  * Description: This should be a list of formats to convert any series
    matching this tag to.
  * Accepted values: 'nii', 'dcm', 'mnc', 'nrrd'
* **QcType**

  * Description: This defines the QC function to use in dm_qc_report.py to
    process human data that is assigned this scan tag.
  * Accepted values: 'anat', 'fmri', 'dti', 'ignore'
* **QcPha**

  * Description: This setting defines the QC function to use in dm_qc_report.py
    to process phantom data that is assigned this tag.
  * Accepted values: 'qa_dti', 'abcd_fmri', or 'default'. You can also omit
    'QcPha' entirely and it will be treated as though 'default' as set.

Optional
^^^^^^^^
Default values can optionally be set for any of the keys usually set in
ExportInfo. To see available keys and advice for setting them see the
[ExportInfo section in 'Sites Block'.](#sites-block)

*************************** REPLACE ExportInfo reference**********************

Example
^^^^^^^
The following is a small excerpt from our own ExportSettings

.. code-block:: yaml

  ExportSettings:
    T1:         { Formats: ['nii', 'dcm', 'mnc'], QcType: anat, QcPha: default }
    T2:         { Formats: ['nii', 'dcm'], QcType: anat }
    RST:        { Formats: ['nii', 'dcm'], QcType: fmri }
    SPRL:       { Formats: ['nii'], QcType: fmri }
    DTI60-1000: { Formats: ['nii', 'dcm', 'nrrd'], QcType: dti, QcPha: qa_dti }
    FMAP:       { Formats: ['nii', 'dcm'], QcType: ignore }
    DTI-ABCD:   { Formats: ['nii', 'dcm'], QcType: dti, Pattern: 'ABCD_dMRI$' }

In this example all of the tags except DTI60-1000 will use the default phantom
QC for their respective QcType. The last tag (DTI-ABCD) provides an example
of using one of the optional settings to set up a default series
description pattern for study. Any study with the same tag in
their ExportInfo can override this by including their own 'Pattern' setting.

FTP
***
These settings manage SFTP access and are needed by scripts like dm_sftp.py
that attempt to access one or more SFTP servers. **NOTE:** The SFTP server
settings do NOT need to be defined in the main config file, but if you don't
set defaults there you will have to ensure that the settings are provided
in each study config file to avoid exceptions.

Required
^^^^^^^^
* **FtpServer**:

  * Description: The fully qualified domain name, or IP address, of an SFTP
    server that new MRI scans will be pulled from.

* **MrFolder**

  * Description: A folder name, list of folder names, or python regex(s) to
    help locate the folder containing scan zip files on the SFTP server.
  * Accepted values: A string (may be a literal string or a regex) or a list
    of strings.

* **MrUser**

  * Description: The username to log in to the SFTP server with.

Optional
^^^^^^^^
* **FtpPort**

  * Description: The port on the server to connect to. If omitted, port 22 is used.
  * Default: 22
  * Accepted values: an integer

* **MrFtpPass**

  * Description: The name of the file in the each study's metadata folder to get the SFTP
    password from. If omitted, a file named 'mrftppass.txt' is searched for.
  * Default: 'mrftppass.txt'

Example
^^^^^^^
.. code-block:: yaml

  FtpServer: mysftp.ca
  FtpPort: 777
  MrFtpPass: myftppass.txt   # Should exist in $STUDY/metadata/
  MrUser: myuser
  MrFolder: ["somefolder", "scans*", "myscans[1-9]"]

In the above example the MrFolder setting will cause any folders on the
'mysftp.ca' server that are literally named "somefolder", that start with
"scans" or that start with "myscans" followed by a number between 1 and 9 to
be searched for scan zip files.

IdMap
*****
Provides a method of translating between ID schemes (Datman to KCNI or vice
versa).

Optional
^^^^^^^^
* **Study**:

  * Description: Maps the expected value for the KCNI study field to the
    expected value for the Datman study field.
* **Site**:

  * Description: Maps the expected value for the KCNI site field to the
    expected value for the Datman site field.
* **Subject**:

  * Description: Converting subject IDs between naming conventions is
    more complicated. It requires two pairs of
    `python style regexes <https://docs.python.org/3/howto/regex.html>`_. The
    first pair matches the portion of the KCNI subject ID that must be
    preserved for the Datman subject ID field and shows how to mangle this
    portion into Datman format. The second pair reverses this: it provides the
    regex that shows what part of the Datman subject field to preserve and a
    regex to mangle this portion into a KCNI subject ID field. Each pair of
    regexes is separated by '->' to indicate where one regex ends and the next
    begins. See the 'Example' section for specific examples.

Example
^^^^^^^
.. code-block:: yaml

  IdMap:
    # Any of the below sections can be omitted if the field doesnt change
    # between conventions.
    # Left side (keys) are KCNI convention, right side (values) Datman convention.
    #
    # KCNI ID                               Datman ID
    # STU01_UTO_10001_01_SE01_MR  becomes   STUDY1_UT2_ABC0001_01_01
    Study:
      STU01: STUDY1
    Site:
      UTO: UT2
    Subject:
      '1(P?[0-9]+)->ABC\1': 'ABC(P?[0-9]+)->1\1'

Logs
****
These settings manage log configuration for datman's log server
(dm_log_server.py) and for scripts that are able to log to it.

Required
^^^^^^^^
* **LogServer**

  * Description: The domain name or IP address of the machine that the log
    server (dm_log_server.py) will listen on. This is also read by scripts
    that output log messages to find the log server.
* **ServerLogDir**

  * Description: The full path to the directory where dm_log_server.py should
    store all logs. This directory should be accessible to the machine running
    the log server (i.e. a path local on that machine or an NFS directory
    mounted to it). Only needed if LogServer is set.

Example
^^^^^^^
.. code-block:: yaml

  LogServer: 111.222.333.444
  LogServerDir: /var/logs/datman_logs

Paths
*****
This block determines the structure of each Datman managed study. Each time a
new pipeline folder or other resource is added to your projects a new entry
needs to be added to the list. The keys are a short descriptive name for the
folder and the values are the relative path the folder should be given within
configured studies.

Required
^^^^^^^^
Below is a list of paths that must be configured for Datman to function
correctly. Most of the core scripts read from or write to the directories
listed here.

* **meta**: Points to the folder meant to hold metadata like scans.csv,
  blacklist.csv, checklist.csv, etc.
* **data**: Parent folder for the original dicom data and its other raw formats
  like nifti, mnc, etc.
* **dcm**: The folder that will hold raw dicom data. Only one dicom image per
  series is stored here
* **dicom**: The folder that will hold raw zip files of dicoms before the
  site naming convention is applied
* **zips**: The folder that holds correctly named links that point to the raw
  zip files in the 'dicom'
* **resources**: The folder that holds all non-dicom data that was present in
  the raw zip files
* **nii, mnc, nrrd**: Folders that hold the converted data in nifti, mnc and
  nrrd formats respectively. If a format will not be used by your site
  (e.g. mnc) you can omit it.
* **qc**: Holds all the QC pipeline outputs
* **logs**: The folder that will store log output from various scripts and
  nightly pipelines

Optional
^^^^^^^^
These paths must be configured if the scripts listed are in use, but may be
omitted otherwise

* **std**

  * Description: Points to the folder that will hold gold standards to be used
    when comparing dicom header parameters. These gold standards should be
    stored as json files with the expected values for important DICOM header
    fields.
  * Used by:

    *  dm_qc_report.py - Reads from this folder

* **task**

  * Description: Points to the folder that holds the any fmri task files.
  * Used by:

    * dm_task_files.py - Writes to this folder
    * dm_parse_ea.py - Reads from this folder
    * dm_parse_Nback.py - Reads from this folder
    * dm_parse_GNGo.py - Reads from this folder

* **bids**

  * Description: Points to the folder that holds the raw data organized into
    bids format.
  * Used by:

    * bidsify.py - Writes to this folder

Example
^^^^^^^
This example is a subset of all keys available.

.. code-block:: yaml
   Paths:
      # The paths on the right can be modified as preferred
      meta: metadata/
      std:  metadata/standards/
      data: data/
      dcm:  data/dcm/
      nii:  data/nii/
      nrrd: data/nrrd/
      qc:   qc/
      log:  logs/

Assuming a configuration where the `DatmanProjectsDir` is set to
`/archive/data` (as it is in ours) and a `ProjectDir` of `SPINS` the above
settings would generate a project with the following folder structure:

::

  /archive/data/SPINS/
                     │
                     └─── metadata
                     │   │
                     │   └─── standards
                     │
                     └─── data
                     │   │
                     │   └─── dcm
                     │   │
                     │   └─── mnc
                     │   │
                     │   └─── nrrd
                     │
                     └─── qc
                     │
                     └─── logs


Projects
********
The projects block contains a list of short-hand codes for each study that
Datman is expected to manage. Each code **must** be unique and is
case-sensitive. Each defined project should map to the name of that study's
config file. These files will be searched for in the ConfigDir
for the current system (as set by the shell variable DM_SYSTEM).

Example
^^^^^^^
.. code-block:: yaml

   # Note that 'Projects' is CamelCase, but study codes may be whatever
   # case you like. You must use that same capitalization when
   # using any datman script on a project (e.g. dm_xnat_extract,py StUdYc)
   Projects:
     Study1: study1_config.yml
     STUDYB: STUDYB.yml
     StUdYc: mystudy.yaml

REDCap
******
Any settings needed to use REDCap integrations are described below. These
settings are used by scripts like `dm_redcap_scan_complete.py`,
`dm_link_shared_ids.py`.

Required
^^^^^^^^
* **RedcapApi**:

  * Description: The URL for the REDCap API endpoint.
  * Used by: dm_link_shared_ids.py
* **RedcapUrl**:

  * Description: The URL for the REDCap server to pull information from.
  * Used by: dm_redcap_scan_complete.py
* **RedcapProjectId**:

  * Description: The project ID to use when retrieving records.
* **RedcapInstrument**:

  * Description: The instrument to retrieve records from.
  * Accepted values: a string.
* **RedcapEventId**:

  * Description: A dictionary of event names mapped to their IDs.
  * Accepted values: A dictionary.

* **RedcapRecordKey**:

  * Description: The name of the survey field that contains the unique record
    ID.
  * Accepted values: a string.

Optional
^^^^^^^^
* **RedcapSubj**:

  * Description: The name of the survey field that holds the session ID
  * Default: 'par_id'
* **RedcapDate**:

  * Description: The name of the survey field that holds the date the survey
    was completed.
  * Default: 'date'
* **RedcapStatus**:

  * Description: The name of the survey field that will indicate whether the
    form is complete.
  * Default: 'tigrlab_scan_completed_complete'
* **RedcapStatusValue**:

  * Description: A value or list of values that RedcapStatus may take to
    indicate that the form is complete.
  * Accepted values: a list of strings or a string.
  * Default: '2'
* **RedcapComments**:

  * Description: The name of the survey field that holds comments from the
    RA who attended the scan.
  * Default: 'cmts'
* **RedcapToken**:

  * Description: The name of the file that will hold the token to access
    REDCap's API. The file should be stored in the study metadata folder and
    be readable to the user(s) who will run any of datman's redcap scripts.
    If undefined the environment variable REDCAP_TOKEN will be used instead.
    Note that, unlike the RedcapToken setting, the REDCAP_TOKEN variable should
    contain the token itself and not the name of a file to read a token from.

* **UsesRedcap**:

  * Description: Indicates whether to expect a redcap 'scan completed' survey
    for sessions in a study (or site).
  * Default: False
  * Used by: QC Dashboard

Example
^^^^^^^
.. code-block:: yaml

  UsesRedcap: True    # if unset, is treated as False
  RedcapApi: myredcapserver.com/api
  RedcapUrl: myredcapserver.com
  RedcapToken: 'mytoken.txt'  # Should exist in $STUDY/metadata,
                              # if unset, REDCAP_TOKEN env var is read
  RedcapProjectId: '1111'
  RedcapInstrument: 'my_instrument'
  RedcapEventId:
    arm1: 111   # Each entry should be event label mapped to its ID
    arm2: 112
    arm3: 999
  RedcapSubj: 'sub_id_field'      # If unset, 'par_id' is used
  RedcapDate: 'date_field'        # If unset, 'date' is used
  RedcapStatus: 'is_complete'     # If unset, 'tigrlab_scan_completed_complete' is used
  RedcapStatusValue: ['1', '2']   # If unset, '2' is used
  RedcapRecordKey: 'record_id_field'
  RedcapComments: 'comment_field' # If unset, 'cmts' is used


Study Metadata
**************
These settings should be included in each study's config file.

Required
^^^^^^^^
* **ProjectDir**:

  * Description: The name of the folder that will hold all of the study's
    contents. This folder will be created inside the current system's
    DatmanProjectsDir if it does not already exist.
* **StudyTag**:

  * Description: The tag that will be used for the 'study' field in each
    session's `ID. <http://imaging-genetics.camh.ca/documentation/#/data/introduction/Data-Naming>`_


Optional
^^^^^^^^
* **FullName**:

  * Description: The full name of the study.
* **Description**:

  * Description: A freeform description of the study and the data it contains.
* **PrimaryContact**:

  * Description: The name of the contact for the study.
* **IsOpen**:

  * Description: Whether the study is still collecting data.
  * Default: True
  * Accepted values: A python boolean.

Example
^^^^^^^
.. code-block:: yaml

  ProjectDir: testing
  StudyTag: TEST
  FullName: Test datman installation
  Description: This is a temporary study used to test against.
  PrimaryContact: Clevis Boxx

SystemSettings
**************
At least one system must be configured. This block can allow
multiple users to have their own separately managed Datman projects or allow
one installed copy of datman to manage projects stored in separate locations.

To run datman you must set the shell variable DM_SYSTEM to the name of one
of the systems defined here (DM_SYSTEM is case-sensitive).

Required
^^^^^^^^
* **DatmanProjectsDir**: Must be the full path to the folder where a set of datman
  managed projects will be kept. For example, on our local system this is
  `/archive/data/`
* **DatmanAssetsDir**: The full path to datman's assets folder. For example, on our
  local system this is `/archive/code/datman/assets/`
* **ConfigDir**: The full path to the folder where all configuration files are
  stored. For example, on our system this is `/archive/code/config/`

Optional
^^^^^^^^
* **Queue**: This specifies the type of queue that jobs will be submitted to if a
  queue is available. Currently this can be either 'sge' or 'slurm'.

Example
^^^^^^^
.. code-block:: yaml

   SystemSettings:
      # You can capitalize system names however you like but when setting
      # DM_SYSTEM you must match the case exactly (e.g. DM_SYSTEM=testing)
      MySystem:
          DatmanProjectsDir: /archive/data
          DatmanAssetsDir: /archive/code/datman/assets
          ConfigDir: /archive/code/config
          Queue: slurm
      testing:
          # Note that 'testing' is using the same copy of datman (i.e. datman
          # is only installed once) but the data + config files are located elsewhere
          DatmanProjectsDir: /tmp/data/
          DatmanAssetsDir: /archive/code/datman/assets
          ConfigDir: /tmp/data/config

XNAT
****
These settings are used by scripts that interact with XNAT, such as
dm_xnat_upload.py and dm_xnat_extract.py.

Required
^^^^^^^^
* **XnatArchive**

  * Description: The name of a project on XNAT to read from / write to. Must
    match the Project ID (not project title) on XNAT exactly.
* **XnatServer**

  * Description: Contains the full URL or IP address of the XNAT server to use

Optional
^^^^^^^^
* **XnatConvention**

  * Description: The naming convention to use on the XNAT server. May differ
    from the naming convention used in the archive (which is Datman). If
    not specified, defaults to 'DATMAN'.
  * Accepted values: 'DATMAN' or 'KCNI'
* **XnatCredentials**

  * Description: The name of a file in the study metadata folder that will
    contain the username and password for the XNAT server. The file must
    contain the username on the first line, and the password on the second line.
    If this setting is provided, it will override the environment variables
    `XNAT_USER` and `XNAT_PASS`.
* **XnatPort**

  * Description: Specifies which port to connect to on the server. If not
    specified, port 443 is used (the standard https port).
  * Accepted values: an integer.
* **XnatSource**

  * Description: The domain name or IP address of the XNAT server to pull new
    scan zip files from. Only used when a second XNAT server is treated as the
    source for new scan data (instead of an SFTP server). If defined,
    XnatSourceArchive and XnatSourceCredentials must also be defined.
  * Used by: xnat_fetch_sessions.py
* **XnatSourceArchive**

  * Description: The Project ID on XnatSource to pull new scans from. Must be
    defined if XnatSource is.
  * Used by: xnat_fetch_sessions.py
* **XnatSourceCredentials**

  * Description: The name of the file in the study metadata folder that will
    hold the username and password for the XnatSource server. The file must
    contain the username on the first line and the password on the second line.
    Must be defined if XnatSource is defined.
  * Used by: xnat_fetch_sessions.py

Example
^^^^^^^
.. code-block:: yaml

  XnatServer: myxnat.ca
  XnatPort: 777
  XnatArchive: MyProject
  XnatConvention: KCNI
  XnatCredentials: xnatlogin.txt   # Should exist in the study metadata folder

  # The below is only used because an XNAT server is being used as a data source
  XnatSource: otherxnat.ca
  XnatSourceArchive: RemoteProjectID
  XnatSourceCredentials: remotelogin.txt  # Should exist in the study metadata folder






## Sites Block
Each scan site for a study needs its own 'site block' of configuration. This section takes the form
```
Sites:
   SITE1:
        <site1 config>
   SITE2:
        <site2 config here>
   ...
   SITEN:
        <siteN config here>
```
where SITEX should match the 'site' tag from the [Datman style ID](https://github.com/TIGRLab/documentation/wiki/Data-Naming).

### Expected Settings
These settings should be defined for each defined site.

* **XNAT_Archive**: This should contain the name of the archive on XNAT where this scan site's data will be stored. That is, it should match XNAT's 'Project ID' field for the project this site will upload to / download from.
* **ExportInfo**: This should hold one entry for each tag this site will use. Entries take the form `TAG: {setting1: X, setting2: X, ... settingN: X}`. The tag from the [Datman style file name](https://github.com/TIGRLab/documentation/wiki/Data-Naming#naming-scans-within-exams) acts as the 'TAG' field and at least the settings below must be defined for each entry. In addition, [defaults from the ExportSettings](https://github.com/TIGRLab/datman/wiki/Site-Config#exportsettings-block) for that tag can be overridden here by being included in the tag's settings.
  * Pattern: A string or [a python style regex](https://docs.python.org/2/library/re.html#regular-expression-syntax) that will match the series description field in the DICOM headers for all scans intended to receive this tag. For example, a 'DTI60-1000' tag meant to be assigned to scans with a series description of 'somethingDTI-60something' might have a pattern set to 'DTI.60' or even just 'DTI' if that is unique enough not to match other series descriptions. If there are multiple different values the series descriptions might take for a single tag a list of strings / regexes can be used in place of a single one.
  * Count: The number of matching series expected for each session at this site. e.g. if a session is expected to collect one T1 for set `Count: 1` for the T1 tag, if three DTI60-1000s are taken set `Count: 3` for that tag, etc.

### Optional Site Settings
#### Unique Site SFTP Server
Including these tags in a site block will let you configure a different sftp server just for a site:
 * **FTPSERVER**: This overrides the default server that is usually set in the [site wide config](https://github.com/TIGRLab/datman/wiki/Site-Config#misc-settings).
 * **FTPPORT**: An optional setting that allows a site to use a a non-standard port for the sftp server
 * **MRFTPPASS**: This should be set to the name of the file in the metadata folder that will hold this site's sftp account password. A full path can be provided if the file is stored outside of the metadata folder.
 * **MRUSER**: Overrides the default MRUSER for the study. See [the section on study metadata for more](#study-metadata-block)
 * **MRFOLDER**: Overrides the default MRFOLDER for the study. See [the section on study metadata for more](#study-metadata-block)

#### Fetching Site Data from an External XNAT Server
Including these tags will allow you to use xnat_fetch_remote.py to pull in data from an external XNAT server for a site:
 * **XNAT_source**: The URL for the remote XNAT server to pull from
 * **XNAT_source_archive**: The Project ID on the XNAT server that holds this site's data
 * **XNAT_source_credentials**: The name of the text file in the metadata folder that will hold the username and password on separate lines (in that order).

#### Overriding the Study Tag
Due to historical reasons, to override the study tag for a site you have to use a unique tag instead of just re-declaring the same key with a different value. This can be done by including the `SITE_TAGS` setting in a site block and must be set to a list even if there is only one alternate tag that a site uses (again because of ancient design decisions, sorry). Note that this doesn't completely override the study tag. Data from a site that defines `SITE_TAGS` may have study tags matching those tags OR the study's tag defined in `STUDY_TAG`.

#### Configuring Additional Redcap Servers
If a site uses a different redcap server to host its 'Scan Completed' surveys (or any other surveys that you may need to pull in) you can add the ['REDCAPAPI' setting](https://github.com/TIGRLab/datman/wiki/Site-Config#misc-settings) to a site block to declare a new server just for that site.

### Example Sites Block
Below is an example of two scan sites named 'CMH' and 'UT1'. Specific things to notice in this example:
  * CMH is overriding the study tag and indicating data from this site may have a study tag of 'STUDY02' instead
  * CMH has an example of a list of regexes for its PDT2 and is overriding `qc_type` from [ExportSettings](https://github.com/TIGRLab/datman/wiki/Site-Config#exportsettings-block) to ignore this series for QC purposes.
  * CMH has enclosed its RST pattern in a list. In this instance a list isn't needed, but doing so is OK even for a single pattern.
  * CMH is configuring an external XNAT server to pull data from
  * UT1 has configured a [non-default sftp server](#unique-site-sftp-server)
  * UT1 is overriding the default formats from [ExportSettings](https://github.com/TIGRLab/datman/wiki/Site-Config#exportsettings-block) for its 'OBS' series
  * UT1 is setting its own redcap server

```
Sites:
  CMH:
    SITE_TAGS: ['STUDY02']
    XNAT_Archive: STUDY1_CMH
    XNAT_source: https://xnat.remoteserver.ca
    XNAT_source_archive: camh_scans
    XNAT_source_credentials: camh_login_creds.txt
    ExportInfo:
      T1:         { Pattern: 'T1w_MPR_vNav$',         Count: 2}
      RST:        { Pattern: ['(?i)Rest'],            Count: 1}
      PDT2:       { Pattern: ['T2.DE','T2DE'],        Count: 1,      qc_type: ignore}
  UT1:
     XNAT_Archive: STUDY1_UT1
     REDCAPAPI: https://ut1redcapserver.ca/redcap/api/
     MRUSER: exampleuser
     MRFOLDER: 'DICOMS/STUDY1'
     FTPSERVER: exampleserver.ca
     FTPPORT: 18777
     MRFTPPASS: my_passfile_name.txt
     ExportInfo:
       T1:         { Pattern: 'T1w_MPR_vNav$',         Count: 1}
       OBS:        { Pattern: 'Observ',                Count: 3,     formats: ['nii']}
```

## Pipeline Config
This section documents any configuration that must be set in the study config for various nightly pipelines to run.

### FreeSurfer
Settings for freesurfer must be inside a block that starts with 'freesurfer:'.

#### Required settings:
  * **tags**: This should be the tag name assigned to T1 scans, or a list of the tag names if there is more than one type of T1 tag used in this study. This setting is used to locate anatomical scans to be fed into recon-all with the '-i' argument.
    * Example: `tags: 'MYT1TAG'` or `tags: ['MYT1TAG1', 'MYT1TAG2', ..., 'MYT1TAGN']`

#### Optional settings:
  * **T2**: This provides the tag (or tags) assigned to T2 scans for this study. If this option is set recon-all will use any T2 anatomical scans it finds for a subject in addition to the T1s.
    * Example: `T2: 'MYT2TAG'` or `T2: ['MYT2TAG1', 'MYT2TAG2', ..., 'MYT2TAGN']`
  * **FLAIR**: This provides the tag (or tags) assigned to FLAIR scans for this study. If this option is set recon-all will use any FLAIR scans it finds for a subject in addition to the T1s.
    * Example: `FLAIR: 'MYFLAIRTAG'` or `FLAIR: ['MYFLAIRTAG1', 'MYFLAIRTAG2', ..., 'MYFLAIRTAGN']`
  * **nu_iter**: This should be a dictionary that contains the value to set FreeSurfer's 'nu_iter' to for each site.
     * Example: Assuming sites 'CMH' and 'MRP' are defined `nu_iter: {CMH: 4, MRP: 8}`

#### Example
Assuming a study where T1 scans are tagged with `T1-Bravo', T2 scans tagged with `T2-TSE` and FLAIR scans just tagged `FLAIR`, and assuming a single site named 'CMH' that wants nu_iter set to 6 the following freesurfer configuration could be used.
```
freesurfer:
    tags: 'T1-Bravo'
    FLAIR: 'FLAIR'
    T2: 'T2-TSE'
    nu_iter: {CMH: 6}
```

### fMRI pipeline
These settings are used for the [epitome / script-it](https://github.com/TIGRLab/epitome) fMRI pipeline. All settings should be inside of a block named 'fmri:' and within this block specific fMRI 'experiment' pipelines are configured. For example, if a study had imitate observe task data and resting state data that study might use something like:
```
fmri:
    imob:
        <imitate and observe settings here>
    rest:
        <resting state settings here>
```
The name of each block inside 'fmri:' will then become the name of an output folder nested within the destination path set for 'fmri'.

#### Required Settings
* **export**: This should be set to a list of strings to look for in output file names to verify that the pipeline has run correctly.
  * Example: If the Datman assets script task.sh is run this might be set to ```['filtered', 'scaled', 'T1', 'MNI-nonlin', 'volsmooth']```, in which case dm_proc_fmri.py will look for files in the output directory containing each of these strings and consider outputs incomplete if it does not find a match for all items in the list.
* **pipeline**: This specifies one of the script-it scripts stored in Datman's assets folder to run. Currently accepted options are: 'task.sh', 'rest.sh', 'rest-sprl.sh'
  * Example: If task data (e.g. imitate observe) is being configured `pipeline: 'task.sh'`
* **tags**: This should contain the tag (or a list of tags) to search for when locating input files.
  * Example: If configuring an imitate-observe pipeline with scans tagged 'IMI' and 'OBS' respectively, settings would be `tags: ['IMI', 'OBS']`. Or for a resting state pipeline with only the 'RST' tag, `tags: 'RST'`
* **del**: Sets the number of TRs to remove from the beginning of each run.
  * Example: `del: 4` will delete the first 4 TRs
* **tr**: Length of the TRs in seconds (Decimals allowed)
  * Example: `tr: 2`
* **dims**: Isotropic voxel dimensions of MNI space data
  * Example: `dims: 3`
* **conn**: This specifies a list of tags used to identify connectivity files. This setting is read by `dm_proc_rest.py`. Usually just set it to `MNI-nonlin`.
  * Example: `conn: ['MNI-nonlin']`
* **glm**: This specifies a list of tags used to identify input files for `dm_proc_ea.py` and `dm_proc_imob.py`. Usually just set it to `volsmooth`
  * Example: `glm: ['volsmooth']`

#### Example
Assuming that the task pipeline needed to be configured for empathic accuracy files with a tag of 'EMP' and the rest pipeline for resting state data with a tag of 'RST' the following settings might be used:
```
fmri:
    ea:
        export: ['filtered', 'scaled', 'T1', 'MNI-nonlin', 'volsmooth']
        pipeline: 'task.sh'
        tags: 'EMP'
        del: 4
        tr: 2
        dims: 3
        conn: ['MNI-nonlin']
        glm: ['volsmooth']
    rest:
        export: ['lowpass', 'T1', 'MNI-nonlin', 'volsmooth']
        pipeline: 'rest.sh'
        tags: 'RST'
        del: 4
        tr: 2
        dims: 3
        conn: ['MNI-nonlin']
```
### Unring
Settings for the Unring pipeline must be inside a block that starts with `unring:`

#### Required Settings
* **tags**: This should contain a list of scan tags to search for in the nrrd folder. Any scan that matches one of these tags will be run through Unring.

#### Example
Assuming only scans tagged 'DTI60-1000' needed to run through the pipeline, the following could be used:
```
unring:
    tags: ['DTI60-1000']
```
### Overriding Paths for a Study
If a ['Paths' block](https://github.com/TIGRLab/datman/wiki/Site-Config#paths-block) is declared inside a study config file it will completely replace the site wide defaults, allowing you to restructure individual studies. Unfortunately, even if only one or two paths need to be changed the other paths will still need to be declared here too since the 'Paths' set here will completely hide the 'Paths' for the site wide config.

For example, if you only wanted to change the location of the nifti folder for a study adding this to your study config does not work:
```
Paths:
  nii: some/other/place
```
Because Datman will no longer be able to see the settings for the other expected paths. To fix this, just copy the other path settings into the study's 'Path' block so it can find them again.
