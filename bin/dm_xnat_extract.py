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
import logging
import os
import platform
import shutil
import sys

import datman.config
import datman.exceptions
import datman.exporters
import datman.scan
import datman.scanid
import datman.xnat
from datman.utils import (validate_subject_id, define_folder,
                          make_temp_directory, locate_metadata, read_blacklist)

logger = logging.getLogger(os.path.basename(__file__))


class BidsOptions:
    """Helper class for options related to exporting to BIDS format.
    """

    def __init__(self, config, keep_dcm=False, bids_out=None,
                 force_dcm2niix=False, clobber=False, dcm2bids_config=None,
                 log_level="INFO", refresh=False):
        self.keep_dcm = keep_dcm
        self.force_dcm2niix = force_dcm2niix
        self.clobber = clobber
        self.refresh = refresh
        self.bids_out = bids_out
        self.log_level = log_level
        self.dcm2bids_config = self.get_bids_config(
            config, bids_conf=dcm2bids_config)

    def get_bids_config(self, config, bids_conf=None):
        """Find the path to a valid dcm2bids config file.

        Args:
            config (:obj:`datman.config.config`): The datman configuration.
            bids_conf (:obj:`str`, optional): The user provided path to
                the config file. Defaults to None.

        Raises:
            datman.exceptions.MetadataException if a valid file cannot
                be found.

        Returns:
            str: The full path to a dcm2bids config file.
        """
        if bids_conf:
            path = bids_conf
        else:
            try:
                path = locate_metadata("dcm2bids.json", config=config)
            except FileNotFoundError as exc:
                raise datman.exceptions.MetadataException(
                    "No dcm2bids.json config file available for "
                    f"{config.study_name}") from exc

        if not os.path.exists(path):
            raise datman.exceptions.MetadataException(
                "No dcm2bids.json settings provided.")

        return path


def main():
    args = read_args()

    configure_logging(args.study, args.quiet, args.verbose, args.debug)

    if args.use_dcm2bids and not datman.exporters.DCM2BIDS_FOUND:
        logger.error("Failed to import Dcm2Bids. Ensure that "
                     "Dcm2Bids is installed when using the "
                     "--use-dcm2bids flag.  Exiting conversion")
        return

    config = datman.config.config(study=args.study)
    if args.use_dcm2bids:
        bids_opts = BidsOptions(
            config,
            keep_dcm=args.keep_dcm,
            force_dcm2niix=args.force_dcm2niix,
            clobber=args.clobber,
            dcm2bids_config=args.dcm_config,
            bids_out=args.bids_out,
            refresh=args.refresh
        )
    else:
        bids_opts = None

    auth = datman.xnat.get_auth(args.username) if args.username else None

    if args.experiment:
        experiments = collect_experiment(
            config, args.experiment, args.study, auth=auth, url=args.server)
    else:
        experiments = collect_all_experiments(
            config, auth=auth, url=args.server)

    logger.info(f"Found {len(experiments)} experiments for study {args.study}")

    for xnat, project, ident in experiments:
        xnat_experiment = get_xnat_experiment(xnat, project, ident)
        if not xnat_experiment:
            continue

        session = datman.scan.Scan(ident, config, bids_root=args.bids_out)

        if xnat_experiment.resource_files and not xnat_experiment.is_shared():
            export_resources(session.resource_path, xnat, xnat_experiment,
                             dry_run=args.dry_run)

        if xnat_experiment.scans:
            export_scans(config, xnat, xnat_experiment, session,
                         bids_opts=bids_opts, dry_run=args.dry_run,
                         ignore_db=args.dont_update_dashboard,
                         wanted_tags=args.tag)


def read_args():
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
        "Options for choosing data from XNAT to extract"
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

    g_dcm2bids = parser.add_argument_group(
        "Options for using dcm2bids"
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

    args = parser.parse_args()

    bids_opts = [args.keep_dcm, args.dcm_config, args.bids_out,
                 args.force_dcm2niix, args.clobber, args.refresh]
    if not args.use_dcm2bids and any(bids_opts):
        parser.error("dcm2bids configuration requires --use-dcm2bids")

    return args


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
    logging.getLogger('datman.exporters').addHandler(ch)


def collect_experiment(config, experiment_id, study, url=None, auth=None):
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

    return [(xnat, xnat_project, ident)]


def get_identifier(config, subid):
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
    experiments = []
    server_cache = {}

    for project, sites in get_projects(config).items():
        for site in sites:
            xnat = datman.xnat.get_connection(
                config, site=site, url=url, auth=auth,
                server_cache=server_cache)

            for exper_id in xnat.get_experiment_ids(project):
                ident = get_experiment_identifier(config, project, exper_id)
                if ident:
                    experiments.append((xnat, project, ident))

    return experiments


def get_experiment_identifier(config, project, experiment_id):
    try:
        ident = validate_subject_id(experiment_id, config)
    except datman.scanid.ParseException:
        logger.error(f"Invalid XNAT experiment ID {experiment_id} in project "
                     f"{project}. Please update XNAT with correct ID.")
        return

    if ident.session is None and not datman.scanid.is_phantom(ident):
        logger.error(f"Invalid experiment ID {experiment_id} in project "
                     f"{project}. Reason - Not a phantom, but missing session "
                     "number")
        return

    if ident.modality != "MR":
        return

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
    experiment_label = ident.get_xnat_experiment_id()

    logger.info(f"Retrieving experiment: {experiment_label}")

    try:
        xnat_experiment = xnat.get_experiment(
            project, ident.get_xnat_subject_id(), experiment_label)
    except Exception as e:
        logger.error(f"Unable to retrieve experiment {experiment_label} from "
                     f"XNAT server. {type(e).__name__}: {e}")
        return
    return xnat_experiment


def export_resources(resource_dir, xnat, xnat_experiment, dry_run=False):
    logger.info(f"Extracting {len(xnat_experiment.resource_files)} resources "
                f"from {xnat_experiment.name}")

    if not os.path.isdir(resource_dir):
        logger.info(f"Creating resources dir {resource_dir}")
        try:
            os.makedirs(resource_dir)
        except OSError:
            logger.error(f"Failed creating resources dir {resource_dir}")
            return

    for label in xnat_experiment.resource_IDs:
        if label == "No Label":
            target_path = os.path.join(resource_dir, "MISC")
        else:
            target_path = os.path.join(resource_dir, label)

        try:
            target_path = define_folder(target_path)
        except OSError:
            logger.error(f"Failed creating target folder: {target_path}")
            continue

        xnat_resource_id = xnat_experiment.resource_IDs[label]

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
        return

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
        return

    # check that the target path exists
    target_dir = os.path.split(target_path)[0]
    if not os.path.exists(target_dir):
        try:
            os.makedirs(target_dir)
        except OSError:
            logger.error(f"Failed to create directory: {target_dir}")
            return

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


def export_scans(config, xnat, xnat_experiment, session, bids_opts=None,
                 wanted_tags=None, ignore_db=False, dry_run=False):
    """Export all XNAT data for a session to desired formats.

    Args:
        config (:obj:`datman.config.config`): A datman config object for
            the study the experiment belongs to.
        xnat (:obj:`datman.xnat.xnat`): An XNAT connection for the server
            the experiment resides on.
        xnat_experiment (:obj:`datman.xnat.XNATExperiment`): The experiment
            to download, extract and export.
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
    logger.info(f"Processing scans in experiment {xnat_experiment.name}")

    xnat_experiment.assign_scan_names(config, session._ident)

    session_exporters = make_session_exporters(
        config, session, xnat_experiment, bids_opts=bids_opts,
        ignore_db=ignore_db, dry_run=dry_run)

    series_exporters = make_all_series_exporters(
        config, session, xnat_experiment, bids_opts=bids_opts,
        wanted_tags=wanted_tags, dry_run=dry_run
    )

    if not needs_export(session_exporters) and not series_exporters:
        logger.debug(f"Session {xnat_experiment} already extracted. Skipping.")
        return

    with make_temp_directory(prefix="dm_xnat_extract_") as temp_dir:
        for scan in xnat_experiment.scans:
            if needs_download(scan, session_exporters, series_exporters):
                scan.download(xnat, temp_dir)

            for exporter in series_exporters.get(scan, []):
                exporter.export(scan.download_dir)

        for exporter in session_exporters:
            exporter.export(temp_dir)


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
        shared=experiment.is_shared(),
        ignore_db=ignore_db
    )

    exporters = []
    for exp_format in formats:
        Exporter = datman.exporters.get_exporter(exp_format, scope="session")
        exporters.append(
            Exporter(config, session, experiment, bids_opts=bids_opts,
                     ignore_db=ignore_db, dry_run=dry_run)
        )
    return exporters


def get_session_formats(bids_opts=None, shared=False, ignore_db=False):
    """Get the string identifiers for all session exporters that are needed.

    Args:
        bids_opts (:obj:`BidsOptions`, optional): dcm2bids settings to be
            used if exporting to BIDS format. Defaults to None.
        shared (bool, optional): Whether to treat the session as a
            shared XNAT experiment. Defaults to False.
        ignore_db (bool, optional): If True, datman's QC dashboard will not
            be updated. Defaults to False.

    Returns:
        list: a list of string keys that should be used to make exporters.
    """
    formats = []
    if shared:
        formats.append("shared")
    elif bids_opts:
        # Only do 'bids' format if not a shared session.
        formats.append("bids")

    if bids_opts:
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
    return any([exp.needs_raw_data() for exp in session_exporters])


def needs_export(session_exporters):
    """Returns True if any session exporters need to be run.
    """
    return any([not exp.outputs_exist() for exp in session_exporters])


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
