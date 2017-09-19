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
from datman.docopt import docopt
import datman.dashboard

DRYRUN = False
LINK_FILE_HEADERS = ['subject', 'target_subject', 'tags']

logging.basicConfig(level=logging.WARN,
        format='[%(name)s] %(levelname)s : %(message)s',
        disable_existing_loggers=False)
logger = logging.getLogger(os.path.basename(__file__))


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


def add_link_to_dbase(source, target):
    logger.debug('Creating database entry linking {} to {}.'.format(source,
                                                                    target))
    ident_src = dm.scanid.parse_filename(source)
    ident_trg = dm.scanid.parse_filename(target)

    db_src = datman.dashboard.dashboard(ident_src[0].get_full_subjectid_with_timepoint())
    db_trg = datman.dashboard.dashboard(ident_trg[0].get_full_subjectid_with_timepoint())

    src_session_db = db_src.get_add_session(ident_src[0].get_full_subjectid_with_timepoint())
    trg_session_db = db_trg.get_add_session(ident_trg[0].get_full_subjectid_with_timepoint())

    if not src_session_db:
        logger.debug('Failed to find source session:{} in database.'
                     .format(os.path.basename(source)))
        return

    if not trg_session_db:
        logger.debug('Failed to find target session:{} in database.'
                     .format(os.path.basename(target)))
        return

    src_scan_db = db_src.get_add_scan(os.path.basename(source))

    if not src_scan_db:
        logger.debug('Failed to find src scan:{} in database.'
                     .format(os.path.basename(source)))

    new_name = datman.scanid.make_filename(ident_trg[0],
                                           ident_trg[1],
                                           ident_trg[2],
                                           ident_trg[3])
    if not DRYRUN:
        datman.dashboard.get_add_session_scan_link(trg_session_db,
                                                   src_scan_db,
                                                   new_name,
                                                   is_primary=False)


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
                # first need to capture the file extension as it gets lost
                # when using dm.scanid to make the new name
                ext = dm.utils.get_extension(filename)

                trg_name = dm.scanid.make_filename(trg_session, file_tag,
                                                   series, description)
                src_file = os.path.join(root, filename)
                trg_file = os.path.join(trg_dir, trg_name) + ext

                make_link(src_file, trg_file)
                add_link_to_dbase(src_file, trg_file)


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

def tags_match(blacklist_entry, tags):
    """
    Returns true if the filename in <blacklist_entry> contains a tag in <tags>.
    """
    try:
        blacklisted_file = blacklist_entry.split()[0]
    except IndexError:
        # Empty line
        return False

    try:
        _, tag, _, _ = datman.scanid.parse_filename(blacklisted_file)
    except datman.scanid.ParseException:
        logger.error("Blacklist entry {} contains non-datman filename. " \
                "Entry will not be copied to target blacklist.".format(
                blacklist_entry))
        return False

    if tag not in tags:
        return False

    return True

def update_file(file_path, line):
    logger.debug("Updating file {} with entry {}".format(file_path, line))
    if DRYRUN:
        return
    with open(file_path, 'a') as file_name:
        file_name.write(line)

def get_blacklist_scans(subject_id, blacklist_path, new_id=None):
    """
    Finds all entries in <blacklist_path> that belong to the participant with
    ID <subject_id>. If <new_id> is given, it modifies the found lines to
    contain the new subject's ID.
    """
    try:
        with open(blacklist_path, 'r') as blacklist:
            lines = blacklist.readlines()
    except IOError:
        lines = []

    entries = []
    for line in lines:
        if subject_id in line:
            if new_id is not None:
                line = line.replace(subject_id, new_id)
            entries.append(line)
    return entries

def copy_blacklist_data(source, source_blacklist, target, target_blacklist, tags):
    """
    Adds entries from <source_blacklist> to <target_blacklist> if they contain
    one of the given tags and have not already been added.
    """
    source_entries = get_blacklist_scans(source, source_blacklist, new_id=target)
    if not source_entries:
        return

    target_entries = get_blacklist_scans(target, target_blacklist)
    missing_entries = set(source_entries) - set(target_entries)
    if not missing_entries:
        return

    for entry in missing_entries:
        if tags_match(entry, tags):
            update_file(target_blacklist, entry)

def delete_old_checklist_entry(checklist_path, entry):
    with open(checklist_path, 'r') as checklist:
        checklist_entries = checklist.readlines()

    new_lines = []
    for line in checklist_entries:
        fields = line.split()
        if not fields:
            continue
        if fields[0] == entry:
            continue
        new_lines.append(" ".join(fields) + '\n')

    with open(checklist_path, 'w') as new_list:
        for line in new_lines:
            new_list.write(line)

def copy_checklist_entry(source_id, target_id, target_checklist_path):
    target_comment = datman.utils.check_checklist(target_id, study=target_id)
    if target_comment:
        # Checklist entry already exists and has been signed off.
        return

    source_comment = datman.utils.check_checklist(source_id, study=source_id)
    if not source_comment:
        # No source comment to copy
        return

    qc_page_name = "qc_{}.html".format(target_id)
    if target_comment == '':
        # target_comment == '' means there's a qc page entry, but its not signed
        # off. Old entry must be deleted to avoid duplication.
        delete_old_checklist_entry(target_checklist_path, qc_page_name)
    qc_report_entry = " ".join([qc_page_name, source_comment])
    update_file(target_checklist_path, qc_report_entry + '\n')

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
    # Creates its a new config each time to avoid side effects (and future bugs)
    # due to the fact that config.get_path() modifies the study setting.
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
    except RuntimeError as e:
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
        source_export_info = config.get_export_info_object(source_id.site)
        tags = source_export_info.tags

    logger.debug("Tags set to {}".format(tags))

    link_resources(source, target)
    copy_metadata(source, target, tags)

    dirs = get_dirs_to_search(config, tags)
    for path_key in dirs:
        link_files(tags, source_id, target_id,
                config.get_path(path_key, study=source),
                config.get_path(path_key, study=target))

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
