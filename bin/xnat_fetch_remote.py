#!/usr/bin/env python
"""
This script fetches all data from an xnat server and stores each found session
as a zip file. It was originally created to grab data from OPT CU's xnat server
and store it in the data/zips folder for later upload to our own server.

There are two ways to use this script:

    1. Specify all the needed details at the command line: XNAT project name,
       server URL, login credentials and an output path
    2. Specify a datman study. The configuration files will then be searched for
       an 'XNAT_source_archive' (gives XNAT project name), 'XNAT_source' (server
       URL), and 'XNAT_source_credentials' (gives name of a credentials file
       stored in metadata or the full path to a file elsewhere). These can be
       added to the study configuration at either the site or study level. The
       output location will be set to the study's 'zips' folder.

Whether the credentials file is found from the command line or the configuration
file the format is expected to be username then password each separated by a newline.

Usage:
    xnat_fetch_remote.py [options] <project> <server> <credentials> <destination>
    xnat_fetch_remote.py [options] <study>


Arguments:
    <study>                 Name of the datman study to process.
    <project>               The XNAT project to pull from.
    <server>                Full URL to the remote XNAT server to pull from.
    <credentials>           The full path to a file containing the xnat username
                            a newline, and then the xnat password.
    <destination>           The full path to the intended destination for all
                            downloaded data. The script will attempt to avoid
                            redownloading data if data already exists at
                            this location.

Options:
    -l, --log-to-server     Set whether to log to the logging server.
    -n, --dry-run           Do nothing
    -v, --verbose
    -d, --debug

"""

from docopt import docopt

def main():
    arguments = docopt(__doc__)


if __name__ == "__main__":
    main()
