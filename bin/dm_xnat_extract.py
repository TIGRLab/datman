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
                          make_temp_directory)

logger = logging.getLogger(os.path.basename(__file__))


def main():
    args = read_args()

    configure_logging(args.study, args.quiet, args.verbose, args.debug)

    if args.use_dcm2bids and not datman.exporters.DCM2BIDS_FOUND:
        logger.error("Failed to import Dcm2Bids. Ensure that "
                     "Dcm2Bids is installed when using the "
                     "--use-dcm2bids flag.  Exiting conversion")
        return

    config = datman.config.config(study=args.study)

    if args.username:
        auth = datman.xnat.get_auth(args.username)

    if args.experiment:
        experiments = collect_experiment(args.experiment, args.study, config)
    else:
        experiments = collect_all_experiments(
            config, auth=auth, url=args.server)

    logger.info(f"Found {len(experiments)} experiments for study {args.study}")

    for xnat, project, ident in experiments:
        xnat_experiment = get_xnat_experiment(xnat, project, ident)
        if not xnat_experiment:
            continue

        if xnat_experiment.resource_files:
            export_resources(config, xnat, xnat_experiment, ident)

        if xnat_experiment.scans:
            export_scans(
                config,
                xnat,
                xnat_experiment,
                ident,
                use_bids=args.use_dcm2bids,
                bids_root=args.bids_out,
                keep_dcm=args.keep_dcm,
                clobber=args.clobber,
                force_dcm2niix=args.keep_dcm2niix,
                dcm2bids_config=args.dcm2bids_config,
                wanted_tags=args.wanted_tags,
                ignore_db=args.ignore_db)


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
        action="store",
        metavar="tag,...",
        nargs="?",
        help="List of scan tags to download"
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
                 args.force_dcm2niix, args.clobber]
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
    ident = get_identifier(experiment_id)
    xnat = datman.xnat.get_connection(
        config, site=ident.site, url=None, auth=auth)
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
        logger.error(f"Invalid experiment ID {experiment_id} in project "
                     f"{project}.")
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


def export_resources(config, xnat, xnat_experiment, ident):
    logger.info(f"Extracting {len(xnat_experiment.resource_files)} resources "
                f"from {xnat_experiment.name}")

    base_path = os.path.join(config.get_path('resources'), str(ident))

    if not os.path.isdir(base_path):
        logger.info(f"Creating resources dir {base_path}")
        try:
            os.makedirs(base_path)
        except OSError:
            logger.error(f"Failed creating resources dir {base_path}")
            return

    for label in xnat_experiment.resource_IDs:
        if label == "No Label":
            target_path = os.path.join(base_path, "MISC")
        else:
            target_path = os.path.join(base_path, label)

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
                                  resource_path)


def download_resource(xnat, xnat_experiment, xnat_resource_id,
                      xnat_resource_uri, target_path, dry_run=False):
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


def export_scans(config, xnat, xnat_experiment, ident, use_bids=False,
                 bids_root=None, keep_dcm=False, clobber=False,
                 force_dcm2niix=False, dcm2bids_config=None, wanted_tags=None,
                 ignore_db=False, dry_run=False):
    logger.info(f"Processing scans in experiment {xnat_experiment.name}")

    session = datman.scan.Scan(ident, config, bids_root=bids_root)

    if use_bids and os.path.exists(session.bids_path):
        logger.info(f"{session.bids_path} already exists")
        if clobber:
            logger.info("Overwriting because of --clobber")
        else:
            logger.info("(Use --clobber to overwrite)")
            return

    xnat_experiment.set_export_formats(
        use_bids=use_bids,
        ignore_db=ignore_db
    )

    xnat_experiment.assign_scan_names(
        config,
        ident,
        wanted_tags=wanted_tags,
        ignore_blacklist=use_bids
    )

    with make_temp_directory(prefix="dm_xnat_extract_") as temp_dir:
        for scan in xnat_experiment.scans:
            if not scan.needs_download(session):
                continue

            scan.download(xnat, temp_dir)
            for exporter in make_series_exporters(session, scan,
                                                  dry_run=dry_run):
                exporter.export()

        for format in xnat_experiment.formats:
            Exporter = datman.exporters.get_exporter(format, "session")

            if not Exporter:
                continue

            exporter = Exporter(config, session, xnat_experiment, temp_dir,
                                keep_dcm=keep_dcm, clobber=clobber,
                                force_dcm2niix=force_dcm2niix,
                                dcm2bids_config=dcm2bids_config)
            exporter.export()


def make_series_exporters(session, scan, dry_run=False):
    for idx, tag in enumerate(scan.tags):
        try:
            formats = scan.formats[tag]
        except KeyError:
            formats = []

        for format in formats:
            Exporter = datman.exporters.get_exporter(format, "series")

            if not Exporter:
                continue

            yield Exporter(
                scan.download_dir,
                Exporter.get_output_dir(session),
                scan.names[idx],
                echo_dict=scan.echo_dict,
                dry_run=dry_run
            )


if __name__ == '__main__':
    main()
