#!/usr/bin/env python
"""
Extracts data from XNAT archive folders into a few well-known formats.

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
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
import glob
import logging
import os
import platform
import shutil
import sys

import datman.config
import datman.exceptions
import datman.exporters
import datman.importers
import datman.scan
import datman.scanid
import datman.xnat
from datman.utils import (validate_subject_id, define_folder,
                          make_temp_directory, read_blacklist)

logger = logging.getLogger(os.path.basename(__file__))


def main():
    args, tool_opts = read_args()

    log_level = get_log_level(args)
    configure_logging(args.study, log_level)

    if args.use_dcm2bids and not datman.exporters.DCM2BIDS_FOUND:
        logger.error("Failed to locate Dcm2Bids. Ensure that "
                     "Dcm2Bids is installed when using the "
                     "--use-dcm2bids flag.  Exiting conversion")
        return

    config = datman.config.config(study=args.study)
    if args.use_dcm2bids:
        bids_opts = datman.exporters.BidsOptions(
            config,
            keep_dcm=args.keep_dcm,
            force_dcm2niix=args.force_dcm2niix,
            clobber=args.clobber,
            dcm2bids_config=args.dcm_config,
            bids_out=args.bids_out,
            log_level=log_level,
            refresh=args.refresh,
            extra_opts=tool_opts.get('--dcm2bids-', [])
        )
    else:
        bids_opts = None

    sessions = get_sessions(config, args)

    logger.info(f"Found {len(sessions)} sessions for study {args.study}")

    for xnat, importer in sessions:
        session = datman.scan.Scan(importer.ident, config,
                                   bids_root=args.bids_out)

        if importer.resource_files:
            export_resources(session.resource_path, xnat, importer,
                             dry_run=args.dry_run)

        if importer.scans:
            export_scans(config, xnat, importer, session,
                         bids_opts=bids_opts, dry_run=args.dry_run,
                         ignore_db=args.dont_update_dashboard,
                         wanted_tags=args.tag)


def read_args():
    """Configure the ArgumentParser.
    """
    def _is_dir(path, parser):
        """Ensure a given directory exists."""
        if path is None or not os.path.isdir(path):
            raise parser.error(f"Directory does not exist: <{path}>")
        return os.path.abspath(path)

    def _is_file(path, parser):
        """Ensure a given file exists."""
        if path is None or not os.path.isfile(path):
            raise parser.error(f"File does not exist: <{path}>")
        return os.path.abspath(path)

    parser = ArgumentParser(
        description="Extracts data from XNAT archive folders into a "
                    "few well-known formats.",
        formatter_class=ArgumentDefaultsHelpFormatter,
    )

    g_main = parser.add_argument_group(
        "Options for choosing data to extract"
    )
    g_main.add_argument(
        "study",
        action="store",
        help="Nickname of the study to process",
    )
    g_main.add_argument(
        "experiment",
        action="store",
        nargs='?',
        help="Full ID of the experiment to process",
    )
    g_main.add_argument(
        "--blacklist", action="store", metavar="FILE",
        type=lambda x: _is_file(x, parser),
        help="Table listing series to ignore override the "
             "default metadata/blacklist.csv"
    )
    g_main.add_argument(
        "--server", action="store", metavar="URL",
        help="XNAT server to connect to, overrides the server "
             "defined in the configuration files."
    )
    g_main.add_argument(
        "-u", "--username", action="store", metavar="USER",
        help="XNAT username. If specified then the environment "
             "variables (or any credential files) are ignored "
             "and you are prompted for a password. Note that if "
             "multiple servers are configured for a study the "
             "login used should be valid for all servers.."
    )
    g_main.add_argument(
        "--dont-update-dashboard", action="store_true", default=False,
        help="Dont update the dashboard database"
    )
    g_main.add_argument(
        "-t",
        "--tag",
        action="append",
        metavar="tag,...",
        nargs="?",
        help="A scan tag to download. Can repeat option for multiple tags."
    )
    g_main.add_argument(
        "--use-dcm2bids", action="store_true", default=False,
        help="Pull xnat data and convert to bids using dcm2bids"
    )
    g_main.add_argument(
        "--use-zips", action="store", metavar="ZIP_DIR",
        nargs="?", default="USE_XNAT",
        help="A directory of zip files to use instead of pulling from XNAT. "
             "If not provided the study's 'dicom' dir will be used instead."
    )

    g_dcm2bids = parser.add_argument_group(
        "Options for using dcm2bids. Note that you can feed options directly "
        "to dcm2bids by prefixing any with '--dcm2bids-'. For example, the "
        "dcm2bids option 'auto-extract-entities' can be used with "
        "'--dcm2bids-auto-extract-entities'. Note that the spelling and case "
        "must match exactly what dcm2bids expects to receive and must exist "
        "for the version of dcm2bids in use"
    )
    g_dcm2bids.add_argument(
        "--bids-out", action="store", metavar="DIR",
        type=lambda x: _is_dir(x, parser),
        help="Path to output bids folder"
    )
    g_dcm2bids.add_argument(
        "--dcm-config", action="store", metavar="FILE",
        type=lambda x: _is_file(x, parser),
        help="Path to dcm2bids config file"
    )
    g_dcm2bids.add_argument(
        "--keep-dcm", action="store_true", default=False,
        help="Keep raw dcm pulled from xnat in temp folder"
    )
    g_dcm2bids.add_argument(
        "--force-dcm2niix", action="store_true", default=False,
        help="Force dcm2niix to be rerun in dcm2bids"
    )
    g_dcm2bids.add_argument(
        "--clobber", action="store_true", default=False,
        help="Clobber previous bids data"
    )
    g_dcm2bids.add_argument(
        "--refresh", action="store_true", default=False,
        help="Refresh previously exported bids data by re-running against an "
             "existing tmp folder in the bids output directory. Useful if the "
             "contents of the configuration file changes."
    )

    g_perfm = parser.add_argument_group("Options for logging and debugging")
    g_perfm.add_argument(
        "-d", "--debug", action="store_true",
        default=False,
        help="Show debug messages"
    )
    g_perfm.add_argument(
        "-q", "--quiet", action="store_true",
        default=False,
        help="Minimal logging"
    )
    g_perfm.add_argument(
        "-v", "--verbose", action="store_true",
        default=False,
        help="Maximal logging"
    )
    g_perfm.add_argument(
        "-n", "--dry-run", action="store_true",
        default=False,
        help="Do nothing"
    )

    tool_opts, clean_args = parse_tool_opts(sys.argv[1:], ['--dcm2bids-'])
    args = parser.parse_args(clean_args)

    bids_opts = [args.keep_dcm, args.dcm_config, args.bids_out,
                 args.force_dcm2niix, args.clobber, args.refresh]
    if not args.use_dcm2bids and (any(bids_opts) or
                                  '--dcm2bids-' in tool_opts):
        parser.error("dcm2bids configuration requires --use-dcm2bids")

    return args, tool_opts


def parse_tool_opts(
        args: list[str],
        accepted_prefixes: list[str]
    ) -> tuple[dict[str, list[str]], list[str]]:
    """Collect user options intended for wrapped tools.

    Args:
        args (list[str]): A list of string inputs to process.
        accepted_prefixes (list[str]): a list of prefixes for options that
            will be accepted.

    Returns:
        tuple[dict[str, list[str]], list[str]]:
            A tuple containing:
                - A dictionary mapping an accepted prefix and arguments
                    associated with it.
                - A list of all arguments the user provided that do not match
                    an accepted prefix.
    """
    extra_opts = {}
    clean_args = []
    for arg in args:
        found = False
        for prefix in accepted_prefixes:
            if arg.startswith(prefix):
                found = True
                opt = arg[len(prefix):]
                # _, opt = arg.split(prefix)
                extra_opts.setdefault(prefix, []).append(opt)
        if not found:
            clean_args.append(arg)
    return extra_opts, clean_args


def get_log_level(args):
    """Return a string representing the log level, based on user input.

    A string representation of the log level is needed to please dcm2bids :)
    """
    if args.quiet:
        return "ERROR"

    if args.verbose:
        return "INFO"

    if args.debug:
        return "DEBUG"

    return "WARNING"


def configure_logging(study, log_level):
    """Configure the logging for this run.

    Args:
        study (:obj:`str`): The name of the study being exported.
        log_level (:obj:`str`): The log level to use.
    """
    ch = logging.StreamHandler(sys.stdout)

    log_level = getattr(logging, log_level)
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
    logging.getLogger('datman.exporters').addHandler(ch)
    logging.getLogger('datman.importers').addHandler(ch)


def get_sessions(config, args):
    """Get all scan sessions to be exported.

    Args:
        config (:obj:`datman.config.config`): The datman configuration.
        args (:obj:`argparse.ArgumentParser`): The argument parser for the
            user's input arguments.

    Returns:
        list[(None|datman.xnat.XNAT, datman.importers.SessionImporter)]:
            a list of tuples containing the XNAT connection to use (if needed
            during export) and a SessionImporter. If no sessions are found,
            will return an empty list.
    """
    if args.use_zips != "USE_XNAT":
        return collect_zips(config, args)

    auth = datman.xnat.get_auth(args.username) if args.username else None

    if args.experiment:
        return collect_experiment(
            config, args.experiment, args.study, auth=auth, url=args.server)

    return collect_all_experiments(config, auth=auth, url=args.server)


def collect_zips(config, args):
    """Locate all usable zip files.

    Args:
        config (:obj:`datman.config.config`): The datman configuration.
        args (:obj:argparse.ArgumentParser): The argument parser for the
            user's command line inputs.

    Returns:
        list[(None, datman.importers.ZipImporter)]: A list of tuples each
            containing None (for compatibility with exporting XNATExperiments)
            and a ZipImporter. Will return an empty list if no zip files are
            found.
    """
    if args.use_zips is None:
        zip_folder = config.get_path("dicom")
    else:
        zip_folder = args.use_zips

    if not os.path.exists(zip_folder):
        logger.error(f"Zip file directory not found: {zip_folder}")
        return []

    if args.experiment:
        ident = get_identifier(config, args.experiment)
        if not ident:
            logger.error(f"Invalid session ID {args.experiment}.")
            return []

        zip_path = os.path.join(zip_folder, str(ident) + ".zip")
        if not os.path.exists(zip_path):
            logger.error(f"Zip file not found: {zip_path}")
            return []

        return [(None, datman.importers.ZipImporter(ident, zip_path))]

    zip_files = []
    for zip_path in glob.glob(os.path.join(zip_folder, "*.zip")):
        sess_name = os.path.basename(zip_path).replace(".zip", "")
        ident = get_identifier(config, sess_name)
        if not ident:
            logger.error(
                f"Ignoring invalid zip file name in dicom dir: {sess_name}")
            continue
        zip_files.append(
            (None, datman.importers.ZipImporter(ident, zip_path))
        )

    return zip_files


def collect_experiment(config, experiment_id, study, url=None, auth=None):
    """Get a single XNAT experiment.

    Args:
        config (:obj:`datman.config.config`): A datman configuration object.
        experiment_id (:obj:`str`): An XNAT experiment ID.
        study (:obj:`str`): A valid study ID.
        url (:obj:`str`, optional): The XNAT url to use. If not given, it
            will be retrieved from the configuration files.
        auth (:obj:`tuple`, optional): A tuple containing the username and
            password to use when accessing the XNAT server. If not given,
            the XNAT_USER and XNAT_PASS environment variables will be used.

    Return:
        list[(datman.xnat.XNAT, datman.importers.XNATExperiment)]:
            a list with a single tuple containing the xnat connection to use
            and the experiment importer. If not found, an empty list will be
            given.
    """
    ident = get_identifier(config, experiment_id)
    xnat = datman.xnat.get_connection(
        config, site=ident.site, url=url, auth=auth)
    xnat_project = xnat.find_project(
        ident.get_xnat_subject_id(),
        config.get_xnat_projects(study)
    )

    if not xnat_project:
        logger.error(f"Failed to find experiment {experiment_id} on XNAT. "
                     f"Ensure it matches an existing experiment ID.")
        return []

    experiment = get_xnat_experiment(xnat, xnat_project, ident)
    if not experiment:
        return []

    return [(xnat, experiment)]


def get_identifier(config, subid):
    """Get a valid identifier for a given ID.

    Args:
        config (:obj:`datman.config.config`): A datman configuration object
            for a study.
        subid (:obj:`str`): A valid identifier in one of datman's accepted name
            conventions.

    Returns:
        datman.scanid.Identifier: A datman Identifier for the given subid.
    """
    ident = validate_subject_id(subid, config)

    try:
        convention = config.get_key("XnatConvention", site=ident.site)
    except datman.config.UndefinedSetting:
        convention = "DATMAN"

    if convention == "KCNI":
        try:
            settings = config.get_key("IdMap")
        except datman.config.UndefinedSetting:
            settings = None
        ident = datman.scanid.get_kcni_identifier(ident, settings)

    return ident


def collect_all_experiments(config, auth=None, url=None):
    """Retrieve all XNAT experiment objects for a single study.

    Args:
        config (:obj:`datman.config.config`): A datman configuration object
            for the current study.
        auth (:obj:`tuple`, optional): A tuple containing an XNAT username and
            password. If not provided, the XNAT_USER and XNAT_PASS variables
            will be used. Defaults to None.
        url (:obj:`str`): The URL for the XNAT server.

    Returns:
        list[datman.importers.XNATExperiment]: A list of XNATExperiment
            importers for all experiments belonging to the config's study.
    """
    experiments = []
    server_cache = {}

    for project, sites in get_projects(config).items():
        for site in sites:
            xnat = datman.xnat.get_connection(
                config, site=site, url=url, auth=auth,
                server_cache=server_cache)

            for exper_id in xnat.get_experiment_ids(project):
                ident = get_experiment_identifier(config, project, exper_id)
                if not ident:
                    continue
                experiment = get_xnat_experiment(xnat, project, ident)
                if experiment:
                    experiments.append((xnat, experiment))

    return experiments


def get_experiment_identifier(config, project, experiment_id):
    """Get a valid datman identifier for an experiment found on XNAT.

    Args:
        config (:obj:`datman.config.config`): A datman configuration object.
        project (:obj:`str`): The name of a project on XNAT.
        experiment_id (:obj:`str`): The name of an experiment found on XNAT.

    Returns:
        :obj:`datman.scanid.Identifier` or None if experiment_id is invalid.
    """
    try:
        ident = validate_subject_id(experiment_id, config)
    except datman.scanid.ParseException:
        logger.error(f"Invalid XNAT experiment ID {experiment_id} in project "
                     f"{project}. Please update XNAT with correct ID.")
        return None

    if ident.session is None and not datman.scanid.is_phantom(ident):
        logger.error(f"Invalid experiment ID {experiment_id} in project "
                     f"{project}. Reason - Not a phantom, but missing session "
                     "number")
        return None

    if ident.modality != "MR":
        return None

    return ident


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
        try:
            xnat_project = config.get_key("XnatArchive", site=site)
        except datman.config.UndefinedSetting:
            logger.warning(f"{site} doesnt define an XnatArchive to pull "
                           "from. Ignoring.")
            continue
        projects.setdefault(xnat_project, set()).add(site)
    return projects


def get_xnat_experiment(xnat, project, ident):
    """Retrieve information about an XNAT experiment.

    Args:
        xnat (:obj:`datman.xnat.XNAT`): A connection to an XNAT server.
        project (:obj:`str`): The name of the XNAT project the experiment
            belongs to.
        ident (:obj:`datman.scanid.Identifier`): A datman identifier for the
            experiment.

    Returns:
        :obj:`datman.importers.XNATExperiment` or None if not found.
    """
    experiment_label = ident.get_xnat_experiment_id()

    logger.info(f"Retrieving experiment: {experiment_label}")

    try:
        xnat_experiment = xnat.get_experiment(
            project, ident.get_xnat_subject_id(), experiment_label,
            ident=ident)
    except Exception as e:
        logger.error(f"Unable to retrieve experiment {experiment_label} from "
                     f"XNAT server. {type(e).__name__}: {e}")
        return None
    return xnat_experiment


def export_resources(resource_dir, xnat, importer, dry_run=False):
    """Export all resource (non-dicom) files for a scan session.

    Args:
        resource_dir (:obj:`str`): The absolute path to where resources
            should be exported.
        xnat (:obj:`datman.xnat.XNAT`): A connection to an XNAT server.
        importer (:obj:`datman.importers.SessionImporter`): An importer for
            the scan session to export resources for.
        dry_run (bool, optional): Report changes that would be made without
            modifying anything.  Defaults to False.
    """
    logger.info(f"Extracting {len(importer.resource_files)} resources "
                f"from {importer.name}")

    if not os.path.isdir(resource_dir):
        logger.info(f"Creating resources dir {resource_dir}")
        try:
            os.makedirs(resource_dir)
        except OSError:
            logger.error(f"Failed creating resources dir {resource_dir}")
            return

    if isinstance(importer, datman.importers.ZipImporter):
        out_dir = os.path.join(resource_dir, "MISC")
        try:
            define_folder(out_dir)
        except OSError:
            logger.error(f"Failed creating target folder: {out_dir}")
            return
        for item in importer.resource_files:
            dest_item = os.path.join(out_dir, item)
            if not os.path.exists(dest_item):
                importer.get_resources(out_dir, item)
        return

    xnat_experiment = importer

    for label in xnat_experiment.resource_ids:
        if label == "No Label":
            target_path = os.path.join(resource_dir, "MISC")
        else:
            target_path = os.path.join(resource_dir, label)

        try:
            target_path = define_folder(target_path)
        except OSError:
            logger.error(f"Failed creating target folder: {target_path}")
            continue

        xnat_resource_id = xnat_experiment.resource_ids[label]

        try:
            resources = xnat.get_resource_list(xnat_experiment.project,
                                               xnat_experiment.subject,
                                               xnat_experiment.name,
                                               xnat_resource_id)
        except Exception as e:
            logger.error(f"Failed getting resource {xnat_resource_id} for "
                         f"experiment {xnat_experiment.name}. Reason - {e}")
            continue

        if not resources:
            continue

        for resource in resources:
            resource_path = os.path.join(target_path, resource['URI'])
            if os.path.isfile(resource_path):
                logger.debug(f"Resource {resource['name']} from experiment "
                             f"{xnat_experiment.name} already exists")
            else:
                logger.info(f"Downloading {resource['name']} from experiment "
                            f"{xnat_experiment.name}")
                download_resource(xnat,
                                  xnat_experiment,
                                  xnat_resource_id,
                                  resource['URI'],
                                  resource_path,
                                  dry_run=dry_run)


def download_resource(xnat, xnat_experiment, xnat_resource_id,
                      xnat_resource_uri, target_path, dry_run=False):
    """
    Download a single resource file from XNAT. Target path should be
    full path to store the file, including filename
    """
    if dry_run:
        logger.info(f"DRY RUN: Skipping download of {xnat_resource_uri} to "
                    f"{target_path}")
        return None

    try:
        source = xnat.get_resource(xnat_experiment.project,
                                   xnat_experiment.subject,
                                   xnat_experiment.name,
                                   xnat_resource_id,
                                   xnat_resource_uri,
                                   zipped=False)
    except Exception as e:
        logger.error("Failed downloading resource archive from "
                     f"{xnat_experiment.name} with reason: {e}")
        return None

    # check that the target path exists
    target_dir = os.path.split(target_path)[0]
    if not os.path.exists(target_dir):
        try:
            os.makedirs(target_dir)
        except OSError:
            logger.error(f"Failed to create directory: {target_dir}")
            return None

    # copy the downloaded file to the target location
    try:
        if not dry_run:
            shutil.copyfile(source, target_path)
    except (IOError, OSError):
        logger.error(f"Failed copying resource {source} to target "
                     f"{target_path}")

    # finally delete the temporary archive
    try:
        os.remove(source)
    except OSError:
        logger.error(f"Failed to remove temporary archive {source} on "
                     f"system {platform.node()}")
    return target_path


def export_scans(config, xnat, importer, session, bids_opts=None,
                 wanted_tags=None, ignore_db=False, dry_run=False):
    """Export all XNAT data for a session to desired formats.

    Args:
        config (:obj:`datman.config.config`): A datman config object for
            the study the experiment belongs to.
        xnat (:obj:`datman.xnat.xnat`): An XNAT connection for the server
            the experiment resides on.
        importer (:obj:`datman.importer.SessionImporter`): An instance of
            a SessionImporter that holds all information needed to get
            scans data.
        session (:obj:`datman.scan.Scan`): The datman session this experiment
            belongs to.
        bids_opts (:obj:`BidsOptions`, optional): dcm2bids settings to be
            used if exporting to BIDS format. Defaults to None.
        wanted_tags (:obj:`list`, optional): A list of datman style tags.
            If provided, only scans that match the given tags will be
            exported. Defaults to None.
        ignore_db (bool, optional): If True, datman's QC dashboard will not
            be updated. Defaults to False.
        dry_run (bool, optional): If True, no outputs will be made. Defaults
            to False.
    """
    logger.info(f"Processing scans in experiment {importer.name}")

    importer.assign_scan_names(config, session._ident)

    session_exporters = make_session_exporters(
        config, session, importer, bids_opts=bids_opts,
        ignore_db=ignore_db, dry_run=dry_run)

    series_exporters = make_all_series_exporters(
        config, session, importer, bids_opts=bids_opts,
        wanted_tags=wanted_tags, dry_run=dry_run
    )

    if not needs_export(session_exporters) and not series_exporters:
        logger.debug(f"Session {importer} already extracted. Skipping.")
        return

    with make_temp_directory(prefix="dm_xnat_extract_") as temp_dir:
        for scan in importer.scans:
            if needs_download(scan, session_exporters, series_exporters):
                scan.get_files(temp_dir, xnat)

            for exporter in series_exporters.get(scan, []):
                exporter.export(scan.dcm_dir)

        for exporter in session_exporters:
            try:
                exporter.export(temp_dir)
            except Exception as e:
                logger.error(f"Exporter {exporter} failed - {e}")


def make_session_exporters(config, session, experiment, bids_opts=None,
                           ignore_db=False, dry_run=False):
    """Creates exporters that take an entire session as input.

    Args:
        config (:obj:`datman.config.config`): A datman config object for
            the study the experiment belongs to.
        session (:obj:`datman.scan.Scan`): The datman session this experiment
            belongs to.
        experiment (:obj:`datman.xnat.XNATExperiment`): The experiment
            to create exporters for.
        bids_opts (:obj:`BidsOptions`, optional): dcm2bids settings to be
            used if exporting to BIDS format. Defaults to None.
        ignore_db (bool, optional): If True, datman's QC dashboard will not
            be updated. Defaults to False.
        dry_run (bool, optional): If True, no outputs will be made. Defaults
            to False.

    Returns:
        list: Returns a list of :obj:`datman.exporters.Exporter` for the
            desired session export formats.
    """
    formats = get_session_formats(
        bids_opts=bids_opts,
        ignore_db=ignore_db
    )

    exporters = []
    for exp_format in formats:
        # pylint: disable-next=invalid-name
        Exporter = datman.exporters.get_exporter(exp_format, scope="session")
        exporters.append(
            Exporter(config, session, experiment, bids_opts=bids_opts,
                     ignore_db=ignore_db, dry_run=dry_run)
        )
    return exporters


def get_session_formats(bids_opts=None, ignore_db=False):
    """Get the string identifiers for all session exporters that are needed.

    Args:
        bids_opts (:obj:`BidsOptions`, optional): dcm2bids settings to be
            used if exporting to BIDS format. Defaults to None.
        ignore_db (bool, optional): If True, datman's QC dashboard will not
            be updated. Defaults to False.

    Returns:
        list: a list of string keys that should be used to make exporters.
    """
    formats = []
    if bids_opts:
        formats.append("bids")
        formats.append("nii_link")
    if not ignore_db:
        formats.append("db")
    return formats


def make_all_series_exporters(config, session, experiment, bids_opts=None,
                              wanted_tags=None, dry_run=False):
    """Create series exporters for all scans in an experiment.

    Args:
        config (:obj:`datman.config.config`): A datman config object for
            the study the experiment belongs to.
        session (:obj:`datman.scan.Scan`): The datman session this experiment
            belongs to.
        experiment (:obj:`datman.xnat.XNATExperiment`): The experiment
            to create series exporters for.
        bids_opts (:obj:`BidsOptions`, optional): dcm2bids settings to be
            used if exporting to BIDS format. Defaults to None.
        wanted_tags (:obj:`list`, optional): A list of datman style tags.
            If provided, only scans that match the given tags will have
            exporters created for them. Defaults to None.
        dry_run (bool, optional): If True, no outputs will be made. Defaults
            to False.
    """
    if bids_opts:
        return {}

    tag_config = get_tag_settings(config, session.site)
    if not tag_config:
        return {}

    series_exporters = {}
    for scan in experiment.scans:
        if not scan.is_usable(strict=True):
            continue

        exporters = make_series_exporters(
            session, scan, tag_config, config, wanted_tags=wanted_tags,
            dry_run=dry_run)

        if exporters:
            series_exporters[scan] = exporters

    return series_exporters


def get_tag_settings(config, site):
    """Get configuration for all tags defined for a specific site.
    """
    try:
        tags = config.get_tags(site=site)
    except datman.exceptions.UndefinedSetting:
        logger.error(f"Can't locate tag settings for site {site}")
        return None
    return tags


def make_series_exporters(session, scan, tag_config, config, wanted_tags=None,
                          dry_run=False):
    """Create series exporters for a single scan.

    Args:
        session (:obj:`datman.scan.Scan`): The datman session this experiment
            belongs to.
        scan (:obj:`datman.xnat.XNATScan`): The scan to create scan exporters
            for.
        tag_config (:obj:`datman.config.TagInfo`): The tag configuration
            of all tags for the data's study and site.
        config (:obj:`datman.config.config`): A datman config object for
            the study the experiment belongs to.
        wanted_tags (:obj:`list`, optional): A list of datman style tags.
            If provided, only scans that match the given tags will have
            exporters created for them. Defaults to None.
        dry_run (bool, optional): If True, no outputs will be made. Defaults
            to False.
    """
    exporters = []
    for idx, tag in enumerate(scan.tags):
        try:
            _ = datman.scanid.parse_filename(scan.names[idx])
        except datman.scanid.ParseException:
            logger.error(f"Invalid filename {scan.names[idx]}, ignoring scan.")
            continue

        if wanted_tags and tag not in wanted_tags:
            continue

        try:
            formats = tag_config.get(tag)["Formats"]
        except KeyError:
            formats = []

        if is_blacklisted(scan.names[idx], config):
            formats = []

        logger.debug(f"Found export formats {formats} for {scan}")
        for exp_format in formats:
            # pylint: disable-next=invalid-name
            Exporter = datman.exporters.get_exporter(
                exp_format, scope="series")

            if not Exporter:
                continue

            exporter = Exporter(
                Exporter.get_output_dir(session),
                scan.names[idx],
                echo_dict=scan.echo_dict,
                dry_run=dry_run
            )

            if not exporter.outputs_exist():
                exporters.append(exporter)

    return exporters


def is_blacklisted(scan_name, config):
    """Returns True if the given scan has been blacklisted.
    """
    try:
        blacklist_entry = read_blacklist(scan=scan_name, config=config)
    except datman.scanid.ParseException:
        logger.error(f"{scan_name} is not a datman ID, cannot check blacklist")
        return False

    if blacklist_entry:
        return True
    return False


def needs_raw(session_exporters):
    """Returns true if raw data is needed to run any session exporters.
    """
    return any(exp.needs_raw_data() for exp in session_exporters)


def needs_export(session_exporters):
    """Returns True if any session exporters need to be run.
    """
    try:
        return any(not exp.outputs_exist() for exp in session_exporters)
    except ValueError:
        # ValueError is raised when an invalid series number exists on XNAT.
        # Skip these sessions
        return False


def needs_download(scan, session_exporters, series_exporters):
    """Returns True if the given scan needs to be downloaded.
    """
    if needs_raw(session_exporters) and scan.is_usable():
        return True
    if scan in series_exporters:
        return True
    return False


if __name__ == '__main__':
    main()
