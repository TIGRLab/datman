#!/usr/bin/env python
"""
Generates quality control reports on defined MRI data types. If no subject is
given, all subjects are submitted individually to the queue.

Usage:
    dm_qc_report.py [options] <study>
    dm_qc_report.py [options] <study> <session>

Arguments:
    <study>           Name of the study to process e.g. ANDT
    <session>         Datman name of session to process e.g. DTI_CMH_H001_01_01

Options:
    --refresh          Update dashboard metadata (e.g. header diffs, scan
                       lengths) and generate missing metrics, if any. Note
                       that existing QC metrics will not be modified.
    --remake           Delete and recreate all QC metrics. Also force update
                       of dashboard metadata (e.g. header diffs, scan lengths).
    --log-to-server    If set, all log messages will also be sent to the
                       configured logging server. This is useful when the
                       script is run on the queue, since it swallows logging.
    -q --quiet         Only report errors
    -v --verbose       Be chatty
    -d --debug         Be extra chatty

Requires:
    FSL/5.0.10
    matlab/R2014a - qa-dti phantom pipeline
    AFNI/2014.12.16 - abcd_fmri phantom pipeline
"""

import os
import glob
import time
import logging
import logging.handlers

import nibabel as nib
from docopt import docopt

import datman.config
import datman.utils
import datman.scan
import datman.dashboard
import datman.metrics
from datman.exceptions import InputException, ParseException, QCException

logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

REMAKE = False
REFRESH = False


def main():
    global REMAKE
    global REFRESH

    arguments = docopt(__doc__)
    study = arguments["<study>"]
    session = arguments["<session>"]
    REMAKE = arguments["--remake"]
    REFRESH = arguments["--refresh"]
    use_server = arguments["--log-to-server"]
    verbose = arguments["--verbose"]
    debug = arguments["--debug"]
    quiet = arguments["--quiet"]

    config = get_config(study)

    if use_server:
        add_server_handler(config)

    if quiet:
        logger.setLevel(logging.ERROR)
    if verbose:
        logger.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)

    if not session:
        return submit_subjects(config)

    if not datman.dashboard.dash_found:
        logger.error("Dashboard database not found, can't run.")
        return

    subject = prepare_scan(session, config)
    make_metrics(subject, config)


def get_config(study):
    """Get the study config and verify all needed paths are defined.

    Args:
        study (:obj:`str`): A study ID.

    Returns:
        :obj:`datman.config.config`: A config object for the study.
    """
    try:
        config = datman.config.config(study=study)
    except Exception:
        logger.error(f"Cannot find configuration info for study {study}")
        raise

    required_paths = ["nii", "qc", "std", "meta"]

    for path in required_paths:
        try:
            config.get_path(path)
        except datman.config.UndefinedSetting:
            logger.error(f"Path {path} not defined for project: {study}")
            raise

    return config


def add_server_handler(config):
    """Add a handler that pushes log messages to a server.

    Args:
        config (:obj:`datman.config.config`): A config object for the study.
    """
    server_ip = config.get_key("LogServer")
    server_handler = logging.handlers.SocketHandler(
        server_ip, logging.handlers.DEFAULT_TCP_LOGGING_PORT
    )
    logger.addHandler(server_handler)


def submit_subjects(config):
    """Submit a job for each subject in the study that still needs metrics.

    Args:
        config (:obj:`datman.config.config`): A config object for the study.
    """
    missing_cmds = check_prerequisites()
    if missing_cmds:
        logger.error(
            "Quitting. Software pre-requisite(s) missing, check all commands "
            f"installed: {', '.join(missing_cmds)}"
        )
        return

    subs = get_subids(config)

    for subject in subs:
        if not (REMAKE or REFRESH or needs_qc(subject, config)):
            continue

        command = make_command(subject)
        job_name = f"qc-{subject}-{time.strftime('%Y%m%d')}"

        logger.info(f"Submitting QC job for {subject}.")
        datman.utils.submit_job(
            command, job_name, "/tmp", system=config.system,
            argslist="--mem=5G"
        )


def check_prerequisites():
    missing_requirements = []
    for metric_type in datman.metrics.QC_FUNC.values():
        if not metric_type.is_runnable():
            missing_requirements.extend(metric_type.get_requirements())

    for metric_type in datman.metrics.PHA_QC_FUNC.values():
        if not metric_type.is_runnable():
            missing_requirements.extend(metric_type.get_requirements())

    return list(set(missing_requirements))


def get_subids(config):
    """Find all subject IDs for a study.

    Args:
        config (:obj:`datman.config.config`): A config object for the study.
    """
    nii_dir = config.get_path("nii")
    subject_nii_dirs = glob.glob(os.path.join(nii_dir, "*"))
    all_subs = [os.path.basename(path) for path in subject_nii_dirs]
    return all_subs


def make_command(subject_id):
    arguments = docopt(__doc__)

    command = [
        __file__,
        arguments["<study>"],
        subject_id
    ]

    for arg in arguments:
        if not (arg.startswith("-") and arguments[arg]):
            continue

        if isinstance(arguments[arg], bool):
            command.append(arg)
        else:
            command.append(f"{arg} {arguments[arg]}")

    return " ".join(command)


@datman.dashboard.release_db
def needs_qc(subject_id, config):
    """Check if any QC metrics are missing for a subject.

    Args:
        subject_id (:obj:`str`): The ID of a subject belonging to the study.
        config (:obj:`datman.config.config`): A config object for the study.

    Returns:
        bool: True if any metrics are missing, False otherwise.
    """
    try:
        subject = datman.scan.Scan(subject_id, config)
    except ParseException:
        logger.error(f"{subject_id} does not conform to datman naming "
                     "convention. Ignoring.")
        return False

    if not os.path.exists(subject.qc_path):
        return True

    handlers = datman.metrics.get_handlers(subject)

    for nii in subject.niftis:
        scan = datman.dashboard.get_scan(nii.file_name)

        if not scan:
            logger.error(f"Database record missing for {nii.file_name}")
            continue

        if not scan.length:
            return True

        if scan.is_outdated_header_diffs():
            return True

        try:
            metric = handlers[scan.qc_type](nii.path, subject.qc_path)
        except KeyError:
            logger.error(
                f"Invalid qc type {scan.qc_type} found for {nii.file_name}"
            )
            continue
        except QCException as e:
            logger.error(e)
            continue

        if not metric.exists():
            return True

    return False


def prepare_scan(subject_id, config):
    """Locate/create needed subject folders and clean up empty QC files.

    Args:
        subject_id (:obj:`str`): The ID of a subject in the study.
        config (:obj:`datman.config.config`): A config object for the study.

    Returns:
        :obj:`datman.scan.Scan`: A scan object for the subject.
    """
    try:
        subject = datman.scan.Scan(subject_id, config)
    except ParseException as e:
        logger.error(e, exc_info=True)
        raise e

    if not os.path.exists(subject.nii_path):
        raise InputException(f"Input path doesn't exist: {subject.nii_path}")

    qc_dir = datman.utils.define_folder(subject.qc_path)
    datman.utils.remove_empty_files(qc_dir)
    return subject


def make_metrics(subject, config):
    """Make QC metrics for each nifti file found for a subject.
    """
    db_subject = datman.dashboard.get_subject(subject.full_id)
    if not db_subject:
        logger.error(f"Database record not found for {subject.full_id}")
        return

    try:
        ignored_fields = config.get_key(
            "IgnoreHeaderFields", site=db_subject.site.name
        )
    except datman.config.UndefinedSetting:
        ignored_fields = []

    try:
        field_tolerances = config.get_key(
            "HeaderFieldTolerance", site=db_subject.site.name
        )
    except datman.config.UndefinedSetting:
        field_tolerances = {}

    handlers = datman.metrics.get_handlers(subject)

    for nii in subject.niftis:
        db_record = datman.dashboard.get_scan(nii.file_name)
        if not db_record:
            logger.error(
                f"Database record doesnt exist for scan {nii.file_name}. "
                "Ignoring."
            )
            continue

        try:
            metric = handlers[db_record.qc_type](nii.path, subject.qc_path)
        except Exception as e:
            logger.error(f"Failed to generate metrics for {nii.file_name}. "
                         f"Reason - {e}")

        update_dashboard(nii.path, ignored_fields, field_tolerances)
        make_scan_metrics(metric)


@datman.dashboard.release_db
def update_dashboard(nii_path, header_ignore=None, header_tolerance=None):
    """Update dashboard records for a scan.

    Args:
        nii_path (:obj:`str`): The full path to a nifti file.
        header_ignore (:obj:`list`, optional): Header fields to ignore during
            header checks. Defaults to None.
        header_tolerance (:obj:`dict`, optional): Header field tolerances to
            use during header checks. Defaults to None.
    """
    db_record = datman.dashboard.get_scan(nii_path)

    if REMAKE or REFRESH or db_record.is_outdated_header_diffs():
        try:
            db_record.update_header_diffs(
                standard=db_record.gold_standards[0],
                ignore=header_ignore, tolerance=header_tolerance)
        except Exception as e:
            logger.error(
                f"Failed generating header diffs for {str(db_record)} due to "
                f"exception: {e}"
            )

    if REMAKE or REFRESH or not db_record.length:
        add_scan_length(nii_path, db_record)


def make_scan_metrics(metric):
    """Generate all metrics for a single scan.

    Args:
        metric (:obj:`datman.metrics.Metric`): A QC metric to generate.
    """
    if metric.exists() and not REMAKE:
        return

    file_name = os.path.basename(metric.input)
    if not metric.is_runnable():
        logger.error(
            f"Can't make QC metrics for {file_name}. Software missing, "
            "check all commands are available: "
            f"{', '.join(metric.get_requirements())}"
        )
        return

    if REMAKE:
        try:
            remove_outputs(metric)
        except Exception as e:
            logger.error(f"Failed removing old outputs for {file_name}: {e}")
            return

    try:
        metric.generate()
    except datman.metrics.QCException as e:
        logger.error(f"Error making metrics for {file_name}: {e}")
    else:
        metric.write_manifest(overwrite=REMAKE)


def add_scan_length(nii_path, scan):
    """Find the length of a scan and it to the database.
    Args:
        nii_path (:obj:`str`): The full path to a nifti file.
        scan (:obj:`dashboard.models.Scan`): A scan database record.
    """
    try:
        data = nib.load(nii_path)
    except Exception as e:
        logger.error(f"Failed to read scan length for {nii_path}. Reason "
                     f"- {e}")
        return

    try:
        length = str(data.shape[3])
    except IndexError:
        length = "N/A"

    scan.length = length
    scan.save()


def remove_outputs(metric):
    for command in metric.outputs:
        for item in metric.outputs[command]:
            try:
                os.remove(item)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    main()
