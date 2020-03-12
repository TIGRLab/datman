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
import csv
import re

from docopt import docopt

import datman as dm
import datman.scanid
import datman.utils
import datman.dashboard as dashboard

DRYRUN = False
LINK_FILE_HEADERS = ['subject', 'target_subject', 'tags']

logger = logging.getLogger(os.path.basename(__file__))
log_handler = logging.StreamHandler()
logger.addHandler(log_handler)
log_handler.setFormatter(logging.Formatter('[%(name)s] %(levelname)s : '
                                           '%(message)s'))


def read_link_file(link_file):
    """Reads a link_file returns each line"""
    logger.info('Reading link file {}'.format(link_file))
    with open(link_file, 'r') as f:
        f.readline()
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
    # Give whole session_name in case it's 'DTI'
    metadata_path = datman.config.config().get_path('meta',
                                                    study=session_name)
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

    # Make relative, so the link works from the SCC too
    rel_source = dm.utils.get_relative_source(source, target)

    try:
        os.symlink(rel_source, target)
    except OSError as e:
        logger.debug('Failed to create symlink: {}'.format(e.strerror))
        return None

    return target


def add_link_to_dashboard(source, target, target_path):
    if not dashboard.dash_found:
        return

    logger.debug('Creating database entry linking {} to {}.'.format(
            source, target))
    if DRYRUN:
        return

    target_record = dashboard.get_scan(target)
    if target_record:
        # Already in database, no work to do.
        return

    db_source = dashboard.get_scan(source)
    if not db_source:
        logger.error("Source scan {} not found in dashboard database. "
                     "Can't create link {}".format(source, target))
        return

    try:
        dashboard.add_scan(target, source_id=db_source.id)
    except Exception as e:
        logger.error("Failed to add link {} to dashboard database. "
                     "Reason {}. Removing link from file system to re-attempt "
                     "later.".format(target, str(e)))
        if not target_path:
            # No link was made
            return
        try:
            os.remove(target_path)
        except (OSError, IsADirectoryError):
            logger.error("Failed to clean up link {}".format(target_path))


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
            if ident.session == src_session.session and file_tag in tags:
                # If the file is from the same session we're supposed to link
                # and the tag is in the list, make a link.

                ext = dm.utils.get_extension(filename)
                trg_name = dm.scanid.make_filename(trg_session, file_tag,
                                                   series, description)
                src_file = os.path.join(root, filename)
                trg_file = os.path.join(trg_dir, trg_name) + ext

                result = make_link(src_file, trg_file)
                add_link_to_dashboard(src_file, trg_file, result)


def get_file_types_for_tag(tag_settings, tag):
    """Check which file types should be processed for each tag"""
    try:
        return tag_settings.get(tag, 'formats')
    except KeyError:
        return []


def get_dirs_to_search(source_config, tag_list):
    dirs_to_search = []
    tag_settings = source_config.get_tags()
    for tag in tag_list:
        filetypes = get_file_types_for_tag(tag_settings, tag)
        if filetypes:
            dirs_to_search.extend(filetypes)
        else:
            logger.error("Tag {} has no file types defined in ExportSettings."
                         "Searching all paths for matching data.".format(tag))
            dirs_to_search = list(source_config.get_key('Paths').keys())
            break
    dirs_to_search = set(dirs_to_search)
    return dirs_to_search


def tags_match(blacklist_entry, tags):
    """
    Returns true if the filename in <blacklist_entry> contains a tag in <tags>.
    """
    try:
        _, tag, _, _ = datman.scanid.parse_filename(blacklist_entry)
    except datman.scanid.ParseException:
        logger.error("Blacklist entry {} contains non-datman filename. "
                     "Entry will not be copied to target blacklist."
                     "".format(blacklist_entry))
        return False

    if tag not in tags:
        return False

    return True


def copy_blacklist_data(source, source_blacklist, target, target_blacklist,
                        tags):
    """
    Adds entries from <source_blacklist> to <target_blacklist> if they contain
    one of the given tags and have not already been added.
    """
    source_entries = datman.utils.read_blacklist(subject=source,
                                                 path=source_blacklist)
    expected_entries = {orig_scan.replace(source, target): comment
                        for (orig_scan, comment) in source_entries.items()}

    if not expected_entries:
        return

    target_entries = datman.utils.read_blacklist(subject=target,
                                                 path=target_blacklist)
    missing_scans = set(expected_entries.keys()) - set(target_entries.keys())

    new_entries = {}
    for scan in missing_scans:
        if not tags_match(scan, tags):
            continue
        new_entries[scan] = expected_entries[scan]

    if not new_entries:
        return

    datman.utils.update_blacklist(new_entries, path=target_blacklist)


def copy_checklist_entry(source_id, target_id, target_checklist_path):
    target_comment = datman.utils.read_checklist(subject=target_id)
    if target_comment:
        # Checklist entry already exists and has been signed off.
        return

    source_comment = datman.utils.read_checklist(subject=source_id)
    if not source_comment:
        # No source comment to copy
        return

    entries = {target_id: source_comment}
    datman.utils.update_checklist(entries, path=target_checklist_path)


def copy_metadata(source_id, target_id, tags):
    source_config = datman.config.config(study=source_id)
    target_config = datman.config.config(study=target_id)
    source_metadata = source_config.get_path('meta')
    target_metadata = target_config.get_path('meta')

    checklist_path = os.path.join(target_metadata, 'checklist.csv')
    copy_checklist_entry(source_id, target_id, checklist_path)

    source_blacklist = os.path.join(source_metadata, 'blacklist.csv')
    target_blacklist = os.path.join(target_metadata, 'blacklist.csv')
    copy_blacklist_data(source_id, source_blacklist, target_id,
                        target_blacklist, tags)


def get_resources_dir(subid):
    # Creates its a new config each time to avoid side effects (and future
    # bugs) due to the fact that config.get_path() modifies the study setting.
    config = datman.config.config(study=subid)
    result = os.path.join(config.get_path('resources'), subid)
    return result


def link_resources(source_id, target_id):
    source_resources = get_resources_dir(source_id)
    if not os.path.exists(source_resources):
        return
    target_resources = get_resources_dir(target_id)
    make_link(source_resources, target_resources)


def get_datman_scanid(session_id, config):
    try:
        session = datman.utils.validate_subject_id(session_id, config)
    except datman.scanid.ParseException as e:
        logger.error("Invalid session ID given: {}. Exiting".format(str(e)))
        sys.exit(1)
    return session


def link_session_data(source, target, given_tags):
    # Must give whole source ID, in case the study portion is 'DTI'
    config = datman.config.config(study=source)
    config_target = datman.config.config(study=target)

    source_id = get_datman_scanid(source, config)
    target_id = get_datman_scanid(target, config_target)

    if given_tags:
        # Use the supplied list of tags to link
        tags = [tag.upper() for tag in given_tags.split(',')]
    else:
        # Use the list of tags from the source site's export info
        tags = list(config.get_tags(source_id.site))

    logger.debug("Tags set to {}".format(tags))

    link_resources(source, target)

    if not dashboard.dash_found:
        # The dashboard automatically handles linked checklist/blacklist
        # comments so only update if metadata files are being used instead
        copy_metadata(source, target, tags)

    dirs = get_dirs_to_search(config, tags)
    for path_key in dirs:
        link_files(tags,
                   source_id,
                   target_id,
                   config.get_path(path_key, study=source),
                   config.get_path(path_key, study=target))

    # Return tags used for linking, in case links file needs to be updated
    return tags


def create_linked_session(src_session, trg_session, tags):
    """
    A helper function to allow the main functionality of dm-link-project-scans
    to be imported elsewhere.
    """
    logger.info("Linking the provided source {} and target "
                "{}".format(src_session, trg_session))
    tags = link_session_data(src_session, trg_session, tags)

    src_link_file = get_external_links_csv(src_session)
    trg_link_file = get_external_links_csv(trg_session)

    for link_file in [src_link_file, trg_link_file]:
        write_link_file(link_file, src_session, trg_session, tags)


def main():
    global DRYRUN, CONFIG
    arguments = docopt(__doc__)
    link_file = arguments['<link_file>']
    src_session = arguments['<src_session>']
    trg_session = arguments['<trg_session>']
    tags = arguments['<tags>']
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    DRYRUN = arguments['--dry-run']
    quiet = arguments['--quiet']

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

    create_linked_session(src_session, trg_session, tags)


if __name__ == '__main__':
    main()
