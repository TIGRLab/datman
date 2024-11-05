.. include:: links.rst
.. _datman-conf:

-------------------
Configuration Files
-------------------

Datman requires a main configuration file to run. This can be constructed from
the template file ``main_config.yml`` found in Datman's
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

From **most** specific definition to **least** it goes:

1. Defining a setting within a 'Sites' block in a study config file (site level)
2. Defining a setting inside a study config file but outside of all 'Sites'
   blocks (study level).
3. Defining a setting within the main config file (global)

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
(instead of 'MyProject' from the main config file).

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

Blacklist
*********
These settings are used by ``dm_blacklist_rm`` and any other scripts that
read from / remove blacklisted data.

Optional
^^^^^^^^

.. _config BlacklistDel:

* **BlacklistDel**

  * Description: Defines which directories to delete blacklisted data from.
    This value is read by ``dm_blacklist_rm``.
  * Accepted values: A list of path names, where each path name has already
    been defined in `Paths`_.
  * Default value: If omitted ``dm_blacklist_rm`` will delete blacklisted
    scans from ``nii``, ``mnc``, ``nrrd``, and ``resources``, if these
    directories exist.

Example
^^^^^^^
.. code-block:: yaml

   # To delete from the nifti, resources, and task data folders:
   BlacklistDel: [nii, resources, task]

   # Or limit deletion to the nifti folder:
   BlacklistDel: [nii]

.. _config Export:

ExportInfo
**********
This setting belongs in the site settings within a study config file. It
describes which data to export from XNAT and what tags to assign the exported
series. Note that each tag defined here must also exist within ExportSettings
in the main configuration file.

Required
^^^^^^^^
These settings must exist for each tag that is defined.

* **Pattern**: Describes fields from the dicom headers that must be matched for
  the current tag to be assigned. See the `Pattern`_ section for more info.

* **Count**: Indicates the number of series that should match this tag for
  each session. Note that if more series are found than expected they will
  still be tagged and downloaded correctly, this number is just used to
  report that more were found than expected (or fewer) during QC.

Example
^^^^^^^
.. code-block:: yaml

  ExportInfo:
    # Example tags. These can be named anything, but should be defined in
    # ExportSettings in the main config file first.
    T1:
      Pattern:
        ...
      Count: 1
    T2:
      Pattern:
        ...
      Count: 1
    RST:
      Pattern:
        ...
      Count: 3

ExportSettings
**************
This block defines the expected scan tags. Each tag has its own dictionary of
config values that defines which formats to convert to, which QC function to
use for human data, which QC function to use for phantoms, and
any bids export settings (if converting to bids format).

**NOTE:** Any settings from this block can be overridden by the `ExportInfo`_
block in a study config file.

Required
^^^^^^^^
The following settings should be defined in the main configuration file and act
as defaults for each tag that studies will use. The benefit of pre-defining tags
this way is that it helps detect typos in a study config file, and helps prevent
different studies from tagging the same type of acquisition in different ways.

* **Formats**

  * Description: This should be a list of formats that any series
    matching the tag should be exported to.
  * Accepted values: a list which may contain any of these data formats 'nii',
    'dcm', 'mnc', 'nrrd'
* **QcType**

  * Description: This defines what type of QC metrics dm_qc_report.py should
    try to generate for human data that matches the tag.
  * Accepted values: 'anat', 'fmri', 'dti', 'ignore'

Optional
^^^^^^^^
* **QcPha**

  * Description: This defines what type of QC metrics dm_qc_report.py should
    try to generate for phantom data that matches the tag.
  * Accepted values: 'qa_dti', 'abcd_fmri', or 'default'.
  * Default value: If omitted, it will be treated as being set to 'default'
* Any settings usually provided in `ExportInfo`_ can also be set here to
  provide a global default for a tag.

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

.. _config FTP:

FTP
***
These settings manage SFTP access and are needed by scripts, like dm_sftp.py,
that interact with sftp servers.

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

  * Description: The name of the file in the study metadata folder to
    get the SFTP password from. If omitted, a file named 'mrftppass.txt' is
    searched for.
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

.. _config Standards:

Gold Standards
**************
These settings tune the sensitive of gold standard comparisons by QC tools.
The gold standard files are json side car files that have been stored in the
study's ``std`` directory (by default this is ``${STUDY}/metadata/standards``).

Optional
^^^^^^^^
* **IgnoreHeaderFields**:

  * Description: A list of dicom header field names to ignore during
    comparisons. These are Case-Sensitive.
* **HeaderFieldTolerance**:

  * Description: A list of ``HeaderField: Tolerance`` pairs to determine when
    numeric differences should be ignored. The header field names are
    Case-Sensitive.

Example
^^^^^^^

.. code-block:: yaml

  IgnoreHeaderFields:
    # Note that these are case-sensitive!
    - AcquisitionTime
    - ManufacturersModelName

  HeaderFieldTolerance:
    # Note that these are case-sensitive!
    EchoTime: 0.005
    RepetitionTime: 1

.. _config Idmap:

IdMap
*****
Provides a method of translating between ID schemes (Datman to KCNI or vice
versa).

Optional
^^^^^^^^
* **Study**:

  * Description: Maps the expected value for the KCNI study ID field to the
    expected value for the Datman study ID field.
* **Site**:

  * Description: Maps the expected value for the KCNI site ID field to the
    expected value for the Datman site ID field.
* **Subject**:

  * Description: Describes how to convert the subject ID field from KCNI
    convention to Datman convention and back again. This is more complicated.
    It requires two pairs of
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
    # Any of the below sections can be omitted if the field doesn't change
    # between naming conventions.
    # Left side (keys) are KCNI convention, right side (values) are Datman convention.
    #
    # KCNI ID                               Datman ID
    # STU01_UTO_10001_01_SE01_MR  becomes   STUDY1_UT2_ABC0001_01_01
    Study:
      STU01: STUDY1
    Site:
      UTO: UT2
    Subject:
      '1(P?[0-9]+)->ABC\1': 'ABC(P?[0-9]+)->1\1'

.. _config Logs:

Logs
****
These settings manage log configuration for datman's log server
(dm_log_server.py) and for scripts that are able to log to it.

Required
^^^^^^^^
* **LogServer**

  * Description: The domain name or IP address of the machine that the log
    server (dm_log_server.py) will be listening on. This is also read by scripts
    that output log messages to find the log server.
* **ServerLogDir**

  * Description: The full path to the directory where dm_log_server.py should
    store all logs. This directory should be accessible to the machine running
    the log server (i.e. a path local to that machine or an NFS directory
    mounted to it). Only needed if LogServer is set.

Example
^^^^^^^
.. code-block:: yaml

  LogServer: 111.222.333.444
  LogServerDir: /var/logs/datman_logs

.. _config Paths:

Paths
*****
This block determines the structure for the contents of each Datman managed
study folder. The keys are a short descriptive name for the
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
* **zips**: The folder that holds the name-corrected links that point to the raw
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
    stored as json files containing the expected values for important DICOM
    header fields.
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

    * dm_xnat_extract.py - Writes to this folder when the ``--use-dcm2bids``
      option is used.
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

Assuming a configuration where the ``DatmanProjectsDir`` is set to
``/archive/data`` (as it is in ours) and a ``ProjectDir`` of ``SPINS`` the above
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

Pattern
*******
This setting should be defined for each tag inside `ExportInfo`_. It describes
how to assign a tag to each series based on the dicom header fields.

Required
^^^^^^^^
* **SeriesDescription**:

  * Description: A python regex that will match the series description field
    in the dicom headers for any series that should receive the current tag.
  * Accepted values: `A python regex <https://docs.python.org/3/howto/regex.html>`_
    or list of regexes.

Optional
^^^^^^^^
* **ImageType**:

  * Description: A python regex to match the image type of the dicom header.
    Used to distinguish between different image types when the series
    description is identical.
  * Accepted values: `A python regex. <https://docs.python.org/3/howto/regex.html>`_
* **EchoNumber**:

  * Description: The echo number to apply the tag to when multiple exist within
    a single acquisition.
  * Accepted values: an integer.

Example
^^^^^^^
.. code-block:: yaml

  ExportInfo:
    T1:
      Pattern:
        SeriesDescription: 'Sag.?T1.BRAVO'
      Count: 1
    DTI60-1000:
      Pattern:
        # A list of regexes is also allowed
        SeriesDescription: ['ep2d','DTI.60Dir*GRAPPA$']
      Count: 2
    # These two entries give an example of using echo number to split multiple
    # echoes out of an acquisition.
    MAG1:
      Pattern:
        SeriesDescription: 'field'
        EchoNumber: 1
      Count: 1
    MAG2:
      Pattern:
        SeriesDescription: 'field'
        EchoNumber: 2
      Count: 1
    # These two entries give an example of using ImageType to apply different
    # tags to series with the same SeriesDescription
    T2:
      Pattern:
        SeriesDescription: 'T2w_SPC_vNav$'
        ImageType: 'ORIGINAL.*ND$'
      Count: 1
    T2-NORM:
      Pattern:
        SeriesDescription: 'T2w_SPC_vNav$'
        ImageType: 'ORIGINAL.*ND.*NORM$'
      Count: 1

Projects
********
The projects block contains a list of short-hand codes for each study that
Datman is expected to manage. Each code **must** be unique and is
case-sensitive. Each defined project should map to the name of that study's
config file. These files will be searched for in the ConfigDir (from the
`SystemSettings`_) for the current system.

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

.. _config Redcap:

REDCap
******
Any settings needed to use REDCap integrations are described below. These
settings are used by scripts like ``dm_redcap_scan_complete.py``, and
``dm_link_shared_ids.py``.

Required
^^^^^^^^

* **RedcapUrl**:

  * Description: The URL of the REDCap server to query for surveys. If the
    'Data Entry Trigger' feature is being used, this must match the URL
    contained in the requests that will be sent (this should just be the
    plain old home page URL).
  * Used by: dm_redcap_scan_complete.py and the QC dashboard if it's installed.
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
* **RedcapApiUrl**:

  * Description: The URL for the REDCap API. Only needed if this URL differs
    from RedcapUrl.
  * Default: 'RedcapUrl'
  * Used by: dm_link_shared_ids.py
* **RedcapComments**:

  * Description: The name of the survey field that holds comments from the
    RA who attended the scan.
  * Default: 'cmts'
* **RedcapDate**:

  * Description: The name of the survey field that holds the date the survey
    was completed.
  * Default: 'date'
* **RedcapSharedIdPrefix**:

  * Description: The string identifier that will prefix every REDCap survey
    field that holds an alternate ID/shared ID for the session. Used to
    share data between studies. If only one shared ID is expected, the REDCap
    survey field may be identical to the prefix (e.g. prefix is 'shared_id' and
    the survey field is also just 'shared_id').
  * Default: 'shared_parid'
  * Used by: dm_link_shared_ids.py
* **RedcapStatus**:

  * Description: The name of the survey field that will indicate whether the
    form is complete.
  * Default: 'tigrlab_scan_completed_complete'
* **RedcapStatusValue**:

  * Description: A value or list of values that RedcapStatus may take to
    indicate that the form is complete.
  * Accepted values: a list of strings or a string.
  * Default: '2'
* **RedcapSubj**:

  * Description: The name of the survey field that holds the correctly
    formatted session ID.
  * Default: 'par_id'
* **RedcapToken**:

  * Description: The name of the file that will hold the token to access
    REDCap's API. The file should be stored in the study metadata folder and
    be readable to the user(s) who will run any of datman's redcap scripts.
    If undefined, the environment variable REDCAP_TOKEN will be used instead.
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
  RedcapUrl: myredcapserver.com
  RedcapApiUrl: myredcapserver.com/api # These URLs can refer to different servers
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

  # Use if sharing scans between studies. Should hold the prefix of the
  # survey field name used for each alternate ID (one ID per field, e.g.
  # 'shared_id1', 'shared_id2')
  RedcapSharedIdPrefix: 'shared_id'


Sites
*****
Each scan site collecting data for a study needs its own configuration
block in the study config file. Any site-specific configuration should
be placed in this block to override study or global defaults.

Required
^^^^^^^^
* **ExportInfo**:

  * Description: A block of configuration describing which scans to download
    and how to apply scan tags to them. See `ExportInfo`_ for more info.
* **Site codes**:

  * Description: One unique code per scan site that will collect scans for the
    study. Each site code will be matched to the site tag portion of a
    `Datman style ID. <https://github.com/TIGRLab/documentation/wiki/Data-Naming>`_

Example
^^^^^^^
.. code-block:: yaml

  Sites:
      # Your site codes may be whatever you like, but they should fit
      # Datman's convention of being no more than three characters and
      # only containing letters and numbers.
      CMH:
        # Site specific settings can go here
        ExportInfo:
          ...
      UT1:
        # As an example, a site can upload to a different XNAT project
        # by redefining XnatArchive here
        XnatArchive: MYSTUDY_UT1
        ExportInfo:
          ...
      ...
      XXX:
        ExportInfo:
          ...

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
* **Description**:

  * Description: A freeform description of the study and the data it contains.
* **FullName**:

  * Description: The full name of the study.
* **IsOpen**:

  * Description: Whether the study is still collecting data.
  * Default: True
  * Accepted values: A python boolean.
* **PrimaryContact**:

  * Description: The name of the contact for the study.

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
* **ConfigDir**: The full path to the folder where all configuration files are
  stored. For example, on our system this is `/archive/code/config/`
* **DatmanAssetsDir**: The full path to datman's assets folder. For example, on our
  local system this is `/archive/code/datman/assets/`
* **DatmanProjectsDir**: Must be the full path to the folder where a set of datman
  managed projects will be kept. For example, on our local system this is
  `/archive/data/`

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

.. _config Tasks:

Task Files
**********
These settings are used by scripts that work with fMRI task files (e.g.
dm_task_files).

Optional
^^^^^^^^
* **TaskRegex**

  * Description: `A regular expression <https://docs.python.org/3/library/re.html>`_
    used to identify task files. This is needed because task files are often
    named less consistently than scan data and are often (at least initially)
    in a resources folder filled with many other non-task files.

Example
^^^^^^^
.. code-block:: yaml

  # This will identify any file with 'behav' or the 'edat2' extension as
  # task data.
  TaskRegex: 'behav|\.edat2'

  # This will identify any file with the .log extension as task data
  TaskRegex: '\.log'

.. _config XNAT:

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

* **XnatDataSharing**

  * Description: Indicates whether sessions from this study should be shared
    under other IDs in other XNAT projects. The alternate IDs to use are
    obtained from REDCap (``RedcapSharedIdPrefix`` must be set in addition to
    the normal REDCap configuration, see `Redcap`_ section for more info).
  * Accepted values: Any value is regarded as true. If absent, is False.
  * Used by: dm_link_shared_ids.py


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

  # This is used if sessions should be shared into other xnat projects
  XnatDataSharing: True
