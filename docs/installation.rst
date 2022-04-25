.. include:: links.rst

------------
Installation
------------

.. code-block:: shell

  git clone https://github.com/TIGRLab/datman.git
  cd datman
  pip install .

You'll also want to update your path to make datman's command line utilities
(the scripts in datman's bin folder) accessible without having to type out
the full path, as shown below.

.. code-block:: shell

  # $ROOTDIR should be replaced with the full path to your cloned datman copy
  export PATH=${PATH}:$ROOTDIR/datman/bin

Datman requires some configuration files to run, as described
:ref:`here. <datman-conf>` Once your configuration files have been created,
make your settings available to datman by setting the DM_CONFIG environment
variable to the full path to your main config file and setting DM_SYSTEM to
your system name.

.. code-block:: shell

  export DM_CONFIG=<full path to your main config file>
  export DM_SYSTEM=<name of a system within the config file>

**Optional Configuration**

If you plan to use the XNAT integration you'll also need to provide your
XNAT credentials

.. code-block:: shell

  export XNAT_USER=<your username>
  export XNAT_PASS=<your password>

Using the redcap integration requires providing a redcap token

.. code-block:: shell

  export REDCAP_TOKEN=<your token here>

**Software Dependencies**

Some of datman's scripts have additional software dependencies. These are
listed below.

  * `dcm2niix <https://github.com/rordenlab/dcm2niix>`_ - Needed by dm_xnat_extract.py
  * `matlab <https://www.mathworks.com>`_ - Needed by dm_qc_report.py
  * `AFNI <https://afni.nimh.nih.gov/>`_ - Needed by dm_qc_report.py
  * `FSL <https://fsl.fmrib.ox.ac.uk/fsl/fslwiki>`_ - Needed by dm_qc_report.py
  * `qcmon <https://github.com/TIGRLab/qcmon>`_ - Needed by dm_qc_report.py

----------------
Docker Container
----------------
Rather than installing Datman directly you can run it in a docker container.
Note that the docker container does not contain the dependencies
dm_qc_report.py needs to run (largely due to matlab license issues). All other
scripts will run correctly, though.

.. code-block:: shell

  # Run interactively
  docker run -it -v ${data_dir}:/data -v ${conf_dir}:/config tigrlab/datman

  # Run just a single script (e.g. dm_sftp.py)
  docker run -v ${data_dir}:/data -v ${conf_dir}:/config tigrlab/datman dm_sftp.py $STUDY_NICKNAME

``data_dir`` should be the path to the directory that will hold all managed
studies. ``conf_dir`` should be the path to the directory containing the Datman
configuration files.

You'll still need to create the Datman configuration files as described
:ref:`here. <datman-conf>` The main configuration file should be named
``main_config.yml`` for the container to detect it. You'll also need to add
this system configuration to your ``SystemSettings`` block.

.. code-block:: yaml

  docker:
    DatmanProjectsDir: '/data'
    DatmanAssetsDir: '/datman/assets'
    ConfigDir: '/config'

**Running as a specific user**

If you don't want outputs from running the container to be root owned you can
run it as a local user by including the ``--user flag``. On Linux you can
retrieve a user's ID with ``$(id -u $USER)`` or ``$(id -u)`` for the current
user.

.. code-block:: shell

  # Any datman scripts run this way will generate outputs owned by
  # the user who ran the container instead of root.
  docker run -it -v ${data_dir}:/data -v ${conf_dir}:/config --user $(id -u) tigrlab/datman

**Providing credentials for XNAT / REDCap**

If you want to run a datman script that accesses XNAT or REDCap you can provide
your credentials using docker's -e flag.

.. code-block:: shell

  # To run dm_xnat_extract.py
  docker run -v ${data_dir}:/data -v ${conf_dir}:/config -e "XNAT_USER=<user>" -e "XNAT_PASS=<password>" tigrlab/datman dm_xnat_extract.py <STUDY>

  # To run dm_redcap_scan_completed.py
  docker run -v ${data_dir}:/data -v ${conf_dir}:/config -e "REDCAP_TOKEN=<your token>" tigrlab/datman dm_redcap_scan_completed.py <STUDY>
