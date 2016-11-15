#!/usr/bin/env python
"""
Extracts data from xnat archive folders into a few well-known formats.

Usage:
    xnat-extract.py [options] <study>
    xnat-extract.py [options] <study> <session>

Arguments:
    <study>            Nickname of the study to process
    <session>          Fullname of the session to process

Options:
    --blacklist FILE    Table listing series to ignore
                            override the default metadata/blacklist.csv
    -v --verbose        Show intermediate steps
    -d --debug          Show debug messages
    -q --quiet          Show minimal output
    -n --dry-run        Do nothing
    --server URL          XNAT server to connect to,
                            overrides the server defined
                            in the site config file.

    -c --credfile FILE    File containing XNAT username and password. The
                          username should be on the first line, and password
                          on the next. Overrides the credfile in the project
                          metadata

    -u --username USER    XNAT username. If specified then the credentials
                          file is ignored and you are prompted for password.

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
from docopt import docopt
import logging
import sys
import datman.config
import datman.xnat
import datman.utils
import datman.dashboard
import getpass
import os
import glob
import tempfile
import zipfile
import fnmatch
import platform
import shutil
import dicom

logger = logging.getLogger(__file__)
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

    # setup logging
    logging.basicConfig()
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

    formatter = logging.Formatter('%(asctime)s - %(name)s - '
                                  '%(levelname)s - %(message)s')
    ch.setFormatter(formatter)

    logger.addHandler(ch)

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
        if not credfile:
            credfile = os.path.join(cfg.get_path('meta', study),
                                    'xnat-credentials')
        with open(credfile) as cf:
            lines = cf.readlines()
            username = lines[0].strip()
            password = lines[1].strip()

    xnat = datman.xnat.xnat(server, username, password)

    # setup the dashboard object
    if not db_ignore:
        try:
            dashboard = datman.dashboard.dashboard(study)
        except datman.dashboard.DashboardException as e:
            logger.error('Failed to initialise dashboard')

    # get the list of xnat projects linked to the datman study
    xnat_projects = cfg.get_xnat_projects(study)
    sessions = []
    if session:
        # if session has been provided on the command line, identify which
        # project it is in
        xnat_project = xnat.find_session(session, xnat_projects)
        if not xnat_projects:
            logger.error('Failed to find session:{} in xnat.'
                         .format(xnat_projects))
        sessions.append((xnat_project, session))
    else:
        for project in xnat_projects:
            project_sessions = xnat.get_sessions(project)
            for session in project_sessions:
                sessions.append((project, session['label']))

        logger.debug('Found {} sessions for study:'.format(len(sessions),
                                                           study))

    for session in sessions:
        process_session(session)


def process_session(session):
    global xnat

    xnat_project = session[0]
    session_label = session[1]

    # check the session is valid on xnat
    if not xnat.get_session(xnat_project, session_label):
        logger.warning('Invalid session:{} in xnat project:{}'
                       .format(session_label, xnat_project))
        return

    if len(xnat.get_experiments(xnat_project, session_label)) > 1:
        logger.warning('Found more than one experiment for session:{}'
                       'in study:{} Only processing first'
                       .format(session_label, xnat_project))

    # sesssion_label should be a valid datman scanid
    try:
        ident = datman.scanid.parse(session_label)
    except datman.scanid.ParseException:
        logger.error('Invalid session:{}, skipping'.format(session_label))
        return

    experiment = xnat.get_experiment(xnat_project,
                                     session_label,
                                     session_label)
    if not experiment:
        logger.warning('No experiments found for session:{}'
                       .format(session_label))
        return

    # experiment_label should be the same as the session_label
    if not experiment['data_fields']['label'] == session_label:
        logger.warning('Experiment label:{} doesnt match session_label:{}'
                       .format(experiment['data_fields']['label'],
                               session_label))
        return

    if dashboard:
        logger.debug('Adding session:{} to db'.format(session_label))
        try:
            dashboard.get_add_session(ident.get_full_subjectid_with_timepoint(),
                                      date=experiment['data_fields']['date'],
                                      create=True)
        except datman.dashboard.DashboardException as e:
                logger.error('Failed adding session:{} to dashboard'
                             .format(session_label))

    for data in experiment['children']:
        if data['field'] == 'resources/resource':
            process_resources(xnat_project, ident, data)
        elif data['field'] == 'scans/scan':
            process_scans(xnat_project, ident, data)
        else:
            logger.warning('Unrecognised field type:{} for experiment:{}'
                           'in session:{} from study:{}'
                           .format(data['field'],
                                   session_label,
                                   session_label,
                                   xnat_project))


def check_resources_exist(resource_list, target_dir):
    """Check if non-dicom resource files have been downloaded from xnat"""
    exists = [os.path.isfile(os.path.join(target_dir, resource['name']))
              for resource in resource_list]


def process_resources(xnat_project, scanid, data):
    """Export any non-dicom resources from the xnat archive"""
    global cfg
    logger.info('Extracting {} resources from {}'
                .format(len(data), str(scanid)))
    base_path = os.path.join(cfg.get_path('resources'),
                             scanid.get_full_subjectid_with_timepoint())

    for item in data['items']:
        try:
            data_type = item['data_fields']['label']
        except KeyError:
            data_type = 'misc'

        target_path = os.path.join(base_path, data_type)

        try:
            target_path = datman.utils.define_folder(target_path)
        except OSError:
            logger.error('Failed creating target folder:{}'
                         .format(target_path))
            continue

        xnat_resource_id = item['data_fields']['xnat_abstractresource_id']

        resources = xnat.get_resource_list(xnat_project,
                                           str(scanid),
                                           str(scanid),
                                           xnat_resource_id)

        for resource in resources:
            if os.path.isfile(os.path.join(target_path, resource['name'])):
                logger.debug('Resource:{} found for session:{}'
                             .format(resource['name'], str(scanid)))
            else:
                logger.info('Resource:{} not found for session:{}'
                            .format(resource['name'], str(scanid)))
                get_resource(xnat_project,
                             str(scanid),
                             xnat_resource_id,
                             resource['ID'],
                             target_path)


def get_resource(xnat_project, xnat_session, xnat_resource_group,
                 xnat_resource_id, target_path):

    archive = xnat.get_resource(xnat_project,
                                xnat_session,
                                xnat_session,
                                xnat_resource_group,
                                xnat_resource_id)

    # extract the files from the archive, ignoring the filestructure
    try:
        with zipfile.ZipFile(archive[1]) as zip_file:
            for member in zip_file.namelist():
                filename = os.path.basename(member)
                if not filename:
                    continue
                if DRYRUN:
                    continue
                source = zip_file.open(member)
                target = file(os.path.join(target_path, filename), 'wb')
                with source, target:
                    shutil.copyfileobj(source, target)
    except:
        logger.error('Failed extracting resources archive:{}'
                     .format(xnat_session), exc_info=True)

    # finally delete the temporary archive
    try:
        os.remove(archive[1])
    except OSError:
        logger.error('Failed to remove temporary archive:{} on system:{}'
                     .format(archive, platform.node()))


def process_scans(xnat_project, scanid, scans):
    """Process a set of scans in an xnat experiment
    scanid is a valid datman.scanid object
    Scans is the json output from xnat query representing scans
    in an experiment"""
    global cfg

    # setup the export functions for each format
    xporters = {
        "mnc": export_mnc_command,
        "nii": export_nii_command,
        "nrrd": export_nrrd_command,
        "dcm": export_dcm_command,
    }

    # load the export info from the site config files
    exportinfo = cfg.get_exportinfo(site=scanid.site)
    if not exportinfo:
        logger.error('Failed to get exportinfo for study:{} at site:{}'
                     .format(cfg.study_name, scanid.site))
        return

    for scan in scans['items']:
        description = scan['data_fields']['series_description']
        mangled_descr = datman.utils.mangle(description)
        series = scan['data_fields']['ID']
        padded_series = series.zfill(2)
        tag = datman.utils.guess_tag(description, exportinfo)

        if not tag:
            logger.warn("No matching export pattern for {},"
                        " descr: {}. Skipping".format(str(scanid),
                                                      description))
            continue
        elif type(tag) is list:
            logger.error("Multiple export patterns match for {},"
                         " descr: {}, tags: {}".format(str(scanid),
                                                       description, tag))
            continue

        file_stem = "_".join([str(scanid), tag, padded_series, mangled_descr])

        if dashboard:
            logger.info('Adding scan:{} to dashboard'.format(file_stem))
            try:
                dashboard.get_add_scan(file_stem, create=True)
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
            export_formats = cfg.get_key(['ExportSettings', tag])
        except KeyError:
            logger.error('Export settings for tag:{} not found for study:{}'
                         .format(tag, cfg.study_name))
            continue
        if check_if_dicom_is_processed(scanid,
                                       file_stem,
                                       export_formats.keys()):
            logger.warn('Scan:{} has been processed, skipping'
                        .format(file_stem))
            continue

        logger.debug('Getting scan from xnat')
        tempdir, src_dir = get_dicom_archive_from_xnat(xnat_project,
                                                       str(scanid),
                                                       series)
        if not src_dir:
            logger.error('Failed getting scan from xnat')
            continue

        try:
            for export_format in export_formats.keys():
                target_base_dir = cfg.get_path(export_format)
                target_dir = os.path.join(target_base_dir,
                                          scanid.get_full_subjectid_with_timepoint())
                try:
                    target_dir = datman.utils.define_folder(target_dir)
                except OSError as e:
                    logger.error('Failed creating target folder:{}'
                                 .format(target_dir))
                    raise(e)

                exporter = xporters[export_format]
                exporter(src_dir, target_dir, file_stem)
        except:
            logger.error('An error happened exporting {} from scan:{}'
                         .format(export_format, str(scanid)), exc_info=True)

        logger.debug('Completed exports')
        try:
            shutil.rmtree(tempdir)
        except shutil.Error:
            logger.error('Failed to delete tempdir:{} on system:{}'
                         .format(tempdir, platform.node()))


def get_dicom_archive_from_xnat(xnat_project, session, series):
    """Downloads and extracts a dicom archive from xnat to a local temp folder
    Returns the path to the tempdir (for later cleanup) as well as the
    path to the .dcm files inside the tempdir
    """
    global xnat
    # going to create a local directory and make a copy of the
    # dicom files there
    tempdir = tempfile.mkdtemp(prefix='dm2_xnat_extract_')
    logger.debug('Downloading dicoms for:{}, series:{}.'
                 .format(session, series))
    dicom_archive = xnat.get_dicom(xnat_project,
                                   session,
                                   session,
                                   series)
    if not dicom_archive:
        logger.error('Failed to download dicom archive for:{}, series:{}'
                     .format(session, series))
        return

    logger.debug('Unpacking archive')

    with zipfile.ZipFile(dicom_archive[1], 'r') as myzip:
        try:
            myzip.extractall(tempdir)
        except:
            logger.error('An error occured unpaking dicom archive for:{}'
                         ' skipping')
            os.remove(dicom_archive[1])
            return

    logger.debug('Deleting archive file')
    os.remove(dicom_archive[1])
    # get the root dir for the extracted files
    archive_files = []
    for root, dirname, filenames in os.walk(tempdir):
        for filename in fnmatch.filter(filenames, '*.[Dd][Cc][Mm]'):
            archive_files.append(os.path.join(root, filename))
    base_dir = os.path.dirname(archive_files[0])
    return(tempdir, base_dir)


def get_resource_archive_from_xnat(xnat_project, session, resourceid):
    """Downloads and extracts a resource archive from xnat
    to a local temp file
    Returns the path to the tempfile (for later cleanup)"""
    global xnat

    logger.debug('Downloadind resources for:{}, series:{}.'
                 .format(session, resourceid))

    resource_archive = xnat.get_resource(xnat_project,
                                         session,
                                         session,
                                         resourceid)
    return(resource_archive)


def check_if_dicom_is_processed(scanid, file_stem, export_formats):
    """returns true if exported files exist for all specified formats"""
    global cfg

    for f in export_formats:
        outdir = os.path.join(cfg.get_path(f),
                              scanid.get_full_subjectid_with_timepoint())
        outfile = os.path.join(outdir, file_stem)
        # need to use wildcards here as dont really know what the
        # file extensions will be
        exists = [os.path.isfile(p) for p in glob.glob(outfile + '.*')]
        if not exists:
            return
        if not all(exists):
            return
    return True


def export_mnc_command(seriesdir, outputdir, stem):
    """
    Converts a DICOM series to MINC format
    """
    outputfile = os.path.join(outputdir, stem) + ".mnc"

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

    if os.path.exists(outputfile):
        logger.warn("{}: output {} exists. skipping."
                    .format(seriesdir, outputfile))
        return

    logger.debug("Exporting series {} to {}".format(seriesdir, outputfile))

    # convert into tempdir
    tmpdir = tempfile.mkdtemp()
    datman.utils.run('dcm2nii -x n -g y -o {} {}'
                     .format(tmpdir, seriesdir), DRYRUN)

    # move nii in tempdir to proper location
    for f in glob.glob("{}/*".format(tmpdir)):
        bn = os.path.basename(f)
        ext = datman.utils.get_extension(f)
        if bn.startswith("o") or bn.startswith("co"):
            continue
        else:
            datman.utils.run("mv {} {}/{}{}"
                             .format(f, outputdir, stem, ext), DRYRUN)
    shutil.rmtree(tmpdir)


def export_nrrd_command(seriesdir, outputdir, stem):
    """
    Converts a DICOM series to NRRD format
    """
    outputfile = os.path.join(outputdir, stem) + ".nrrd"

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


def parse_exportinfo(exportinfo):
    """
    Takes the dictionary structure from project_settings.yaml and returns a
    pattern:tag dictionary.

    If multiple patterns are specified in the configuration file, these are
    joined with an '|' (OR) symbol.
    """
    tags = exportinfo.keys()
    patterns = [tagtype["Pattern"] for tagtype in exportinfo.values()]

    regex = []
    for pattern in patterns:
        if type(pattern) == list:
            regex.append(("|").join(pattern))
        else:
            regex.append(pattern)

    tagmap = dict(zip(regex, tags))

    return tagmap


if __name__ == '__main__':
    main()
