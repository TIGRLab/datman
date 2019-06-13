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
from collections import namedtuple

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
wanted_tags = None
db_ignore = False

#Constant dict to perform matching between ExportInfo --> data fields in XNAT scan object
PATTERN_TO_SCANINFO = {
        'SeriesDescription' : ['series_description', 'type'],
        'ImageType' : 'parameters/imageType'
        }

def main():
    global xnat
    global cfg
    global DRYRUN
    global wanted_tags
    global db_ignore


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

    configure_logger(study, quiet, verbose, debug)

    logger.info("Loading config")
    cfg = datman.config.config(study=study)

    server = datman.xnat.get_server(cfg, url=server)
    username, password = datman.xnat.get_auth(username)
    xnat = datman.xnat.xnat(server, username, password)
    xnat_projects = cfg.get_xnat_projects(study)

    #Pair session with projects, otherwise collect all project sessions
    if session:
        xnat_project = xnat.find_session(session, xnat_projects)
        if not xnat_project:
            logger.error("Failed to find session: {} in XNAT. "
                         "Ensure it is named correctly with timepoint and repeat."
                         .format(session))
            return

        sessions = [(xnat_project, session)]

    else:
        sessions = collect_sessions(xnat_projects, cfg)

    logger.info("Processing {} sessions for study: {}"
                .format(len(sessions), study))

    parseable_sessions = [s for s in sessions if is_datman_parseable(s[1])]
    for proj, session in parseable_sessions:

        try:
            experiment = get_xnat_experiment(proj,session)
        except XnatException as e:
            logger.error('Failed to retrieve XNAT experiment for {},\
                    for reason {}'.format(session,e))
            continue

        if not db_ignore:
            add_session_to_dashboard(session, experiment, db_ignore)

        process_experiment(proj, session, experiment)



def configure_logger(study, quiet, verbose, debug):
    '''
    Configure logger object
    Arguments:
        study                       Study name
        quiet                       Quiet boolean flag
        verbose                     Verbose boolean flag
        debug                       Debug boolean flag

    By default sets log level to WARNING
    '''
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

    return

def is_datman_parseable(session):
    '''
    Returns True if parseable by datman.scanid.parse else False
    '''

    try:
        datman.scanid.parse(session)
    except datman.scanid.ParseException:
        logger.error('{} is an invalid session name, skipping!'.format(session))
        return False
    else:
        return True

def get_xnat_experiment(xnat_project, session_label):
    '''
    Get an experiment from XNAT 

    Arguments:
        xnat_project                    XNAT Project ID
        session_label                   DATMAN subject scanning session

    Output:
        experiment                      XNAT nested JSON table
    '''

    logger.info("Fetching experiment from {}".format(session_label))
    experiments = xnat.get_experiments(xnat_project, session_label)
    experiment_label = experiments[0]['label']

    if experiment_label != session_label:
        logger.warning("Experiment label: {} doesn't match session label: {}"
                       .format(experiment_label, session_label))

    experiment = xnat.get_experiment(xnat_project,
                                     session_label,
                                     experiment_label)
    return experiment

def add_session_to_dashboard(session_label,experiment,db_ignore):

    logger.debug("Adding session {} to dashboard".format(session_label))

    try:
        ident = datman.scanid.parse(session_label)
    except datman.scanid.ParseException:
        logger.error("Invalid session: {}. Skipping".format(session_label))
        return

    try:
        db_session = dashboard.get_session(ident, create=True)
    except dashboard.DashboardException as e:
        logger.error("Failed adding session {}. Reason: {}".format(
                session_label, e))
    else:
        set_date(db_session, experiment)


#TODO: Clean dis up
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

            if sub_id.session is None and not datman.scanid.is_phantom(session['label']):
                logger.error("Invalid ID {} in project {}. Reason: Not a "
                             "phantom, but missing series number"
                             .format(session['label'], project))
                continue

            sessions.append((project, session['label']))

    return sessions

def process_experiment(xnat_project, session_label, experiment):

    '''
    Process an XNAT experiment

    Arguments:
        xnat_project                    XNAT project ID
        session_label                   DATMAN subject scanning session
    '''

    logger.info("Processing session: {}".format(session_label))
    experiment_label = experiment['data_fields']['label']
    ident = datman.scanid.parse(session_label)

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

    #For each scan 
    for scan in scans['items']:
        series_id = scan['data_fields']['ID']
        scan_info = xnat.get_scan_info(xnat_project,
                                       session_label,
                                       experiment_label,
                                       series_id)

        if is_derived(scan_info) or not has_valid_dicoms(scan_info):
            continue

        file_stem, tag, multiecho = create_scan_name(exportinfo,
                                                     scan_info,
                                                     session_label)

        if len(file_stem) > 1:
            import pdb; pdb.set_trace()

        if not file_stem:
            continue

        for stem, t in zip(file_stem, tag):

            if wanted_tags and (t not in wanted_tags):
                continue

            if scan_in_blacklist(stem):
                continue

            if not db_ignore:
                add_scan_to_db(stem)

            try:
                export_formats = tags.get(t)['formats']
            except KeyError:
                logger.error("Export settings formats for tag: {} not found for "
                             "study: {}".format(tag, cfg.study_name))
                continue

            export_formats = [e for e in export_formats if not export_exists(ident, stem, e)]
            if not export_formats:
                logger.warn("Scan: {} has been processed. Skipping"
                            .format(stem))
                continue

            #Ideally this pulling should be a separate functionality
            get_scans(ident, xnat_project, session_label, experiment_label,
                      series_id, export_formats, stem, multiecho)

def add_scan_to_db(stem):
    logger.info('Adding scan {} to dashboard'.format(stem))
    try:
        dashboard.get_scan(stem, create=True)
    except datman.scanid.ParseException as e:
        logger.error('Failed adding scan {} to dashboard with error: {}'.format(file_stem,e))
    return

def scan_in_blacklist(stem):

    try:
        blacklist_entry = datman.utils.read_blacklist(scan=stem, config=cfg)
    except datman.scanid.ParseException as e:
        logger.error("Failed adding scan {} to dashboard with "
                "error: {}".format(file_stem, e))
        return True

    if blacklist_entry:
        logger.warn("Skipping export of {} due to blacklist entry '{}'".format(
                file_stem, blacklist_entry))
        return True

    return False

def get_exportinfo_patterns(scan_info):
    '''
    Make a dictionary containing a mapping from:
    ExportInfo Pattern type --> relevant value in scan_info using
    PATTERN_TO_SCANINFO dict
    '''

    descriptors = {}
    for k,v in PATTERN_TO_SCANINFO.iteritems():
        if not isinstance(v,list):
            v = [v]

        for i in v:
            try:
                descriptors.update({k : scan_info['data_fields'][i]})
            except KeyError:
                continue
            else:
                break
    
    return descriptors

def create_scan_name(exportinfo, scan_info, session_label):
    """Creates name suitable for a scan including the tags"""

    try:
        series_id = scan_info['data_fields']['ID']
    except TypeError as e:
        logger.error("{} failed. Cause: {}".format(session_label, e.message))

    #Get mappings from ExportInfo patterns --> scan_info fields
    descriptors = get_exportinfo_patterns(scan_info)
    if 'SeriesDescription' not in descriptors.keys():
        logger.error("Failed to get description for series: {} "
                     "from session: {}"
                     .format(series_id, session_label))
        return None, None, None

    mangled_descr = mangle(descriptors['SeriesDescription'])
    padded_series = series_id.zfill(2)
    multiecho = is_multiecho(scan_info)

    tag = guess_tag(exportinfo, scan_info, descriptors, multiecho)

    if tag is None:
        logger.warning("No matching export pattern for {}, "
                       "descr: {}. Skipping".format(session_label,
                                                    descriptors['SeriesDescription']))
        return None, None, None
    elif len(tag) > 1 and not multiecho:
        logger.error("Multiple export patterns match for {}, "
                     "descr: {}, tags: {}".format(session_label,
                                                  descriptors['SeriesDescription'], tag))
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
    try:
        if 'MultiEcho' in scan_info['children'][0]['items'][0]['data_fields']['name']:
            multiecho = True
    except KeyError:
        pass
    return multiecho

def guess_tag(exportinfo, scan_info, descriptors, multiecho):

    matches = []
    for tag, p in exportinfo.iteritems():

        description_regex = []
        valid_tag = True

        valid_descriptors = [k for k in p.keys() if k in descriptors.keys()]
        for k in valid_descriptors:

            description_regex = p[k]
            if isinstance(description_regex, list):
                description_regex = '|'.join(description_regex)

            if not re.search(description_regex, descriptors[k], re.IGNORECASE):
                valid_tag = False

        if valid_tag:
            matches.append(tag)


    if len(matches) == 1:
       return matches
    elif len(matches) == 2 and multiecho:
       return matches
    else: 
       return None


def khas_valid_dicoms(scan_info, series_id, session_label):
    '''
    Check whether session contains valid dicoms
    '''
    for scan_info_child in scan_info['children']:
        for scan_info_child_item in scan_info_child['items']:

            try:
                file_type = scan_info_child_item['data_fields']['content']
            except KeyError:
                continue
            else:
                if file_type == 'RAW': 
                    return True

        logger.warning("No RAW dicom data found in series: {} session: {}"
                       .format(series_id, session_label))
        return False

def has_valid_dicoms(scan_info):

    for scan_info_child in scan_info['children']:
        for scan_info_child_item in scan_info_child['items']:

            try:
                file_type = scan_info_child_item['data_fields']['content']
            except KeyError:
                continue
            else:
                if file_type == 'RAW': 
                    return True

    return False

def is_derived(scan_info):

    try:
        image_type = scan_info['data_fields']['parameters/imageType']
    except KeyError:
        return

    if 'DERIVED' in image_type:
        return True
    else:
        return False


def kis_derived(scan_info, series_id, session_label):
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

def export_exists(ident, file_stem, export_format):
    '''
    Returns True if export format exists in desired output directory
    '''

    outdir = os.path.join(cfg.get_path(export_format), ident.get_full_subjectid_with_timepoint())
    outfile = os.path.join(outdir,file_stem)
    exists = [os.path.isfile(p) for p in glob(outfile + '.*')]

    if exists:
        return True
    else:
        return False

#TODO: Simplify this function to deal with one at a time?
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
            ident = datman.scanid.parse(session_label)
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
