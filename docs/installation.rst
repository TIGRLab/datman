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
