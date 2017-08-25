#!/usr/bin/env python
"""
Calculates tract coordinates in subject space.
Transforms a DTI atlas to subject space and returns streamlines coordinates
    associated with tracts.

This is the launch file to run multiple subjects in datman format

Usage:
    tractmap.py [options] <study>
    tractmap.py [options] <study> <session>

Arguments:
    <study>     Name of the study to process
    <session>   Session identifier,
                all subjects in a study are processed if not included

Options:
    --atlas_file=<atlas_file>       Path to a tractography atlas file (vtp or vtk)
    --cluster_dir=<cluster_dir>     Path to a folder containing the atlas tract clusters
    --mrml_file=<mrml_file>         Path to the atlas mrml (Slicer) file mapping clusters to tracts
    --cluster-pattern=<pattern>     A regular expression used to limit files
                                    in <clusterDir>
                                    [default: ^.*cluster_\d{5}]
    --mitk_container=<mirtk_file>   Path to the mirtk singularity image
                                    [default: /archive/code/containers/MIRTK/MIRTK.img]
    --tags=<tags>                   Comma seperated list of tags to process
                                    [default: DTI60-1000]
    --leave_temp_files              Delete temporary files.
                                    [default: True]
    --debug                         Extra logging information
    --quiet                         Only log errors
    --logDir=<logDir>               Place to put logs
    --rewrite                       Overwrite existing outputs

Details:
    If atlas_file, cluser_dir, mrml_file are not specified the defaults in
    /opt/quarantine/tractmap are used.
"""
import logging
import os
import subprocess
import sys
import tempfile
from datman.docopt import docopt

from datman import scanid
from datman import config

JOB_TEMPLATE = """
#####################################
#$ -S /bin/bash
#$ -wd /tmp/
#$ -N {name}
#$ -e {errfile}
#$ -o {logfile}
#####################################
echo "------------------------------------------------------------------------"
echo "Job started on" `date`
echo "------------------------------------------------------------------------"
{script}
echo "------------------------------------------------------------------------"
echo "Job ended on" `date`
echo "------------------------------------------------------------------------"
"""

CODE_TEMPLATE = """
module load python/2.7.13_sci_01
module load whitematteranalysis/latest
module load tractconverter/0.8.1
module load tractmap/latest
source activate
get_subject_tract_coordinates.py \
--cluster-pattern="{cluster_pattern}" \
--mirtk_file="{container}" \
--output="{outfile}" \
{options} \
"{subject}" "{anat}"
"""

logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class QJob(object):
    def __init__(self, cleanup=True):
        self.cleanup = cleanup

    def __enter__(self):
        self.qs_f, self.qs_n = tempfile.mkstemp(suffix='.qsub')
        return self

    def __exit__(self, type, value, traceback):
        try:
            os.close(self.qs_f)
            if self.cleanup:
                os.remove(self.qs_n)
        except OSError:
            pass

    def run(self, code, name="Tractmap", logfile="output.$JOB_ID", errfile="error.$JOB_ID", cleanup=True, slots=1):
        open(self.qs_n, 'w').write(JOB_TEMPLATE.format(script=code,
                                                       name=name,
                                                       logfile=logfile,
                                                       errfile=errfile,
                                                       slots=slots))
        logger.info('Submitting job')
        logger.debug('Job code:{}'.format(code))
        subprocess.call('qsub < ' + self.qs_n, shell=True)


def make_job(src_files, outFile):
    """
    Launches a job on the cluster
    """
    opts = ''

    if ATLAS_FILE:
        opts = opts + "--atlas_file='{}' ".format(ATLAS_FILE)
    if CLUSTER_DIR:
        opts = opts + "--cluster_dir='{}' ".format(CLUSTER_DIR)
    if MRML_FILE:
        opts = opts + "--mrml_file='{}' ".format(MRML_FILE)
    if CLEANUP:
        opts = opts + "--cleanup "
    if DEBUG:
        opts = opts + "--debug "
    if QUIET:
        opts = opts + "--quiet "

    code = CODE_TEMPLATE.format(cluster_pattern=CLUSTER_PATTERN,
                                container=CONTAINER,
                                atlas=ATLAS_FILE,
                                clusters=CLUSTER_DIR,
                                mrml=MRML_FILE,
                                subject=src_files[1],
                                anat=src_files[0],
                                options=opts,
                                outfile=outFile)

    with QJob() as qjob:
        logfile = os.path.join(LOGDIR, 'output.$JOB_ID')
        errfile = os.path.join(LOGDIR, 'error.$JOB_ID')
        qjob.run(code=code, logfile=logfile, errfile=errfile)


def get_files(session, filename):
    """
    Starts with a file in the nii folder
    Checks if the file is a DTI type, and session is not a phantom
    Checks to see if a SlicerTractography file exists in the dtiprep folder
    Returns a tuple(dti_file, tract_file) or none
    """
    if not filename.endswith('.nii.gz'):
        logger.info('File:{} is not a nifti file. Skipping'
                    .format(filename))
        return

    try:
        ident, tag, series, desc = scanid.parse_filename(filename)
    except scanid.ParseException:
        logger.debug('Invalid filename:{}'.format(filename))
        return

    if scanid.is_phantom(ident.get_full_subjectid_with_timepoint()):
        msg = "Session:{} is a phantom. Skipping".format(session)
        logger.info(msg)
        return

    if not tag in TAGS:
        msg = ("File:{} is not in taglist:{}. Skipping"
               .format(os.path.basename(filename),
                       TAGS))
        return

    base_name = scanid.make_filename(ident, tag, series, desc) + '_SlicerTractography.vtk'

    tract_file = os.path.join(DTIPREP_PATH, session, base_name)

    if not os.path.isfile(tract_file):
        logger.info('Tract file:{} not found.'.format(tract_file))
        return

    return(filename, tract_file)


def process_session(session):
    """
    Searches for all .nii.gz files with DTI tag in a session
    """
    logger.info('Processing session:{}'.format(session))
    # Check if inputs exist
    dtiprep_dir = os.path.join(DTIPREP_PATH, session)
    nii_dir = os.path.join(NII_PATH, session)
    files = os.listdir(nii_dir)
    # add the full path back to the file
    files = [os.path.join(nii_dir, f) for f in files]
    files_to_process = [get_files(session, f) for f in files]
    files_to_process = [f for f in files_to_process if f]

    if len(files_to_process) == 0:
        logger.warning('No DTI files found for session:{}'
                       .format(session))
        return

    for f in files_to_process:
        # check if the output already exists
        basename = os.path.splitext(os.path.basename(f[1]))[0]
        basename = basename + '_tract_ends.json'
        out_path = os.path.join(dtiprep_dir, basename)
        if os.path.isfile(out_path):
            logger.info('File:{} in session:{} is already processed. Skipping'
                        .format(basename, session))
            continue
        make_job(f, out_path)


def main(study, session=None):
    logger.info('Processing study:{}'.format(study))
    if session:
        process_session(session)
    else:
        sessions = os.listdir(NII_PATH)
        logger.info('Found {} sessions.'.format(len(sessions)))
        for session in sessions:
            process_session(session)

if __name__ == '__main__':
    arguments = docopt(__doc__)
    study = arguments['<study>']
    session = arguments['<session>']
    ATLAS_FILE = arguments['--atlas_file']
    CLUSTER_DIR = arguments['--cluster_dir']
    MRML_FILE = arguments['--mrml_file']
    CLUSTER_PATTERN = arguments['--cluster-pattern']
    CONTAINER = arguments['--mitk_container']
    CLEANUP = arguments['--leave_temp_files']
    LOGDIR = arguments['--logDir']
    OVERWRITE = arguments['--rewrite']
    TAGS = arguments['--tags']

    TAGS = [tag.strip() for tag in TAGS.split(',')]

    QUIET = False
    DEBUG = False
    if arguments['--debug']:
        DEBUG = True
        logger.setLevel(logging.DEBUG)
    elif arguments['--quiet']:
        QUIET = True
        logger.setLevel(logging.ERROR)
    else:
        logger.setLevel(logging.WARN)

    CFG = config.config(study=study)

    DTIPREP_PATH = CFG.get_path('dtiprep')
    NII_PATH = CFG.get_path('nii')

    if not LOGDIR:
        LOGDIR = os.path.join(DTIPREP_PATH, 'tractmap_logs')
    if not os.path.isdir(LOGDIR):
        logger.info("Creating log dir:{}".format(LOGDIR))
        try:
            os.mkdir(LOGDIR)
        except OSError:
            msg = 'Failed creating log directory"{}'.format(LOGDIR)
            logger.error(msg)
            sys.exit(msg)

    main(study, session)
