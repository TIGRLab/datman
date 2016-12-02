#!/usr/bin/env python
"""Share (link) scans across projects.

Creates soft links for scans from a subject in one project to a subject
in another project. Writes details of the link to a .csv file.

If a specific source and target session are given, a record of the link
created will be appended to the external-links.csv file in each project's
metadata.

Usage:
    dm-link-project-scans.py [options] <link_file>
    dm-link-project-scans.py [options] <src_session> <trg_session> [<tags>]

Arguments:
    <link_file>         Path to the external-links.csv file.
    <src_session>       Name of the source session in standard format.
    <trg_session>       Name of the target session in standard format.
    <tags>              Comma seperated list of scan tags to link.

Options:
    -h --help                   Show this screen.
    -q --quiet                  Suppress output.
    -v --verbose                Show more output.
    -d --debug                  Show lots of output.
    -o                          Path to the output file.
    --dry-run                   Perform a dry run.

Details:
    Parses all nii files in the src_session, if a files tags match <tags>
    a softlink is created in trg_session. If <tags> are not provided files
    matching tags defined in config-yaml are linked.
    A config file (default tigrlab_config.yaml) is read to determine the
    project folders. If the tag is defined in this file the ExportSettings
    node is used to determine which file types to link.
"""
import os
import sys
import logging
import yaml
import csv
import re
import datman as dm
import datman.scanid, datman.utils
from docopt import docopt

DRYRUN = False
LINK_FILE_HEADERS = ['subject', 'target_subject', 'tags']

logging.basicConfig(level=logging.WARN,
        format='[%(name)s] %(levelname)s - %(message)s',
        disable_existing_loggers=False)
logger = logging.getLogger(os.path.basename(__file__))


def read_link_file(link_file):
    """Reads a link_file returns each line"""
    logger.info('Reading link file {}'.format(link_file))
    with open(link_file, 'r') as f:
        for line in f:
            # Doing it this way so the file can be human readable
            line = re.split('\\s*', line)
            line = line[0:3]
            if not line == LINK_FILE_HEADERS:
                yield(line)

def write_link_file(link_file, src_session, trg_session, tags):
    """If the link file doesnt exist, create it, if it exists and the entry is
    not present append, otherwise do nothing"""
    if DRYRUN:
        return

    write_headers = not os.path.isfile(link_file)

    with open(link_file, 'a+') as linkfile:
        spamwriter = csv.writer(linkfile, delimiter='\t')
        if write_headers:
            logger.info('Creating link file: {}'.format(link_file))
            spamwriter.writerow(LINK_FILE_HEADERS)
        # Check if entry already exists in link file
        entry = [src_session, trg_session, ','.join(tags)]
        entry_found = False
        for line in read_link_file(link_file):
            if line == entry:
                logger.debug('Found link entry: {}'.format(entry))
                entry_found = True
        if not entry_found:
            logger.debug('Writing to link file entry: {}'.format(entry))
            spamwriter.writerow(entry)

def get_external_links_csv(session_name):
    session = get_datman_scanid(session_name)
    metadata_path = datman.config.config().get_path('meta',
            study=session.study)
    csv_path = os.path.join(metadata_path, 'external-links.csv')
    return csv_path

def make_link(source, target):
    logger.debug('Linking {} to {}'.format(source, target))

    if DRYRUN:
        return

    parent_folder = os.path.dirname(target)
    if not os.path.isdir(parent_folder):
        logger.debug('Creating target dir: {}'.format(parent_folder))
        os.makedirs(parent_folder)

    try:
        os.symlink(source, target)
    except OSError as e:
        logger.debug('Failed to create symlink: {}'.format(e.strerror))

def link_files(tags, src_session, trg_session, src_data_dir, trg_data_dir):
    """Check the tags list to see if a file should be linked,
        if true link the file
        x_data_dir should be the path to the folder containing all subject data
        """

    src_dir = os.path.join(src_data_dir,
                           src_session.get_full_subjectid_with_timepoint())

    trg_dir = os.path.join(trg_data_dir,
                           trg_session.get_full_subjectid_with_timepoint())

    logger.info("Making links in {} for tagged files in {}".format(trg_dir,
            src_dir))

    for root, dirs, files in os.walk(src_dir):
        for filename in files:
            try:
                ident, file_tag, series, description = \
                    dm.scanid.parse_filename(filename)
            except dm.scanid.ParseException:
                continue
            if file_tag in tags:
                # need to create the link
                ## first need to capture the file extension
                ext = dm.utils.get_extension(filename)

                trg_name = dm.scanid.make_filename(trg_session, file_tag,
                                                   series, description)
                src_file = os.path.join(root, filename)
                trg_file = os.path.join(trg_dir, trg_name) + ext

                make_link(src_file, trg_file)


def get_file_types_for_tag(export_settings, tag):
    """Check which file types should be processed for each tag"""
    try:
        return export_settings[tag].keys()
    except KeyError:
        return []

def get_dirs_to_search(source_config, tag_list):
    dirs_to_search = []
    for tag in tag_list:
        filetypes = get_file_types_for_tag(source_config.get_key('ExportSettings'),
                tag)
        if filetypes:
            dirs_to_search.extend(filetypes)
        else:
            logger.error("Tag {} has no file types defined in ExportSettings." \
                    "Searching all paths for matching data.".format(tag))
            dirs_to_search = source_config.get_key('paths').keys()
            break
    dirs_to_search = set(dirs_to_search)
    return dirs_to_search

def get_datman_scanid(session_id):
    try:
        session = dm.scanid.parse(session_id)
    except dm.scanid.ParseException:
        logger.error("Invalid session ID given: {}. Exiting".format(session_id))
        sys.exit(1)
    return session

def link_session_data(source, target, given_tags):
    source_id = get_datman_scanid(source)
    target_id = get_datman_scanid(target)

    config = datman.config.config(study=source_id.study)

    if given_tags:
        # Use the supplied list of tags to link
         tags = [tag.upper() for tag in given_tags.split(',')]
    else:
        # Use the list of tags from the source site's export info
        source_export_info = config.get_export_info_object(source_id.site)
        tags = source_export_info.tags

    logger.debug("Tags set to {}".format(tags))

    dirs = get_dirs_to_search(config, tags)
    for path_key in dirs:
        link_files(tags, source_id, target_id,
                config.get_path(path_key, study=source_id.study),
                config.get_path(path_key, study=target_id.study))

    # Return tags used for linking, in case links file needs to be updated
    return tags

def main():
    global DRYRUN, CONFIG
    arguments    = docopt(__doc__)
    link_file    = arguments['<link_file>']
    src_session  = arguments['<src_session>']
    trg_session  = arguments['<trg_session>']
    tags         = arguments['<tags>']
    verbose      = arguments['--verbose']
    debug        = arguments['--debug']
    DRYRUN       = arguments['--dry-run']
    quiet        = arguments['--quiet']

    logger.setLevel(logging.WARN)

    if quiet:
        logger.setLevel(logging.ERROR)

    if verbose:
        logger.setLevel(logging.INFO)

    if debug:
        logger.setLevel(logging.DEBUG)

    if link_file is not None:
        logger.info("Using link file {} to make links".format(link_file))
        for line in read_link_file(link_file):
            link_session_data(line[0], line[1], line[2])
        return

    logger.info("Linking the provided source {} and target " \
            "{}".format(src_session, trg_session))
    tags = link_session_data(src_session, trg_session, tags)

    src_link_file = get_external_links_csv(src_session)
    trg_link_file = get_external_links_csv(trg_session)

    for link_file in [src_link_file, trg_link_file]:
        write_link_file(link_file, src_session, trg_session, tags)

if __name__ == '__main__':
    main()
