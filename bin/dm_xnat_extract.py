#!/usr/bin/env python
"""
Extracts data from xnat archive folders into a few well-known formats.

Usage:
    dm_xnat_extract.py [options] <study>
    dm_xnat_extract.py [options] <study> <session>

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
    -c --credfile FILE       File containing XNAT username and password. The username should be on the first line, and password on the next. Overrides the credfile in the project metadata
    -u --username USER       XNAT username. If specified then the credentials file is ignored and you are prompted for password.
    --dont-update-dashboard  Dont update the dashboard database

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
import logging
import sys
import getpass
import os
import glob
import tempfile
import zipfile
import fnmatch
import platform
import shutil
import hashlib

import dicom

from datman.docopt import docopt
import datman.config
import datman.xnat
import datman.utils
import datman.scanid
import datman.dashboard
import datman.exceptions

logger = logging.getLogger(os.path.basename(__file__))

xnat = None
cfg = None
dashboard = None
excluded_studies = ['testing']
DRYRUN = False
db_ignore = False   # if true dont update the dashboard db

def main():
    global xnat
    global cfg
    global excluded_studies
    global DRYRUN
    global dashboard

    arguments = docopt(__doc__)
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    quiet = arguments['--quiet']
    study = arguments['<study>']
    server = arguments['--server']
    credfile = arguments['--credfile']
    username = arguments['--username']
    session = arguments['<session>']
    db_ignore = arguments['--dont-update-dashboard']

    if arguments['--dry-run']:
        DRYRUN = True
        db_ignore = True

    # setup logging
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.WARN)
    logger.setLevel(logging.WARN)
    if quiet:
        logger.setLevel(logging.ERROR)
        ch.setLevel(logging.ERROR)
    if verbose:
        logger.setLevel(logging.INFO)
        ch.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)
        ch.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s - %(name)s - {study} - '
                                  '%(levelname)s - %(message)s'.format(
                                      study=study))
    ch.setFormatter(formatter)

    logger.addHandler(ch)
    logging.getLogger('datman.utils').addHandler(ch)

    # setup the config object
    logger.info('Loading config')

    cfg = datman.config.config(study=study)

    # setup the xnat object
    if not server:
        try:
            server = 'https://{}:{}'.format(cfg.get_key(['XNATSERVER']),
                                            cfg.get_key(['XNATPORT']))
        except KeyError:
            logger.error('Failed to get xnat server info for study:{}'
                         .format(study))
            return

    if username:
        password = getpass.getpass()
    else:
        #Moving away from storing credentials in text files
        """
        if not credfile:
            credfile = os.path.join(cfg.get_path('meta', study),
                                    'xnat-credentials')
        with open(credfile) as cf:
            lines = cf.readlines()
            username = lines[0].strip()
            password = lines[1].strip()
        """
        username = os.environ["XNAT_USER"]
        password = os.environ["XNAT_PASS"]

    xnat = datman.xnat.xnat(server, username, password)

    # setup the dashboard object
    if not db_ignore:
        try:
            dashboard = datman.dashboard.dashboard(study)
        except datman.dashboard.DashboardException as e:
            logger.error('Failed to initialise dashboard')

    # get the list of xnat projects linked to the datman study
    xnat_projects = cfg.get_xnat_projects(study)

    if session:
        # if session has been provided on the command line, identify which
        # project it is in
        try:
            xnat_project = xnat.find_session(session, xnat_projects)
        except datman.exceptions.XnatException as e:
            raise e

        if not xnat_project:
            logger.error('Failed to find session: {} in xnat.'
                         ' Ensure it is named correctly with timepoint and repeat.'
                         .format(session))
            return

        sessions = [(xnat_project, session)]
    else:
        sessions = collect_sessions(xnat_projects, cfg)

    logger.info('Found {} sessions for study: {}'
                .format(len(sessions), study))

    for session in sessions:
        process_session(session)

def collect_sessions(xnat_projects, config):
    sessions = []
    for project in xnat_projects:
        project_sessions = xnat.get_sessions(project)
        for session in project_sessions:
            try:
                sub_id = datman.utils.validate_subject_id(session['label'],
                        config)
            except RuntimeError as e:
                logger.error("Invalid ID {} in project {}. Reason: {}".format(
                        session['label'], project, str(e)))
                continue

            if not datman.scanid.is_phantom(session['label']) and sub_id.session == '':
                logger.error("Invalid ID {} in project {}. Reason: Not a "
                        "phantom, but missing series number".format(session['label'],
                        project))
                continue

            sessions.append((project, session['label']))
    return sessions

def process_session(session):
    xnat_project = session[0]
    session_label = session[1]

    logger.info('Processing session:{}'.
                format(session[1]))

    # check the session is valid on xnat
    try:
        xnat.get_session(xnat_project, session_label)
    except Exception as e:
        logger.error("Error while getting session {} from XNAT. "
                "Message: {}".format(session_label, e.message))
        return

    try:
        experiments = xnat.get_experiments(xnat_project, session_label)
    except Exception as e:
        logger.warning('Failed getting experiments for:{} in project:{}'
                       ' with reason:{}'
                       .format(session_label, xnat_project, e))
        return

    if len(experiments) > 1:
        logger.error('Found more than one experiment for session:{}'
                       'in study:{} Skipping'
                       .format(session_label, xnat_project))
        return

    if not experiments:
        logger.error('Session:{} in study:{} has no experiments'
                     .format(session_label, xnat_project))
        return


    experiment_label = experiments[0]['label']
    # sesssion_label should be a valid datman scanid
    try:
        ident = datman.scanid.parse(session_label)
    except datman.scanid.ParseException:
        logger.error('Invalid session:{}, skipping'.format(session_label))
        return

    # experiment_label should be the same as the session_label
    if not experiment_label == session_label:
        logger.warning('Experiment label:{} doesnt match session_label:{}'
                       .format(experiment_label,
                               session_label))

    try:
        experiment = xnat.get_experiment(xnat_project,
                                         session_label,
                                         experiment_label)
    except Exception as e:
        logger.error('Failed getting experiment for session:{} with reason'
                     .format(session_label, e))
        return

    if not experiment:
        logger.warning('No experiments found for session:{}'
                       .format(session_label))
        return

    if dashboard:
        logger.debug('Adding session:{} to db'.format(session_label))
        try:
            db_session_name = ident.get_full_subjectid_with_timepoint()
            db_session = dashboard.get_add_session(db_session_name,
                                                   date=experiment['data_fields']['date'],
                                                   create=True)
            if ident.session and int(ident.session) > 1:
                db_session.is_repeated = True
                db_session.repeat_count = int(ident.session)

        except datman.dashboard.DashboardException as e:
                logger.error('Failed adding session:{} to dashboard'
                             .format(session_label))


    for data in experiment['children']:
        if data['field'] == 'resources/resource':
            process_resources(xnat_project, session_label, experiment_label, data)
        elif data['field'] == 'scans/scan':
            process_scans(xnat_project, session_label, experiment_label, data)
        else:
            logger.warning('Unrecognised field type:{} for experiment:{}'
                           'in session:{} from study:{}'
                           .format(data['field'],
                                   experiment_label,
                                   session_label,
                                   xnat_project))

def create_scan_name(export_info, scan_info, session_label):
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
        logger.error('Failed to get description for series:'
                     '{} from session:{}'
                     .format(series_id, session_label))
        return None, None

    mangled_descr = datman.utils.mangle(description)
    series = series_id
    padded_series = series.zfill(2)
    tag = datman.utils.guess_tag(description, export_info)

    if not tag:
        logger.warn("No matching export pattern for {},"
                    " descr: {}. Skipping".format(session_label,
                                                  description))
        return None, None
    elif type(tag) is list:
        logger.error("Multiple export patterns match for {},"
                     " descr: {}, tags: {}".format(session_label,
                                                   description, tag))
        return None, None

    file_stem = "_".join([session_label, tag, padded_series, mangled_descr])
    return(file_stem, tag)


def process_resources(xnat_project, session_label, experiment_label, data):
    """Export any non-dicom resources from the xnat archive"""
    global cfg
    logger.info('Extracting {} resources from {}'
                .format(len(data), session_label))
    base_path = os.path.join(cfg.get_path('resources'),
                             session_label)
    if not os.path.isdir(base_path):
        logger.info('Creating dir:{}'.format(base_path))
        try:
            os.makedirs(base_path)
        except OSError:
            logger.error('Failed creating resources dir:{}.'.format(base_path))
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
            logger.error('Failed creating target folder:{}'
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
            logger.error('Failed getting resource:{} '
                         'for session:{} in project:{}'
                         .format(xnat_resource_id, session_label, e))
            continue

        for resource in resources:
            resource_path = os.path.join(target_path, resource['URI'])
            if os.path.isfile(resource_path):
                logger.debug('Resource:{} found for session:{}'
                             .format(resource['name'], session_label))
            else:
                logger.info('Resource:{} not found for session:{}'
                            .format(resource['name'], session_label))
                _ = get_resource(xnat_project,
                                 session_label,
                                 experiment_label,
                                 xnat_resource_id,
                                 resource['URI'],
                                 resource_path)

            check_duplicates(resource, base_path, target_path)



def check_duplicates(resource, base_path, target_path):
    """Checks to see if a resource file has duplicate copies on the file system
    backs up any duplicates found"""
    fname = os.path.basename(resource['URI'])
    target_file = os.path.join(target_path, resource['URI'])

    dups = []
    for root, dirs, files in os.walk(base_path):
        if 'BACKUPS' in root:
            continue
        if fname in files:
            dups.append(os.path.join(root, fname))
    # remove the target
    logger.debug('Original resource:{}'.format(target_file))
    # potentially throws a value error.
    # target file should always exist
    try:
        del dups[dups.index(target_file)]
    except:
        logger.error('Resource file: {} not found on file system.'
                     ' Did the download fail due to timeout?'.format(target_file))

    for dup in dups:
        try:
            backup_resource(base_path, dup)
        except (IOError, OSError) as e:
            logger.error('Failed backing up resource file:{} with excuse:{}'
                         .format(dup, str(e)))


def backup_resource(base_path, resource_file):
    backup_path = os.path.join(base_path, 'BACKUPS')
    rel_path = os.path.dirname(os.path.relpath(resource_file, base_path))
    target_dir = os.path.join(backup_path, rel_path)
    if not os.path.isdir(target_dir):
        try:
            os.makedirs(target_dir)
        except Exception as e:
            logger.debug('Failed creating backup target:{}'
                         .format(target_dir))
            raise e
    try:
        logger.debug('Moving {} to {}'.format(resource_file, target_dir))
        dst_file = os.path.join(target_dir, os.path.basename(resource_file))
        if os.path.isfile(dst_file):
            is_identical = check_files_are_identical([resource_file, dst_file])
            if is_identical:
                os.remove(resource_file)
            else:
                # This shouldn't happen, but one file may be corrupt.
                # rename the target file.
                fname, ext = os.path.splitext(dst_file)
                dst_file = '{}_copy{}'.format(fname, ext)
        else:
            os.rename(resource_file, dst_file)

    except Exception as e:
        logger.debug('Failed moving resource file:{} to {}'
                     .format(resource_file, target_dir))
        raise e

def check_files_are_identical(files):
    """Checks if files are identical
    Expects an iterable list of filenames"""
    hash1 = hashlib.sha256(open(files.pop(), 'rb').read()).digest()
    for f in files:
        hash2 = hashlib.sha256(open(f, 'rb').read()).digest()
        if hash2 != hash1:
            return False
    return True


def get_resource(xnat_project, xnat_session, xnat_experiment,
                 xnat_resource_group, xnat_resource_id, target_path):
    """Download a single resource file from xnat. Target path should be
    full path to store the file, including filename"""

    try:
        archive = xnat.get_resource(xnat_project,
                                    xnat_session,
                                    xnat_experiment,
                                    xnat_resource_group,
                                    xnat_resource_id,
                                    zipped=False)
    except Exception as e:
        logger.error('Failed downloading resource archive from:{} with reason:{}'
                     .format(xnat_session, e))
        return

    # check that the target path exists
    target_dir = os.path.split(target_path)[0]
    if not os.path.exists(target_dir):
        try:
            os.makedirs(target_dir)
        except OSError:
            logger.error('Failed to create directory:{}'.format(target_dir))
            return

    # copy the downloaded file to the target location
    try:
        source = archive[1]
        if not DRYRUN:
            shutil.copyfile(source, target_path)
    except:
        logger.error('Failed copying resource:{} to target:{}.'
                     .format(source, target_path))

    # finally delete the temporary archive
    try:
        os.remove(archive[1])
    except OSError:
        logger.error('Failed to remove temporary archive:{} on system:{}'
                     .format(archive, platform.node()))
    return(target_path)


def process_scans(xnat_project, session_label, experiment_label, scans):
    """Process a set of scans in an xnat experiment
    scanid is a valid datman.scanid object
    Scans is the json output from xnat query representing scans
    in an experiment"""
    logger.info('Processing scans in session:{}'
                .format(session_label))
    # setup the export functions for each format
    xporters = {
        "mnc": export_mnc_command,
        "nii": export_nii_command,
        "nrrd": export_nrrd_command,
        "dcm": export_dcm_command
    }
    ident = datman.scanid.parse(session_label)
    # load the export info from the site config files
    tags = cfg.get_tags(site=ident.site)
    exportinfo = tags.series_map

    if not exportinfo:
        logger.error('Failed to get exportinfo for study:{} at site:{}'
                     .format(cfg.study_name, ident.site))
        return

    # need to keep a list of scans added to dashboard
    # so we can delete any scans that no longer exist
    scans_added = []

    for scan in scans['items']:
        series_id = scan['data_fields']['ID']
        scan_info = xnat.get_scan_info(xnat_project,
                                       session_label,
                                       experiment_label,
                                       series_id)

        file_stem, tag = create_scan_name(exportinfo, scan_info, session_label)
        if not file_stem:
            continue

        # check if the series contains valid dicom files
        # this is to exclude the secondary dicoms generated by some scanners
        content_types = []
        for scan_info_child in scan_info['children']:
            for scan_info_child_item in scan_info_child['items']:
                if 'content' in scan_info_child_item['data_fields']:
                    content_types.append(scan_info_child_item['data_fields']['content'])

        if "RAW" not in content_types:
            logger.info("NO RAW dicom data found in series:{} session:{}"
                        .format(series_id, session_label))
            continue

        if dashboard:
            logger.info('Adding scan:{} to dashboard'.format(file_stem))
            try:
                dashboard.get_add_scan(file_stem, create=True)
                scans_added.append(file_stem)
            except datman.dashboard.DashboardException as e:
                logger.error('Failed adding scan:{} to dashboard with error:{}'
                             .format(file_stem, str(e)))

        # check the blacklist
        logger.debug('Checking blacklist for file:{}'.format(file_stem))

        blacklist = datman.utils.check_blacklist(file_stem,
                                                 study=cfg.study_name)
        if blacklist:
            logger.warning('Excluding scan:{} due to blacklist:{}'
                           .format(file_stem, blacklist))
            continue

        # first check if the scan has already been processed
        try:
            export_formats = tags.get(tag)['formats']
        except KeyError:
            logger.error('Export settings for tag:{} not found for study:{}'
                         .format(tag, cfg.study_name))
            continue
        if series_is_processed(ident, file_stem, export_formats):
            logger.info('Scan:{} has been processed, skipping'
                        .format(file_stem))
            continue

        logger.debug('Getting scan from xnat')
        # scan hasn't been completely processed, get it from xnat
        with datman.utils.make_temp_directory(prefix='dm_xnat_extract_') as temp_dir:
            src_dir = get_dicom_archive_from_xnat(xnat_project, session_label,
                    experiment_label, series_id, temp_dir)

            if not src_dir:
                logger.error('Failed getting series:{}, session:{} from xnat'
                             .format(series_id, session_label))
                continue

            for export_format in export_formats:
                target_base_dir = cfg.get_path(export_format)
                target_dir = os.path.join(target_base_dir,
                                          ident.get_full_subjectid_with_timepoint())
                try:
                    target_dir = datman.utils.define_folder(target_dir)
                except OSError as e:
                    logger.error('Failed creating target folder:{}'
                                 .format(target_dir))
                    continue

                try:
                    exporter = xporters[export_format]
                except KeyError:
                    logger.error("Export format {} not defined.".format(export_format))

                logger.info('Exporting scan {} to format {}'.format(file_stem,
                        export_format))
                try:
                    exporter(src_dir, target_dir, file_stem)
                except:
                    # The conversion functions dont really ever raise exceptions
                    # even when they fail so this is a bit useless
                    logger.error("An error happened exporting {} from scan: {} "
                            "in session: {}".format(export_format, series_id,
                            session_label), exc_info=True)

        logger.debug('Completed exports')

    # finally delete any extra scans that exist in the dashboard
    if dashboard:
        try:
            dashboard.delete_extra_scans(session_label, scans_added)
        except Exception as e:
            logger.error('Failed deleting extra scans from session:{} with excuse:{}'
                         .format(session_label, e))


def get_dicom_archive_from_xnat(xnat_project, session_label, experiment_label,
                                series, tempdir):
    """Downloads and extracts a dicom archive from xnat to a local temp folder
    Returns the path to the tempdir (for later cleanup) as well as the
    path to the .dcm files inside the tempdir
    """
    # make a copy of the dicom files in a local directory
    logger.debug('Downloading dicoms for:{}, series:{}.'
                 .format(session_label, series))
    try:
        dicom_archive = xnat.get_dicom(xnat_project,
                                       session_label,
                                       experiment_label,
                                       series)
    except Exception as e:
        logger.error('Failed to download dicom archive for:{}, series:{}'
                     .format(session_label, series))
        return None

    logger.debug('Unpacking archive')

    try:
        with zipfile.ZipFile(dicom_archive[1], 'r') as myzip:
            myzip.extractall(tempdir)
    except:
        logger.error('An error occurred unpacking dicom archive for:{}'
                     ' skipping'.format(session_label))
        os.remove(dicom_archive[1])
        return None

    logger.debug('Deleting archive file')
    os.remove(dicom_archive[1])
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
        logger.warning('There were no valid dicom files in xnat session:{}, series:{}'
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


def get_resource_archive_from_xnat(xnat_project, session, resourceid):
    """Downloads and extracts a resource archive from xnat
    to a local temp file
    Returns the path to the tempfile (for later cleanup)"""

    logger.debug('Downloadind resources for:{}, series:{}.'
                 .format(session, resourceid))
    try:
        resource_archive = xnat.get_resource(xnat_project,
                                             session,
                                             session,
                                             resourceid)
    except Exception as e:
        return None
    return(resource_archive)


def series_is_processed(ident, file_stem, export_formats):
    """returns true if exported files exist for all specified formats"""
    global cfg

    for f in export_formats:
        outdir = os.path.join(cfg.get_path(f),
                              ident.get_full_subjectid_with_timepoint())
        outfile = os.path.join(outdir, file_stem)
        # need to use wildcards here as dont really know what the
        # file extensions will be
        exists = [os.path.isfile(p) for p in glob.glob(outfile + '.*')]
        if not exists:
            return False
        if not all(exists):
            return False
    return True


def check_create_dir(target):
    """Checks to see if a directory exists, creates if not"""
    if not os.path.isdir(target):
        logger.info('Creating dir:{}'.format(target))
        try:
            os.makedirs(target)
        except OSError as e:
            logger.error('Failed creating dir:{}.'.format(target))
            raise e

def export_mnc_command(seriesdir, outputdir, stem):
    """
    Converts a DICOM series to MINC format
    """
    outputfile = os.path.join(outputdir, stem) + ".mnc"

    try:
        check_create_dir(outputdir)
    except:
        return

    if os.path.exists(outputfile):
        logger.warn("{}: output {} exists. skipping."
                    .format(seriesdir, outputfile))
        return

    logger.debug("Exporting series {} to {}"
                 .format(seriesdir, outputfile))
    cmd = 'dcm2mnc -fname {} -dname "" {}/* {}'.format(stem,
                                                       seriesdir,
                                                       outputdir)
    datman.utils.run(cmd, DRYRUN)


def export_nii_command(seriesdir, outputdir, stem):
    """
    Converts a DICOM series to NifTi format
    """
    outputfile = os.path.join(outputdir, stem) + ".nii.gz"
    try:
        check_create_dir(outputdir)
    except:
        return
    if os.path.exists(outputfile):
        logger.warn("{}: output {} exists. skipping."
                    .format(seriesdir, outputfile))
        return

    logger.debug("Exporting series {} to {}".format(seriesdir, outputfile))

    # convert into tempdir
    with datman.utils.make_temp_directory(prefix="dm_xnat_extract_") as tmpdir:
        datman.utils.run('dcm2niix -z y -b y -o {} {}'
                         .format(tmpdir, seriesdir), DRYRUN)

        # move nii and accompanying files (BIDS, dirs, etc) from tempdir/ to nii/
        for f in glob.glob("{}/*".format(tmpdir)):
            bn = os.path.basename(f)
            ext = datman.utils.get_extension(f)
            return_code, _ = datman.utils.run("mv {} {}/{}{}"
                                 .format(f, outputdir, stem, ext), DRYRUN)
            if return_code:
                logger.error("Moving dcm2niix output {} to {} has failed.".format(
                        f, outputdir))
                continue

def export_nrrd_command(seriesdir, outputdir, stem):
    """
    Converts a DICOM series to NRRD format
    """
    outputfile = os.path.join(outputdir, stem) + ".nrrd"
    try:
        check_create_dir(outputdir)
    except:
        return
    if os.path.exists(outputfile):
        logger.warn("{}: output {} exists. skipping."
                    .format(seriesdir, outputfile))
        return

    logger.debug("Exporting series {} to {}".format(seriesdir, outputfile))

    cmd = 'DWIConvert -i {} --conversionMode DicomToNrrd -o {}.nrrd' \
          ' --outputDirectory {}'.format(seriesdir, stem, outputdir)

    datman.utils.run(cmd, DRYRUN)


def export_dcm_command(seriesdir, outputdir, stem):
    """
    Copies a single DICOM from the series.
    """
    outputfile = os.path.join(outputdir, stem) + ".dcm"
    try:
        check_create_dir(outputdir)
    except:
        return
    if os.path.exists(outputfile):
        logger.warn("{}: output {} exists. skipping."
                    .format(seriesdir, outputfile))
        return

    dcmfile = None
    for path in glob.glob(seriesdir + '/*'):
        try:
            dicom.read_file(path)
            dcmfile = path
            break
        except dicom.filereader.InvalidDicomError as e:
            pass

    if not dcmfile:
        logger.error("No dicom files found in {}".format(seriesdir))
        return

    logger.debug("Exporting a dcm file from {} to {}"
                 .format(seriesdir, outputfile))
    cmd = 'cp {} {}'.format(dcmfile, outputfile)

    datman.utils.run(cmd, DRYRUN)

if __name__ == '__main__':
    main()
