#!/usr/bin/env python
"""Share (link) scans across projects.

Creates softlinks for scans from a subject in one project to a subject
in another project. Writes details of the link to a .csv file.

Usage:
    link-project-scans.py [options] <link_file>
    link-project-scans.py [options] <link_file> <src_session> <trg_session> [<tags>]

Arguments:
    <link_file>     Path to the external-links.csv file.
    <src_session>   Name of the source session in standard format.
    <trg_session>   Name of the target session in standard format.
    <tags>          Comma seperated list of scan tags to link.

Options:
    -h --help                   Show this screen.
    -q --quiet                  Suppress output.
    -v --verbose                Show more output.
    -d --debug                  Show lots of output.
    -o                          Path to the output file.
    --dry-run                   Perform a dry run.
    --config-yaml=<yamlfile>    Path to site specific yaml file
                                    [default: /archive/data/code/datman/assets/tigrlab_config.yaml]
    --system=<system>           System name for settings [default: kimel]

Details:
    Parses all nii files in the src_session, if a files tags match <tags>
    a softlink is created in trg_session. If <tags> are not provided files
    matching tags defined in config-yaml are linked.
    A config file (default tigrlab_config.yaml) is read to determine the project
    folders. If the tag is defined in this file the ExportSettings node is used
    to determine which file types to link.
"""
import os
import logging
import yaml
import csv
import re
import datman as dm
import datman.scanid
from docopt import docopt


QUIET = False
VERBOSE = False
DEBUG = False
DRYRUN = False
PROJECTS_DIR = None
CONFIG = None
TAGS = None
LINK_FILE_HEADERS = ['subject', 'target_subject', 'tags']

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARN)

def get_file_types_for_tag(tag):
    """Check which file types should be processed for each tag"""
    try:
        return(CONFIG['ExportSettings'][tag].keys())
    except:
        return None

def find_files(directory):
    """generator function to list files in a directory"""
    for root, dirs, files in os.walk(directory):
        for filename in files:
            yield(os.path.join(root, filename))

def get_study_from_tag(tag):
    """Identify the study from the filename study tag"""
    for project_tag in CONFIG['XNATProjects'].keys():
        if tag in CONFIG['XNATProjects'][project_tag]:
            logger.debug('Mapping filename tag: {} to study: {}'.format(tag, project_tag))
            return project_tag
    logger.warning('Failed to identify filename tag:{}'.format(tag))
    return None

def set_tags(tagstring):
    global TAGS
    if tagstring:
        TAGS = [tag.upper() for tag in tagstring.split(',')]
    else:
        TAGS = CONFIG['ExportSettings'].keys()

def split_multi_ext(filename):
    """Split multiple file extensions from a filename"""
    multi_ext = []
    while True:
        name, ext = os.path.splitext(filename)
        if not ext:
            return (name, ''.join(multi_ext))
        multi_ext.append(ext)
        filename = name

def write_link_file(link_file, src_session, trg_session):
    """If the link file doesnt exist, create it, if it exists and the entry is
    not present append, otherwise do nothing"""
    global LINK_FILE_HEADERS

    write_headers = not os.path.isfile(link_file)

    if not DRYRUN:
        with open(link_file, 'a+') as linkfile:
            spamwriter = csv.writer(linkfile, delimiter='\t')
            if write_headers:
                logger.info('Creating link file:{}'.format(link_file))
                spamwriter.writerow(LINK_FILE_HEADERS)
            # Check if entry already exists in link file
            entry = [src_session, trg_session, ','.join(TAGS)]
            entry_found = False
            for line in read_link_file(link_file):
                if line == entry:
                    logger.info('Found link entry:{}'.format(entry))
                    entry_found = True
            if not entry_found:
                logger.info('Writing to link file')
                spamwriter.writerow([src_session, trg_session, ','.join(TAGS)])

def read_link_file(link_file):
    """Reads a link_file returns each line"""
    global LINK_FILE_HEADERS

    logger.info('Reading link file {}'.format(link_file))
    with open(link_file,'r') as f:
        for line in f:
            # Doing it this way so the file can be human readable
            line = re.split('\\s*', line)
            line = line[0:3]
            if not line == LINK_FILE_HEADERS:
                yield(line)

def link_session(src_session, trg_session):
    # Check the source and target sessions are in the correct format
    logger.debug('Checking for valid sessions.')
    if dm.scanid.is_scanid(src_session):
        src_session = dm.scanid.parse(src_session)
        src_study = get_study_from_tag(src_session.study)
        src_project_dir = CONFIG['Projects'][src_study]
        src_project_dir = src_project_dir.replace('<DATMAN_PROJECTSDIR>',
                                                  PROJECTS_DIR)
    else:
        raise ValueError('Invalid src_session: {}'.format(src_session))

    if dm.scanid.is_scanid(trg_session):
        trg_session = dm.scanid.parse(trg_session)
        trg_study = get_study_from_tag(trg_session.study)
        trg_project_dir = CONFIG['Projects'][trg_study]
        trg_project_dir = trg_project_dir.replace('<DATMAN_PROJECTSDIR>',
                                                  PROJECTS_DIR)
    else:
        raise ValueError('Invalid trg_session: {}'.format(trg_session))

    dirs_to_search = []
    for tag in TAGS:
        filetypes = get_file_types_for_tag(tag)
        if filetypes is None:
            # needed for unrecognised filetypes
            dirs_to_search.append('data')
        else:
            for item in [os.path.join('data',filetype) for filetype in filetypes]:
                dirs_to_search.append(item)
    dirs_to_search = set(dirs_to_search)


    # Loop through all the possible files and perform linking
    for directory in dirs_to_search:
        link_files(src_session,
                   trg_session,
                   os.path.join(src_project_dir, directory),
                   os.path.join(trg_project_dir, directory))

def link_files(src_session, trg_session, src_data_dir, trg_data_dir):
    """Check the tags list to see if a file should be linked,
        if true link the file
        x_data_dir should be the path to the folder containing all subject data"""

    src_dir = os.path.join(src_data_dir,
                           src_session.get_full_subjectid_with_timepoint())

    trg_dir = os.path.join(trg_data_dir,
                           trg_session.get_full_subjectid_with_timepoint())

    for root, dirs, files in os.walk(src_dir):
        for filename in files:
            try:
                ident, tag, series, description = \
                    dm.scanid.parse_filename(filename)
            except dm.scanid.ParseException:
                continue
            if tag in TAGS:
                # need to create the link
                ## first need to capture the file extension
                basename , ext = split_multi_ext(filename)

                trg_name = dm.scanid.make_filename(trg_session, tag, series, description)
                src_file = os.path.join(root, filename)
                trg_file = os.path.join(trg_dir, trg_name) + ext

                logger.info('Linking {} to {}'.format(src_file, trg_file))
                try:
                    if not os.path.isdir(os.path.dirname(trg_file)):
                        logger.info('Creating target dir: {}'.format(os.path.dirname(trg_file)))
                        if not DRYRUN:
                            os.makedirs(os.path.dirname(trg_file))
                    if not DRYRUN:
                        os.symlink(src_file, trg_file)
                except OSError as e:
                    logger.error('Failed to create symlink: {}'.format(e.strerror))

if __name__ == '__main__':
    arguments    = docopt(__doc__)
    link_file    = arguments['<link_file>']
    src_session  = arguments['<src_session>']
    trg_session  = arguments['<trg_session>']
    tags         = arguments['<tags>']
    config_yml   = arguments['--config-yaml']
    system_name  = arguments['--system']
    VERBOSE      = arguments['--verbose']
    DEBUG        = arguments['--debug']
    DRYRUN       = arguments['--dry-run']
    QUIET        = arguments['--quiet']

    if QUIET:
        logger.setLevel(logging.ERROR)

    if VERBOSE:
        logger.setLevel(logging.INFO)

    if DEBUG:
        logger.setLevel(logging.DEBUG)

    logging.info('Starting')

    # Check the yaml file can be read correctly
    logger.debug('Reading yaml file.')

    ## Read in the configuration yaml file
    if not os.path.isfile(config_yml):
        raise ValueError("configuration file {} not found. Try again.".format(config_yml))

    ## load the yml file
    with open(config_yml, 'r') as stream:
        CONFIG = yaml.load(stream)

    ## check that the expected keys are there
    ExpectedKeys = ['Projects', 'ExportSettings', 'SystemSettings', 'XNATProjects']
    diffs = set(ExpectedKeys) - set(CONFIG.keys())
    if len(diffs) > 0:
        raise ImportError("configuration file missing {}".format(diffs))

    # TODO: this should be more flexibly coded in the yaml file
    try:
        PROJECTS_DIR = CONFIG['SystemSettings'][system_name]['DATMAN_PROJECTSDIR']
        logger.debug('Setting project Dir to {}'.format(PROJECTS_DIR))
    except KeyError:
        logger.error('Projects dir not found in config file:{}'.format(config_yml))
        raise

    logger.debug('Processing tags: {}'.format(TAGS))

    if src_session is not None and trg_session is not None:
        # processing a single session
        set_tags(tags)
        link_session(src_session, trg_session)
        write_link_file(link_file, src_session, trg_session)
    else:
        # read the link file and process the entries
        for line in read_link_file(link_file):
            set_tags(line[2])
            link_session(line[0], line[1])
