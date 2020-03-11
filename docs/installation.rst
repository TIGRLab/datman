.. include:: links.rst

------------
Installation
------------

Some environment variables need to be added to your shell to run certain datman scripts. You can add these to your shell with ``export VARNAME=VARVALUE`` for each one. For convenience you could also define a bash script full of these export commands and source the script instead or set up an environment module.

Required Variables
~~~~~~~~~~~~~~~~~~

``DM_CONFIG``: Should be the full path to the site-wide datman config file.
``DM_SYSTEM``: Should be set to a system name from the SystemSettings in the datman site config file

Optional Variables
~~~~~~~~~~~~~~~~~~

If you're running any script that interacts with XNAT you must set:

``XNAT_USER``: The user name to log in with
``XNAT_PASS``: The password to use

If you're interacting with a redcap server you should set ``REDCAP_TOKEN`` to your token.