#!/usr/bin/env python
"""
Extracts data from XNAT archive folders into a few well-known formats.

Usage:
    dm_xnat_extract.py [options] <study> [-t <tag>]...
    dm_xnat_extract.py [options] <study> <session> [-t <tag>]...

Arguments:
    <study>            Nickname of the study to process
    <session>          Fullname of the session to process

Options:
    --blacklist FILE         Table listing series to ignore override the default metadata/blacklist.csv
    -v --verbose             Show intermediate steps
    -d --debug               Show debug messages
    -q --quiet               Show minimal output
    -n --dry-run             Do nothing
    --server URL             XNAT server to connect to, overrides the server defined in the site config file.
    -u --username USER       XNAT username. If specified then the credentials file is ignored and you are prompted for password.
    --dont-update-dashboard  Dont update the dashboard database
    -t --tag tag,...         List of scan tags to download

OUTPUT FOLDERS
    Each dicom series will be converted and placed into a subfolder of the
    datadir named according to the converted filetype and subject ID, e.g.

        data/
            nifti/
                SPN01_CMH_0001_01/
                    (all nifti acquisitions for this subject-timepoint)

OUTPUT FILE NAMING

    Each dicom series will be and named according to the following schema:

        <scanid>_<tag>_<series#>_<description>.<ext>

    Where,
        <scanid>  = the scan id from the file name, eg. DTI_CMH_H001_01_01
        <tag>     = a short code indicating the data type (e.g. T1, DTI, etc..)
        <series#> = the dicom series number in the exam
        <descr>   = the dicom series description
        <ext>     = appropriate filetype extension

    For example, a T1 in nifti format might be named:

        DTI_CMH_H001_01_01_T1_11_Sag-T1-BRAVO.nii.gz

    The <tag> is determined from project_settings.yml

NON-DICOM DATA
    XNAT puts "other" (i.e. non-DICOM data) into the RESOURCES folder, defined
    in paths:resources.

    data will be copied to a subfolder of the data directory named
    paths:resources/<scanid>, for example:

        /path/to/resources/SPN01_CMH_0001_01_01/

DEPENDENCIES
    dcm2nii

"""
from datetime import datetime
from glob import glob
import logging
import os
import platform
import shutil
import sys
import re
import zipfile

from docopt import docopt
import pydicom as dicom

import datman.dashboard as dashboard
import datman.config
import datman.xnat
import datman.utils
import datman.scan
import datman.scanid
import datman.exceptions

logger = logging.getLogger(os.path.basename(__file__))


xnat = None
cfg = None
DRYRUN = False
db_ignore = False  # if True dont update the dashboard db
wanted_tags = None


def main():
    global xnat
    global cfg
    global DRYRUN
    global wanted_tags

    arguments = docopt(__doc__)
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    quiet = arguments['--quiet']
    study = arguments['<study>']
    session = arguments['<session>']
    wanted_tags = arguments['--tag']
    server = arguments['--server']
    username = arguments['--username']
    db_ignore = arguments['--dont-update-dashboard']

    if arguments['--dry-run']:
        DRYRUN = True
        db_ignore = True

    # setup logging
    ch = logging.StreamHandler(sys.stdout)

    # setup log levels
    log_level = logging.WARNING

    if quiet:
        log_level = logging.ERROR
    if verbose:
        log_level = logging.INFO
    if debug:
        log_level = logging.DEBUG

    logger.setLevel(log_level)
    ch.setLevel(log_level)

    formatter = logging.Formatter('%(asctime)s - %(name)s - {study} - '
                                  '%(levelname)s - %(message)s'
                                  .format(study=study))

    ch.setFormatter(formatter)

    logger.addHandler(ch)
    logging.getLogger('datman.utils').addHandler(ch)
    logging.getLogger('datman.dashboard').addHandler(ch)

    # setup the config object
    logger.info("Loading config")

    cfg = datman.config.config(study=study)

    # get base URL link to XNAT server, authentication info
    server = datman.xnat.get_server(cfg, url=server)
    username, password = datman.xnat.get_auth(username)

    # initialize requests module object for XNAT REST API
    xnat = datman.xnat.xnat(server, username, password)

    # get the list of XNAT projects linked to the datman study
    xnat_projects = cfg.get_xnat_projects(study)

    if session:
        # if session has been provided on the command line, identify which
        # project it is in
        try:
            xnat_project = xnat.find_session(session, xnat_projects)
        except datman.exceptions.XnatException as e:
            raise e

        if not xnat_project:
            logger.error("Failed to find session: {} in XNAT. "
                         "Ensure it is named correctly with timepoint and repeat."
                         .format(session))
            return

        sessions = [(xnat_project, session)]
    else:
        sessions = collect_sessions(xnat_projects, cfg)

    logger.info("Found {} sessions for study: {}"
                .format(len(sessions), study))

    for session in sessions:
        process_session(session)


def collect_sessions(xnat_projects, config):
    sessions = []

    # for each XNAT project send out URL request for list of session records
    # then validate and add (XNAT project, subject ID ['label']) to output list
    for project in xnat_projects:
        project_sessions = xnat.get_sessions(project)
        for session in project_sessions:
            try:
                sub_id = datman.utils.validate_subject_id(session['label'],
                                                          config)
            except RuntimeError as e:
                logger.error("Invalid ID {} in project {}. Reason: {}"
                             .format(session['label'], project, str(e)))
                continue

            if not datman.scanid.is_phantom(session['label']) and sub_id.session is None:
                logger.error("Invalid ID {} in project {}. Reason: Not a "
                             "phantom, but missing series number"
                             .format(session['label'], project))
                continue

            sessions.append((project, session['label']))

    return sessions


def process_session(session):
    xnat_project = session[0]
    session_label = session[1]

    logger.info("Processing session: {}".format(session_label))

    # session_label should be a valid datman scanid
    try:
        ident = datman.scanid.parse(session_label)
    except datman.scanid.ParseException:
        logger.error("Invalid session: {}. Skipping".format(session_label))
        return

    # check that the session is valid on XNAT
    try:
        xnat.get_session(xnat_project, session_label)
    except Exception as e:
        logger.error("Error while getting session {} from XNAT. "
                     "Message: {}".format(session_label, e.message))
        return

    # look into XNAT project and get list of experiments
    try:
        experiments = xnat.get_experiments(xnat_project, session_label)
    except Exception as e:
        logger.warning("Failed getting experiments for: {} in project: {} "
                       "with reason: {}"
                       .format(session_label, xnat_project, e))
        return

    # we expect exactly 1 experiment per session
    if len(experiments) > 1:
        logger.error("Found more than one experiment for session: {} "
                     "in study: {}. Skipping"
                     .format(session_label, xnat_project))
        return

    if not experiments:
        logger.error("Session: {} in study: {} has no experiments"
                     .format(session_label, xnat_project))
        return

    experiment_label = experiments[0]['label']

    # experiment_label should be the same as the session_label
    if not experiment_label == session_label:
        logger.warning("Experiment label: {} doesn't match session label: {}"
                       .format(experiment_label, session_label))

    # retrieve json table from project --> session --> experiment
    try:
        experiment = xnat.get_experiment(xnat_project,
                                         session_label,
                                         experiment_label)
    except Exception as e:
        logger.error("Failed getting experiment for session: {} with reason"
                     .format(session_label, e))
        return

    if not experiment:
        logger.warning("No experiments found for session: {}"
                       .format(session_label))
        return

    if not db_ignore:
        logger.debug("Adding session {} to dashboard".format(session_label))
        try:
            db_session = dashboard.get_session(ident, create=True)
        except dashboard.DashboardException as e:
            logger.error("Failed adding session {}. Reason: {}".format(
                    db_session, e))
        else:
            set_date(db_session, experiment)

    # experiment['children'] is a list of top level folders in XNAT
    # project --> session --> experiments
    for data in experiment['children']:
        if data['field'] == 'resources/resource':
            process_resources(xnat_project, session_label, experiment_label, data)
        elif data['field'] == 'scans/scan':
            process_scans(ident, xnat_project, session_label, experiment_label, data)
        else:
            logger.warning("Unrecognised field type: {} for experiment: {} "
                           "in session: {} from study: {}"
                           .format(data['field'],
                                   experiment_label,
                                   session_label,
                                   xnat_project))

def set_date(session, experiment):
    try:
        date = experiment['data_fields']['date']
    except KeyError:
        logger.error("No scanning date found for {}, leaving blank.".format(
                session))
        return

    try:
        date = datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        logger.error('Invalid date {} for scan session {}'.format(date,
                session))
        return

    if date == session.date:
        return

    session.date = date
    session.save()

def process_resources(xnat_project, session_label, experiment_label, data):
    """Export any non-dicom resources from the XNAT archive"""
    logger.info("Extracting {} resources from {}"
                .format(len(data), session_label))
    base_path = os.path.join(cfg.get_path('resources'),
                             session_label)
    if not os.path.isdir(base_path):
        logger.info("Creating resources dir: {}".format(base_path))
        try:
            os.makedirs(base_path)
        except OSError:
            logger.error("Failed creating resources dir: {}".format(base_path))
            return

    for item in data['items']:
        try:
            data_type = item['data_fields']['label']
        except KeyError:
            data_type = 'MISC'

        target_path = os.path.join(base_path, data_type)

        try:
            target_path = datman.utils.define_folder(target_path)
        except OSError:
            logger.error("Failed creating target folder: {}"
                         .format(target_path))
            continue

        xnat_resource_id = item['data_fields']['xnat_abstractresource_id']

        try:
            resources = xnat.get_resource_list(xnat_project,
                                               session_label,
                                               experiment_label,
                                               xnat_resource_id)
            if not resources:
                continue
        except Exception as e:
            logger.error("Failed getting resource: {} "
                         "for session: {} in project: {}"
                         .format(xnat_resource_id, session_label, e))
            continue

        for resource in resources:
            resource_path = os.path.join(target_path, resource['URI'])
            if os.path.isfile(resource_path):
                logger.debug("Resource: {} found for session: {}"
                             .format(resource['name'], session_label))

            else:
                logger.info("Resource: {} not found for session: {}"
                        .format(resource['name'], session_label))
                get_resource(xnat_project,
                             session_label,
                             experiment_label,
                             xnat_resource_id,
                             resource['URI'],
                             resource_path)


def get_resource(xnat_project, xnat_session, xnat_experiment,
                 xnat_resource_id, xnat_resource_uri, target_path):
    """
    Download a single resource file from XNAT. Target path should be
    full path to store the file, including filename
    """

    try:
        source = xnat.get_resource(xnat_project,
                                   xnat_session,
                                   xnat_experiment,
                                   xnat_resource_id,
                                   xnat_resource_uri,
                                   zipped=False)
    except Exception as e:
        logger.error("Failed downloading resource archive from: {} with "
                     "reason: {}".format(xnat_session, e))
        return

    # check that the target path exists
    target_dir = os.path.split(target_path)[0]
    if not os.path.exists(target_dir):
        try:
            os.makedirs(target_dir)
        except OSError:
            logger.error("Failed to create directory: {}".format(target_dir))
            return

    # copy the downloaded file to the target location
    try:
        if not DRYRUN:
            shutil.copyfile(source, target_path)
    except:
        logger.error("Failed copying resource: {} to target: {}"
                     .format(source, target_path))

    # finally delete the temporary archive
    try:
        os.remove(source)
    except OSError:
        logger.error("Failed to remove temporary archive: {} on system: {}"
                     .format(source, platform.node()))
    return(target_path)


def process_scans(ident, xnat_project, session_label, experiment_label, scans):
    """
    Process a set of scans in an XNAT experiment
    scanid is a valid datman.scanid object
    Scans is the json output from XNAT query representing scans
    in an experiment
    """
    logger.info("Processing scans in session: {}"
                .format(session_label))

    # load the export info from the site config files
    tags = cfg.get_tags(site=ident.site)
    exportinfo = tags.series_map

    if not exportinfo:
        logger.error("Failed to get exportinfo for study: {} at site: {}"
                     .format(cfg.study_name, ident.site))
        return

    for scan in scans['items']:
        series_id = scan['data_fields']['ID']
        scan_info = xnat.get_scan_info(xnat_project,
                                       session_label,
                                       experiment_label,
                                       series_id)

        valid_dicoms = check_valid_dicoms(scan_info, series_id, session_label)
        if not valid_dicoms:
            continue

        derived = is_derived(scan_info, series_id, session_label)
        if derived:
            continue

        file_stem, tag, multiecho = create_scan_name(exportinfo,
                                                     scan_info,
                                                     session_label)
        if not file_stem:
            continue

        if multiecho:
            for stem, t in zip(file_stem, tag):
                if wanted_tags and (t not in wanted_tags):
                    continue
                export_formats = process_scan(ident, stem, tags, t)
                if export_formats:
                    get_scans(ident, xnat_project, session_label, experiment_label,
                              series_id, export_formats, file_stem, multiecho)

        else:
            file_stem = file_stem[0]
            tag = tag[0]
            if wanted_tags and (tag not in wanted_tags):
                continue
            export_formats = process_scan(ident, file_stem, tags, tag)
            if export_formats:
                get_scans(ident, xnat_project, session_label, experiment_label,
                          series_id, export_formats, file_stem, multiecho)

    # delete any extra scans that exist in the dashboard
    if not db_ignore:
        local_session = datman.scan.Scan(session_label, cfg)
        try:
            dashboard.delete_extra_scans(local_session)
        except Exception as e:
            logger.error("Failed deleting extra scans from session {} with "
                    "excuse {}".format(session_label, e))


def process_scan(ident, file_stem, tags, tag):
    if not db_ignore:
        logger.info("Adding scan {} to dashboard".format(file_stem))
        try:
            dashboard.get_scan(file_stem, create=True)
        except dashboard.DashboardException as e:
            logger.error("Failed adding scan {} to dashboard with "
                    "error {}".format(file_stem, e))

    blacklist_entry = datman.utils.read_blacklist(scan=file_stem, config=cfg)
    if blacklist_entry:
        logger.warn("Skipping export of {} due to blacklist entry '{}'".format(
                file_stem, blacklist_entry))
        return

    try:
        export_formats = tags.get(tag)['formats']
    except KeyError:
        logger.error("Export settings for tag: {} not found for "
                     "study: {}".format(tag, cfg.study_name))
        return

    export_formats = series_is_processed(ident, file_stem, export_formats)
    if not export_formats:
        logger.warn("Scan: {} has been processed. Skipping"
                    .format(file_stem))
        return

    return export_formats


def create_scan_name(exportinfo, scan_info, session_label):
    """Creates name suitable for a scan including the tags"""
    try:
        series_id = scan_info['data_fields']['ID']
    except TypeError as e:
        logger.error("{} failed. Cause: {}".format(session_label, e.message))

    # try and get the scan description, this isn't always in the correct field
    if 'series_description' in scan_info['data_fields'].keys():
        description = scan_info['data_fields']['series_description']
    elif 'type' in scan_info['data_fields'].keys():
        description = scan_info['data_fields']['type']
    else:
        logger.error("Failed to get description for series: {} "
                     "from session: {}"
                     .format(series_id, session_label))
        return None, None, None

    mangled_descr = mangle(description)
    padded_series = series_id.zfill(2)

    multiecho = is_multiecho(scan_info)

    tag = guess_tag(exportinfo, scan_info, description, multiecho)

    if not tag:
        logger.warning("No matching export pattern for {}, "
                       "descr: {}. Skipping".format(session_label,
                                                    description))
        return None, None, None
    elif len(tag) > 1 and not multiecho:
        logger.error("Multiple export patterns match for {}, "
                     "descr: {}, tags: {}".format(session_label,
                                                  description, tag))
        return None, None, None

    file_stem = ['_'.join([session_label, t, padded_series, mangled_descr]) for t in tag]

    return(file_stem, tag, multiecho)


def mangle(string):
    """Mangles a string to conform with the naming scheme.

    Mangling is roughly: convert runs of non-alphanumeric characters to a dash.

    Does not convert '.' to avoid accidentally mangling extensions and does
    not convert '+'
    """
    if not string:
        string = ""
    return re.sub(r"[^a-zA-Z0-9.+]+","-",string)


def is_multiecho(scan_info):
    multiecho = False
    if 'name' in scan_info['children'][0]['items'][0]['data_fields'].keys():
        if 'MultiEcho' in scan_info['children'][0]['items'][0]['data_fields']['name']:
            multiecho = True
    return multiecho


def guess_tag(exportinfo, scan_info, description, multiecho):
    matches = []
    for tag, p in exportinfo.iteritems():
        description_regex = p['SeriesDescription']
        if isinstance(description_regex, list):
            description_regex = '|'.join(description_regex)
        if re.search(description_regex, description, re.IGNORECASE):
            matches.append(tag)
    if len(matches) == 1:
        return matches
    elif len(matches) == 2 and multiecho:
        return matches
    else:
        # field maps might require more information like image type
        # to distinguish between magnitude, phase and phasediff scans
        try:
            image_type = scan_info['data_fields']['parameters/imageType']
            for tag, p in exportinfo.iteritems():
                if tag in matches:
                    if not re.search(p['ImageType'], image_type):
                        matches.remove(tag)
            if len(matches) == 1:
                return matches
            elif len(matches) == 2 and multiecho:
                return matches
            else:
                return None
        except:
            return None


def check_valid_dicoms(scan_info, series_id, session_label):
    # check if the series contains valid dicom files
    # this is to exclude the secondary dicoms generated by some scanners
    content_types = []

    # check if RAW (indicating DICOM) is a file type, if not skip
    for scan_info_child in scan_info['children']:
        for scan_info_child_item in scan_info_child['items']:
            if 'content' in scan_info_child_item['data_fields']:
                file_type = scan_info_child_item['data_fields']['content']
                if file_type == 'RAW':
                    content_types.append(file_type)

    if not content_types:
        logger.warning("No RAW dicom data found in series: {} session: {}"
                       .format(series_id, session_label))
        return None
    return content_types


def is_derived(scan_info, series_id, session_label):
    try:
        image_type = scan_info['data_fields']['parameters/imageType']
    except:
        logger.warning("Image type for series: {} in session: {} could not be found. Skipping"
                       .format(series_id, session_label))
        return
    if 'DERIVED' in image_type:
        derived = True
        logger.warning("Series: {} in session: {} is a derived scan. Skipping"
                       .format(series_id, session_label))
    else:
        derived = False
    return derived


def series_is_processed(ident, file_stem, export_formats):
    """Returns true if exported files exist for all specified formats"""
    remaining_formats = []
    for f in export_formats:
        outdir = os.path.join(cfg.get_path(f),
                              ident.get_full_subjectid_with_timepoint())
        outfile = os.path.join(outdir, file_stem)
        # need to use wildcards here as dont really know what the
        # file extensions will be
        exists = [os.path.isfile(p) for p in glob(outfile + '.*')]
        if not exists:
            remaining_formats.append(f)
    return remaining_formats


def get_scans(ident, xnat_project, session_label, experiment_label, series_id,
        export_formats, file_stem, multiecho):
    logger.info("Getting scan from XNAT")

    # setup the export functions for each format
    xporters = {'mnc': export_mnc_command,
                'nii': export_nii_command,
                'nrrd': export_nrrd_command,
                'dcm': export_dcm_command}

    # scan hasn't been completely processed, get it from XNAT
    with datman.utils.make_temp_directory(prefix='dm_xnat_extract_') as temp_dir:
        src_dir = get_dicom_archive_from_xnat(xnat_project, session_label,
                                              experiment_label, series_id,
                                              temp_dir)

        if not src_dir:
            logger.error("Failed getting series: {}, session: {} from XNAT"
                         .format(series_id, session_label))
            return

        for export_format in export_formats:
            target_base_dir = cfg.get_path(export_format)
            target_dir = os.path.join(target_base_dir,
                                      ident.get_full_subjectid_with_timepoint())
            try:
                target_dir = datman.utils.define_folder(target_dir)
            except OSError as e:
                logger.error("Failed creating target folder: {}"
                             .format(target_dir))
                return

            try:
                exporter = xporters[export_format]
            except KeyError:
                logger.error("Export format {} not defined".format(export_format))

            logger.info('Exporting scan {} to format {}'.format(file_stem,
                                                                export_format))
            try:
                exporter(src_dir, target_dir, file_stem, multiecho)
            except:
                # The conversion functions dont really ever raise exceptions
                # even when they fail so this is a bit useless
                logger.error("An error happened exporting {} from scan: {} "
                             "in session: {}".format(export_format, series_id,
                                                     session_label))

    logger.info('Completed exports')


def get_dicom_archive_from_xnat(xnat_project, session_label, experiment_label,
                                series, tempdir):
    """
    Downloads and extracts a dicom archive from XNAT to a local temp folder
    Returns the path to the tempdir (for later cleanup) as well as the
    path to the .dcm files inside the tempdir
    """
    # make a copy of the dicom files in a local directory
    logger.info("Downloading dicoms for: {}, series: {}"
                .format(session_label, series))
    try:
        dicom_archive = xnat.get_dicom(xnat_project,
                                       session_label,
                                       experiment_label,
                                       series)
    except Exception as e:
        logger.error("Failed to download dicom archive for: {}, series: {}"
                     .format(session_label, series))
        return None

    logger.info("Unpacking archive")

    try:
        with zipfile.ZipFile(dicom_archive, 'r') as myzip:
            myzip.extractall(tempdir)
    except:
        logger.error("An error occurred unpacking dicom archive for: {}. Skipping"
                     .format(session_label))
        os.remove(dicom_archive)
        return None

    logger.info("Deleting archive file")
    os.remove(dicom_archive)

    # get the root dir for the extracted files
    archive_files = []
    for root, dirname, filenames in os.walk(tempdir):
        for filename in filenames:
            f = os.path.join(root, filename)
            if is_valid_dicom(f):
                archive_files.append(f)

    try:
        base_dir = os.path.dirname(archive_files[0])
    except IndexError:
        logger.warning("There were no valid dicom files in XNAT session: {}, series: {}"
                       .format(session_label, series))
        return None
    return base_dir


def is_valid_dicom(filename):
    try:
        dicom.read_file(filename)
    except IOError:
        return
    except dicom.errors.InvalidDicomError:
        return
    return True


def export_mnc_command(seriesdir, outputdir, stem, multiecho=False):
    """Converts a DICOM series to MINC format"""
    outputfile = os.path.join(outputdir, stem) + '.mnc'

    try:
        check_create_dir(outputdir)
    except:
        return

    if os.path.exists(outputfile):
        logger.warning("{}: output {} exists. Skipping"
                       .format(seriesdir, outputfile))
        return

    logger.debug("Exporting series {} to {}"
                 .format(seriesdir, outputfile))
    cmd = 'dcm2mnc -fname {} -dname "" {}/* {}'.format(stem,
                                                       seriesdir,
                                                       outputdir)
    datman.utils.run(cmd, DRYRUN)


def export_nii_command(seriesdir, outputdir, stem, multiecho=False):
    """Converts a DICOM series to NifTi format"""
    try:
        check_create_dir(outputdir)
    except:
        return
    logger.info("Exporting series {}".format(seriesdir))

    if multiecho:
        echo_dict = get_echo_dict(stem)

    # convert into tempdir
    with datman.utils.make_temp_directory(prefix="dm_xnat_extract_") as tmpdir:
        datman.utils.run('dcm2niix -z y -b y -o {} {}'
                         .format(tmpdir, seriesdir), DRYRUN)
        # move nii and accompanying files (BIDS, dirs, etc) from tmpdir/ to nii/
        for f in glob('{}/*'.format(tmpdir)):
            bn = os.path.basename(f)
            ext = datman.utils.get_extension(f)
            # regex is made up of 14 digit timestamp and 1-3 digit series number
            regex = "files_(.*)_([0-9]{14})_([0-9]{1,3})(.*)?" + ext
            m = re.search(regex, bn)
            if not m:
                logger.error("Unable to parse file {} using the regex".format(bn))
                continue

            if multiecho:
                try:
                    echo = int(m.group(4).split('e')[-1][0])
                    stem = echo_dict[echo]
                except:
                    logger.error("Unable to parse valid echo number from file {}"
                                 .format(bn))
                    return

            outputfile = os.path.join(outputdir, stem) + ext
            if os.path.exists(outputfile):
                logger.error("Output file {} already exists. Skipping"
                             .format(outputfile))
                continue

            return_code, _ = datman.utils.run("mv {} {}/{}{}"
                                              .format(f, outputdir, stem, ext), DRYRUN)
            if return_code:
                logger.debug("Moving dcm2niix output {} to {} has failed"
                             .format(f, outputdir))
                continue


def export_nrrd_command(seriesdir, outputdir, stem, multiecho=False):
    """Converts a DICOM series to NRRD format"""
    outputfile = os.path.join(outputdir, stem) + '.nrrd'
    try:
        check_create_dir(outputdir)
    except:
        return
    if os.path.exists(outputfile):
        logger.warning("{}: output {} exists. Skipping"
                       .format(seriesdir, outputfile))
        return

    logger.debug("Exporting series {} to {}".format(seriesdir, outputfile))

    cmd = 'DWIConvert -i {} --conversionMode DicomToNrrd -o {}.nrrd' \
          ' --outputDirectory {}'.format(seriesdir, stem, outputdir)

    datman.utils.run(cmd, DRYRUN)


def export_dcm_command(seriesdir, outputdir, stem, multiecho=False):
    """Copies a DICOM for each echo number in a scan series."""
    try:
        check_create_dir(outputdir)
    except:
        return

    logger.info("Exporting series {}".format(seriesdir))

    if multiecho:
        echo_dict = get_echo_dict(stem)

        dcm_dict = {}
        for path in glob(seriesdir + '/*'):
            try:
                dcm_echo_num = dicom.read_file(path).EchoNumbers
                if dcm_echo_num not in dcm_dict.keys():
                    dcm_dict[int(dcm_echo_num)] = path
                if len(dcm_dict.keys()) == 2:
                    break
            except dicom.filereader.InvalidDicomError as e:
                pass

    else:
        for path in glob(seriesdir + '/*'):
            try:
                dicom.read_file(path)
                dcmfile = path
                break
            except dicom.filereader.InvalidDicomError as e:
                pass

    if multiecho:
        for echo_num, dcm_echo_num in zip(echo_dict.keys(), dcm_dict.keys()):
            outputfile = os.path.join(outputdir, echo_dict[echo_num]) + '.dcm'
            if os.path.exists(outputfile):
                logger.error("Output file {} already exists. Skipping"
                             .format(outputfile))
                continue
            logger.debug("Exporting a dcm file from {} to {}"
                         .format(seriesdir, outputfile))
            cmd = 'cp {} {}'.format(dcm_dict[dcm_echo_num], outputfile)
            datman.utils.run(cmd, DRYRUN)

    elif dcmfile:
        outputfile = os.path.join(outputdir, stem) + '.dcm'
        if os.path.exists(outputfile):
            logger.error("Output file {} already exists. Skipping"
                         .format(outputfile))
            return
        logger.debug("Exporting a dcm file from {} to {}"
                     .format(seriesdir, outputfile))
        cmd = 'cp {} {}'.format(dcmfile, outputfile)
        datman.utils.run(cmd, DRYRUN)

    else:
        logger.error("No dicom files found in {}".format(seriesdir))
        return


def check_create_dir(target):
    """Checks to see if a directory exists, creates if not"""
    if not os.path.isdir(target):
        logger.info("Creating dir: {}".format(target))
        try:
            os.makedirs(target)
        except OSError as e:
            logger.error("Failed creating dir: {}".format(target))
            raise e


def get_echo_dict(stem):
    echo_dict = {}
    for s in stem:
        ident, tag = datman.scanid.parse_filename(s)[:2]
        echo_num = get_echo_number(ident, tag)
        if echo_num not in echo_dict.keys():
            echo_dict[echo_num] = s
    return echo_dict


def get_echo_number(ident, tag):
    tags = cfg.get_tags(site=ident.site)
    exportinfo = tags.series_map
    for t, p in exportinfo.iteritems():
        if t == tag:
            echo_number = p['EchoNumber']
    return echo_number


if __name__ == '__main__':
    main()
