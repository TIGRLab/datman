#!/usr/bin/env python
"""
Extracts data from XNAT archive folders into a few well-known formats.

Usage:
    dm_xnat_extract.py [options] <study> [-t <tag>]...
    dm_xnat_extract.py [options] <study> <experiment> [-t <tag>]...

Arguments:
    <study>                  Nickname of the study to process
    <experiment>             Full ID of the experiment to process

Options:
    --blacklist FILE         Table listing series to ignore override the
                             default metadata/blacklist.csv
    -v --verbose             Show intermediate steps
    -d --debug               Show debug messages
    -q --quiet               Show minimal output
    -n --dry-run             Do nothing
    --server URL             XNAT server to connect to, overrides the server
                             defined in the configuration files.
    -u --username USER       XNAT username. If specified then the environment
                             variables (or any credential files) are ignored
                             and you are prompted for a password. Note that if
                             multiple servers are configured for a study the
                             login used should be valid for all servers.
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


SERVERS = {}
SERVER_OVERRIDE = None
AUTH = None
cfg = None
DRYRUN = False
db_ignore = False  # if True dont update the dashboard db
wanted_tags = None


def main():
    global AUTH
    global SERVER_OVERRIDE
    global cfg
    global DRYRUN
    global wanted_tags
    global db_ignore

    arguments = docopt(__doc__)
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    quiet = arguments['--quiet']
    study = arguments['<study>']
    experiment = arguments['<experiment>']
    wanted_tags = arguments['--tag']
    username = arguments['--username']
    db_ignore = arguments['--dont-update-dashboard']
    SERVER_OVERRIDE = arguments['--server']

    if arguments['--dry-run']:
        DRYRUN = True
        db_ignore = True

    configure_logging(study, quiet, verbose, debug)

    cfg = datman.config.config(study=study)
    if username:
        AUTH = datman.xnat.get_auth(username)

    if experiment:
        experiments = collect_experiment(experiment, study, cfg)
    else:
        experiments = collect_all_experiments(cfg)

    logger.info("Found {} experiments for study {}".format(
        len(experiments), study))

    for xnat, project, experiment in experiments:
        process_experiment(xnat, project, experiment)


def configure_logging(study, quiet=None, verbose=None, debug=None):
    ch = logging.StreamHandler(sys.stdout)

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
    logging.getLogger('datman.xnat').addHandler(ch)


def collect_experiment(user_exper, study, cfg):
    ident = datman.utils.validate_subject_id(user_exper, cfg)

    try:
        convention = cfg.get_key("XNAT_CONVENTION", site=ident.site)
    except datman.config.UndefinedSetting:
        convention = "DATMAN"

    if convention == "KCNI":
        try:
            settings = cfg.get_key("ID_MAP")
        except datman.config.UndefinedSetting:
            settings = None
        ident = datman.scanid.get_kcni_identifier(ident, settings)

    xnat = datman.xnat.get_connection(cfg,
                                      site=ident.site,
                                      url=SERVER_OVERRIDE,
                                      auth=AUTH,
                                      server_cache=SERVERS)

    # get the list of XNAT projects linked to the datman study
    xnat_projects = cfg.get_xnat_projects(study)

    # identify which xnat project the subject is in
    xnat_project = xnat.find_project(ident.get_xnat_subject_id(),
                                     xnat_projects)
    if not xnat_project:
        logger.error("Failed to find experiment {}. Ensure it matches an "
                     "existing experiment ID in XNAT.".format(user_exper))
        return

    return [(xnat, xnat_project, ident)]


def collect_all_experiments(config):
    experiments = []

    # for each XNAT project send out URL request for list of experiment IDs
    # then validate and add (connection, XNAT project, subject ID) to output
    for project, sites in get_projects(config).items():
        for site in sites:
            xnat = datman.xnat.get_connection(config,
                                              site=site,
                                              url=SERVER_OVERRIDE,
                                              auth=AUTH,
                                              server_cache=SERVERS)
            for exper_id in xnat.get_experiment_ids(project):
                try:
                    ident = datman.utils.validate_subject_id(exper_id, config)
                except datman.scanid.ParseException:
                    logger.error("Invalid experiment ID {} in project {}."
                                 "".format(exper_id, project))
                    continue
                if (ident.session is None and
                        not datman.scanid.is_phantom(ident)):
                    logger.error("Invalid experiment ID {} in project {}. "
                                 "Reason - Not a phantom, but missing session "
                                 "number".format(exper_id, project))
                    continue
                if ident.modality != "MR":
                    continue
                experiments.append((xnat, project, ident))

    return experiments


def get_projects(config):
    """Find all XNAT projects and the list of scan sites uploaded to each one.

    Args:
        config (:obj:`datman.config.config`): The config for a study

    Returns:
        dict: A map of XNAT project names to the URL(s) of the server holding
            that project.
    """
    projects = {}
    for site in config.get_sites():
        xnat_project = config.get_key("XNAT_Archive", site=site)
        projects.setdefault(xnat_project, set()).add(site)
    return projects


def process_experiment(xnat, project, ident):
    experiment_label = ident.get_xnat_experiment_id()

    logger.info("Processing experiment: {}".format(experiment_label))

    try:
        xnat_experiment = xnat.get_experiment(
            project, ident.get_xnat_subject_id(), experiment_label)
    except Exception as e:
        logger.error("Unable to retrieve experiment {} from XNAT server. "
                     "{}: {}".format(experiment_label, type(e).__name__, e))
        return

    if not db_ignore:
        logger.debug("Adding session {} to dashboard".format(experiment_label))
        try:
            db_session = dashboard.get_session(ident, create=True)
        except dashboard.DashboardException as e:
            logger.error("Failed adding session {}. Reason: {}".format(
                experiment_label, e))
        else:
            set_alt_ids(db_session, ident)
            set_date(db_session, xnat_experiment)

    if xnat_experiment.resource_files:
        process_resources(xnat, ident, xnat_experiment)
    if xnat_experiment.scans:
        process_scans(xnat, ident, xnat_experiment)


def set_date(session, experiment):
    if not experiment.date:
        logger.debug("No scanning date found for {}, leaving blank.".format(
            session))
        return

    try:
        date = datetime.strptime(experiment.date, '%Y-%m-%d')
    except ValueError:
        logger.error('Invalid date {} for scan session {}'.format(date,
                                                                  session))
        return

    if date == session.date:
        return

    session.date = date
    session.save()


def set_alt_ids(session, ident):
    if not isinstance(ident, datman.scanid.KCNIIdentifier):
        return
    session.timepoint.kcni_name = ident.get_xnat_subject_id()
    session.kcni_name = ident.get_xnat_experiment_id()
    session.save()


def process_resources(xnat, ident, xnat_experiment):
    """Export any non-dicom resources from the XNAT archive"""
    logger.info("Extracting {} resources from {}".format(
        len(xnat_experiment.resource_files), xnat_experiment.name))

    base_path = os.path.join(cfg.get_path('resources'), str(ident))

    if not os.path.isdir(base_path):
        logger.info("Creating resources dir {}".format(base_path))
        try:
            os.makedirs(base_path)
        except OSError:
            logger.error("Failed creating resources dir {}".format(base_path))
            return

    for label in xnat_experiment.resource_IDs:
        if label == 'No Label':
            target_path = os.path.join(base_path, 'MISC')
        else:
            target_path = os.path.join(base_path, label)

        try:
            target_path = datman.utils.define_folder(target_path)
        except OSError:
            logger.error("Failed creating target folder: {}"
                         .format(target_path))
            continue

        xnat_resource_id = xnat_experiment.resource_IDs[label]

        try:
            resources = xnat.get_resource_list(xnat_experiment.project,
                                               xnat_experiment.subject,
                                               xnat_experiment.name,
                                               xnat_resource_id)
        except Exception as e:
            logger.error("Failed getting resource {} for experiment {}. "
                         "Reason - {}".format(xnat_resource_id,
                                              xnat_experiment.name,
                                              e))
            continue

        if not resources:
            continue

        for resource in resources:
            resource_path = os.path.join(target_path, resource['URI'])
            if os.path.isfile(resource_path):
                logger.debug("Resource {} from experiment {} already exists"
                             .format(resource['name'], xnat_experiment.name))

            else:
                logger.info("Downloading {} from experiment {}"
                            .format(resource['name'], xnat_experiment.name))
                download_resource(xnat,
                                  xnat_experiment,
                                  xnat_resource_id,
                                  resource['URI'],
                                  resource_path)


def download_resource(xnat, xnat_experiment, xnat_resource_id,
                      xnat_resource_uri, target_path):
    """
    Download a single resource file from XNAT. Target path should be
    full path to store the file, including filename
    """

    try:
        source = xnat.get_resource(xnat_experiment.project,
                                   xnat_experiment.subject,
                                   xnat_experiment.name,
                                   xnat_resource_id,
                                   xnat_resource_uri,
                                   zipped=False)
    except Exception as e:
        logger.error("Failed downloading resource archive from {} with "
                     "reason: {}".format(xnat_experiment.name, e))
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
    except (IOError, OSError):
        logger.error("Failed copying resource {} to target {}"
                     .format(source, target_path))

    # finally delete the temporary archive
    try:
        os.remove(source)
    except OSError:
        logger.error("Failed to remove temporary archive {} on system {}"
                     .format(source, platform.node()))
    return target_path


def process_scans(xnat, ident, xnat_experiment):
    """Download scans from an XNAT experiment and convert to valid formats.

    Args:
        ident (:obj:`datman.scanid.Identifier`): A valid datman Identifier to
            name files after.
        xnat_experiment (:obj:`datman.xnat.XNATExperiment`): An experiment
            from the XNAT server to download dicoms from.
    """

    logger.info("Processing scans in experiment {}".format(
        xnat_experiment.name))

    # load the export info from the site config files
    tags = cfg.get_tags(site=ident.site)

    if not tags.series_map:
        logger.error("Failed to get export info for study {} at site {}"
                     .format(cfg.study_name, ident.site))
        return

    for scan in xnat_experiment.scans:

        if not scan.raw_dicoms_exist():
            logger.warning("Skipping series {} for session {}. No RAW dicoms "
                           "exist".format(scan.series, xnat_experiment.name))
            continue

        if scan.is_derived():
            logger.warning("Series {} in session {} is a derived scan. "
                           "Skipping.".format(
                               scan.series, xnat_experiment.name))
            continue

        if not scan.description:
            logger.error("Can't find description for series {} from session {}"
                         .format(scan.series, xnat_experiment.name))
            continue

        try:
            scan.set_datman_name(str(ident), tags.series_map)
        except Exception as e:
            logger.info("Failed to make file name for series {} in session "
                        "{}. Reason {}: {}".format(scan.series,
                                                   xnat_experiment.name,
                                                   type(e).__name__,
                                                   e))
            continue

        if len(scan.tags) > 1 and not scan.multiecho:
            logger.error("Multiple export patterns match for {}, "
                         "descr: {}, tags: {}".format(xnat_experiment.name,
                                                      scan.description,
                                                      scan.tags))
            continue

        if not db_ignore:
            update_dashboard(scan.names)

        for fname, tag in zip(scan.names, scan.tags):
            if wanted_tags and (tag not in wanted_tags):
                continue
            export_formats = get_export_formats(ident, fname, tags, tag)
            if export_formats:
                get_scans(xnat, ident, scan, fname, export_formats)


def update_dashboard(scan_names):
    for file_stem in scan_names:
        logger.info("Adding scan {} to dashboard".format(file_stem))
        try:
            dashboard.get_scan(file_stem, create=True)
        except Exception as e:
            logger.error("Failed adding scan {} to dashboard with "
                         "error: {}".format(file_stem, e))


def get_export_formats(ident, file_stem, tags, tag):
    try:
        blacklist_entry = datman.utils.read_blacklist(scan=file_stem,
                                                      config=cfg)
    except datman.scanid.ParseException:
        logger.error("{} is not a datman ID. Skipping.".format(file_stem))
        return

    if blacklist_entry:
        logger.warning("Skipping export of {} due to blacklist entry "
                       "'{}'".format(file_stem, blacklist_entry))
        return

    try:
        export_formats = tags.get(tag)['formats']
    except KeyError:
        logger.error("Export settings for tag: {} not found for "
                     "study: {}".format(tag, cfg.study_name))
        return

    export_formats = series_is_processed(ident, file_stem, export_formats)
    if not export_formats:
        logger.debug("Scan: {} has been processed. Skipping"
                     .format(file_stem))
        return

    return export_formats


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


def get_scans(xnat, ident, xnat_scan, output_name, export_formats):
    logger.info("Getting scan from XNAT")

    # setup the export functions for each format
    xporters = {'mnc': export_mnc_command,
                'nii': export_nii_command,
                'nrrd': export_nrrd_command,
                'dcm': export_dcm_command}

    # scan hasn't been completely processed, get it from XNAT
    with datman.utils.make_temp_directory(prefix='dm_xnat_extract_') as temp:
        src_dir = get_dicom_archive_from_xnat(xnat, xnat_scan, temp)

        if not src_dir:
            logger.error("Failed getting series {} for experiment {} from XNAT"
                         .format(xnat_scan.series, xnat_scan.experiment))
            return

        for export_format in export_formats:
            target_base_dir = cfg.get_path(export_format)
            target_dir = os.path.join(
                target_base_dir,
                ident.get_full_subjectid_with_timepoint())
            try:
                target_dir = datman.utils.define_folder(target_dir)
            except OSError:
                logger.error("Failed creating target folder: {}"
                             .format(target_dir))
                return

            try:
                exporter = xporters[export_format]
            except KeyError:
                logger.error("Export format {} not defined".format(
                             export_format))

            logger.info('Exporting scan {} to format {}'
                        ''.format(xnat_scan.names, export_format))
            try:
                exporter(src_dir, target_dir, output_name, xnat_scan)
            except Exception:
                logger.error("An error happened exporting {} from scan {} "
                             "in experiment {}".format(
                                 export_format, xnat_scan.series,
                                 xnat_scan.experiment))

    logger.info('Completed exports')


def get_dicom_archive_from_xnat(xnat, xnat_scan, tempdir):
    """
    Downloads and extracts a dicom archive from XNAT to a local temp folder
    Returns the path to the tempdir (for later cleanup) as well as the
    path to the .dcm files inside the tempdir
    """
    # make a copy of the dicom files in a local directory
    logger.info("Downloading dicoms for: {}, series: {}"
                .format(xnat_scan.experiment, xnat_scan.series))
    try:
        dicom_archive = xnat.get_dicom(xnat_scan.project,
                                       xnat_scan.subject,
                                       xnat_scan.experiment,
                                       xnat_scan.series)
    except Exception:
        logger.error("Failed to download dicom archive for: {}, series: {}"
                     .format(xnat_scan.subject, xnat_scan.series))
        return None

    logger.info("Unpacking archive")

    try:
        with zipfile.ZipFile(dicom_archive, 'r') as myzip:
            myzip.extractall(tempdir)
    except Exception:
        logger.error("An error occurred unpacking dicom archive for: {}. "
                     "Skipping".format(xnat_scan.subject))
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
        logger.warning("There were no valid dicom files in XNAT session {}, "
                       "series {}".format(xnat_scan.subject, xnat_scan.series))
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


def export_mnc_command(seriesdir, outputdir, stem, scan=None):
    """Converts a DICOM series to MINC format"""
    outputfile = os.path.join(outputdir, stem) + '.mnc'

    try:
        check_create_dir(outputdir)
    except Exception:
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


def export_nii_command(seriesdir, outputdir, stem, scan=None):
    """Converts a DICOM series to NifTi format"""
    try:
        check_create_dir(outputdir)
    except Exception:
        return

    logger.info("Exporting series {}".format(seriesdir))

    # convert into tempdir
    with datman.utils.make_temp_directory(prefix="dm_xnat_extract_") as tmpdir:
        _, log_msgs = datman.utils.run('dcm2niix -z y -b y -o {} {}'
                                       .format(tmpdir, seriesdir), DRYRUN)
        # move nii and files (BIDS, dirs, etc) from tmpdir/ to nii/
        for f in glob('{}/*'.format(tmpdir)):
            bn = os.path.basename(f)
            ext = datman.utils.get_extension(f)
            # regex is made up of 14 digit timestamp and 1-3 digit series num
            regex = "files_(.*)_([0-9]{14})_([0-9]{1,3})(.*)?" + ext
            m = re.search(regex, bn)
            if not m:
                logger.error("Unable to parse file {} using the regex"
                             "".format(bn))
                continue

            if scan and scan.multiecho:
                try:
                    echo = int(m.group(4).split('e')[-1][0])
                    stem = scan.echo_dict[echo]
                except Exception:
                    logger.error("Unable to parse valid echo number from file "
                                 "{}".format(bn))
                    return

            outputfile = os.path.join(outputdir, stem) + ext
            if os.path.exists(outputfile):
                logger.error("Output file {} already exists. Skipping"
                             .format(outputfile))
                continue

            return_code, _ = datman.utils.run("mv {} {}"
                                              .format(f, outputfile), DRYRUN)
            if return_code:
                logger.debug("Moving dcm2niix output {} to {} has failed"
                             .format(f, outputdir))
                continue
            if ext == '.json' and dashboard.dash_found:
                update_side_cars(outputfile)
            error_log = os.path.join(outputdir, stem) + '.err'
            report_issues(error_log, str(log_msgs))


def update_side_cars(side_car):
    scan = get_scan_db_record(side_car)
    if not scan:
        return
    try:
        scan.add_json(side_car)
    except Exception as e:
        logger.error("Failed to add JSON side car to dashboard record "
                     "for {}. Reason - {}".format(side_car, e))


def get_scan_db_record(scan_name):
    try:
        scan = dashboard.get_scan(scan_name)
    except Exception as e:
        logger.error("Failed to retrieve dashboard record for {}. "
                     "Reason - {}".format(scan_name, e))
        return None
    return scan


def report_issues(dest, messages):
    # The only issue we care about currently is if files are missing
    if 'missing images' not in messages:
        return
    try:
        with open(dest, "w") as output:
            output.write(messages)
    except Exception as e:
        logger.error("Failed writing dcm2niix conversion errors to {}. Reason "
                     "- {} {}".format(dest, type(e).__name__, e))
    if dashboard.dash_found:
        scan = get_scan_db_record(os.path.splitext(os.path.basename(dest))[0])
    if not scan:
        return
    scan.add_error(messages)


def export_nrrd_command(seriesdir, outputdir, stem, scan=None):
    """Converts a DICOM series to NRRD format"""
    outputfile = os.path.join(outputdir, stem) + '.nrrd'
    try:
        check_create_dir(outputdir)
    except Exception:
        return
    if os.path.exists(outputfile):
        logger.warning("{}: output {} exists. Skipping"
                       .format(seriesdir, outputfile))
        return

    logger.debug("Exporting series {} to {}".format(seriesdir, outputfile))

    nrrd_script = os.path.join(os.path.dirname(__file__), "dcm_to_nrrd.sh")
    cmd = '{} {} {} {}'.format(nrrd_script, seriesdir, stem, outputdir)

    datman.utils.run(cmd, DRYRUN)


def export_dcm_command(seriesdir, outputdir, stem, scan=None):
    """Copies a DICOM for each echo number in a scan series."""
    try:
        check_create_dir(outputdir)
    except Exception:
        return

    logger.info("Exporting series {}".format(seriesdir))

    if scan and scan.multiecho:
        dcm_dict = {}
        for path in glob(seriesdir + '/*'):
            try:
                dcm_echo_num = dicom.read_file(path).EchoNumbers
                if dcm_echo_num not in dcm_dict.keys():
                    dcm_dict[int(dcm_echo_num)] = path
                if len(dcm_dict.keys()) == 2:
                    break
            except dicom.filereader.InvalidDicomError:
                pass

    else:
        for path in glob(seriesdir + '/*'):
            try:
                dicom.read_file(path)
                dcmfile = path
                break
            except dicom.filereader.InvalidDicomError:
                pass

    if scan and scan.multiecho:
        for echo_num, dcm_echo_num in zip(scan.echo_dict.keys(),
                                          dcm_dict.keys()):
            outputfile = os.path.join(outputdir,
                                      scan.echo_dict[echo_num] + '.dcm')
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


if __name__ == '__main__':
    main()
