#!/usr/bin/env python
'''
Launch DTIPrep preprocessing pipeline for tensor-based analysis

Usage:
    dm_proc_dtiprep.py [options] [-t <TAG>]... <study>

Arguments:
    <study>                                 DATMAN style study shortname

Options:
    -s,--session SESSION                    DATMAN style session ID
    -t,--tag TAG                            Repeatable option for using substring selection to pick files to
                                            process
    -o,--outDir OUTDIR                      Directory to output pre-processing outputs to
    -l,--logDir LOGDIR                      Directory to output logging to
    -h,--homeDir HOMEDIR                    Directory to bind Singularity Home into (see NOTE)
    -q,--quiet                              Only log errors (show ERROR level messages only)
    -v,--verbose                            Chatty logging (show INFO level messages)
    -n,--nthreads NTHREADS                  Number of threads to utilize on the SCC
                                            [default: 3]

Requirements:
    slicer

NOTE:
We mount the user's scratch directory to singularity HOME since scc has some measures to prevent mounting resulting in permission errors. DTIPrep does not output anything into home so it should be okay - Jerry Jeyachandra

'''
import datman.config
import datman.utils
import logging
import os
import tempfile
import sys
import subprocess
import re
from docopt import docopt
import getpass


CONTAINER = 'DTIPREP/dtiprep.img'
DEFAULT_HOME = '/KIMEL/tigrlab/scratch/{user}/'

JOB_TEMPLATE = """
#####################################
#PBS -S /bin/bash
#PBS -N {name}
#PBS -e {errfile}
#PBS -o {logfile}
#####################################

echo "------------------------------------------------------------------------"
echo "Job started on" `date` "on system" `hostname`
echo "------------------------------------------------------------------------"
{script}
echo "------------------------------------------------------------------------"
echo "Job ended on" `date`
echo "------------------------------------------------------------------------"
"""

logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class QJob(object):
    def __init__(self, queue, nthreads=3, cleanup=True):
        self.cleanup = cleanup
        self.nthreads = nthreads
        self.queue = queue.lower()

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

    def get_qsub_cmd(self):
        if self.queue == 'sge':
            return ''
        elif self.queue == 'pbs':
            return '-l nodes=1:ppn{nthreads}'.format(nthreads=self.nthreads)

    def run(self, code, name="DTIPrep", logfile="output.$JOB_ID", errfile="error.$JOB_ID", cleanup=True, slots=1):
        open(self.qs_n, 'w').write(JOB_TEMPLATE.format(script=code,
                                                       name=name,
                                                       logfile=logfile,
                                                       errfile=errfile,
                                                       slots=slots))
        logger.info('Submitting job')

        qsub_opt = self.get_qsub_cmd()
        subprocess.call('qsub {} < '.format(qsub_opt) + self.qs_n, shell=True)


def make_job(src_dir, dst_dir, protocol_dir, log_dir, scan_name, nthreads, protocol_file=None, cleanup=True):
    # create a job file from template and use qsub to submit
    code = ("singularity run -H {home}:/tmp -B {src_dir}:/input -B {dst_dir}:/output -B {protocol_dir}:/meta {container} {scan_name}"
            .format(home=HOME_DIR,
                    src_dir=src_dir,
                    dst_dir=dst_dir,
                    protocol_dir=protocol_dir,
                    container=CONTAINER,
                    scan_name=scan_name))

    if protocol_file:
        code = code + ' --protocolFile={protocol_file}'.format(protocol_file=protocol_file)

    #Feed in global variable QUEUE into QJob
    with QJob(queue=QUEUE, nthreads=nthreads) as qjob:
        #logfile = '{}:/tmp/output.$JOB_ID'.format(socket.gethostname())
        #errfile = '{}:/tmp/error.$JOB_ID'.format(socket.gethostname())
        logfile = os.path.join(log_dir, 'output.$JOB_ID')
        errfile = os.path.join(log_dir, 'error.$JOB_ID')
        logger.info('Making job DTIPrep for scan:{}'.format(scan_name))
        qjob.run(code=code, logfile=logfile, errfile=errfile)


def process_nrrd(src_dir, dst_dir, protocol_dir, log_dir, nrrd_file, nthreads):
    scan, ext = os.path.splitext(nrrd_file[0])

    # expected name for the output file
    out_file = os.path.join(dst_dir, scan + '_QCed' + ext)
    if os.path.isfile(out_file):
        logger.info('File:{} already processed, skipping.'.format(nrrd_file[0]))
        return

    protocol_file = 'dtiprep_protocol_' + nrrd_file[1] + '.xml'

    if not os.path.isfile(os.path.join(protocol_dir, protocol_file)):
        # fall back to the default name
        protocol_file = 'dtiprep_protocol.xml'

    if not os.path.isfile(os.path.join(protocol_dir, protocol_file)):
        logger.error('Protocol file not found for tag:{}. A default protocol dtiprep_protocol.xml can be used.'.format(
            nrrd_file[1]))
    make_job(src_dir, dst_dir, protocol_dir, log_dir, scan, nthreads, protocol_file)


def convert_nii(dst_dir, log_dir):
    """
    Inspects output directory for nrrds, and converts them to nifti for
    downstream pipelines.
    """
    for nrrd_file in filter(lambda x: '.nrrd' in x, os.listdir(dst_dir)):
        file_stem = os.path.splitext(nrrd_file)[0]
        nii_file = file_stem + '.nii.gz'
        bvec_file = file_stem + '.bvec'
        bval_file = file_stem + '.bval'

        if nii_file not in os.listdir(dst_dir):
            logger.info('converting {} to {}'.format(nrrd_file, nii_file))

            cmd = 'DWIConvert --inputVolume {d}/{nrrd} --allowLossyConversion --conversionMode NrrdToFSL --outputVolume {d}/{nii} --outputBVectors {d}/{bvec} --outputBValues {d}/{bval}'.format(
                d=dst_dir, nrrd=nrrd_file, nii=nii_file, bvec=bvec_file, bval=bval_file)
            rtn, msg = datman.utils.run(cmd, verbose=False)

            # only report errors for actual diffusion-weighted data with directions
            # since DWIConvert is noisy when converting non-diffusion data from nrrd
            # we assume if this conversion is broken then all other conversion must be
            # suspect as well -- jdv
            if '_QCed.nrrd' in nrrd_file and rtn != 0:
                logger.error('File:{} failed to convert to NII.GZ\n{}'.format(nrrd_file, msg))


def process_session(src_dir, out_dir, protocol_dir, log_dir, session, tags, nthreads):
    """Launch DTI prep on all nrrd files in a directory"""
    src_dir = os.path.join(src_dir, session)
    out_dir = os.path.join(out_dir, session)
    nrrds = [f for f in os.listdir(src_dir) if f.endswith('.nrrd')]

    if not tags:
        tags = ['DTI']

    # filter for tags
    nrrd_dti = []
    for f in nrrds:
        try:
            _, tag, _, _ = datman.scanid.parse_filename(f)
        except datman.scanid.ParseException:
            continue
        tag_match = [re.search(t, tag) for t in tags]
        if any(tag_match):
            nrrd_dti.append((f, tag))

    if not nrrd_dti:
        logger.warning('No DTI nrrd files found for session:{}'.format(session))
        return
    logger.info('Found {} DTI nrrd files.'.format(len(nrrd_dti)))

    if not os.path.isdir(out_dir):
        try:
            os.mkdir(out_dir)
        except OSError:
            logger.error('Failed to create output directory:{}'.format(out_dir))
            return

    # dtiprep on nrrd files
    for nrrd in nrrd_dti:
        process_nrrd(src_dir, out_dir, protocol_dir, log_dir, nrrd, nthreads)

    # convert output nrrd files to nifti
    convert_nii(out_dir, log_dir)

if __name__ == '__main__':

    arguments   =   docopt(__doc__)

    study       =   arguments['<study>']
    session     =   arguments['--session']
    logDir      =   arguments['--logDir']
    outDir      =   arguments['--outDir']
    homeDir     =   arguments['--homeDir']
    tags        =   arguments['--tag']
    quiet       =   arguments['--quiet']
    verbose     =   arguments['--verbose']
    nthreads    =   arguments['--nthreads']

    #Set singularity home directory, see note in docstring

    if quiet:
        logger.setLevel(logging.ERROR)
    if verbose:
        logger.setLevel(logging.DEBUG)

    #Initialize global variables
    global HOME_DIR
    global QUEUE

    cfg = datman.config.config(study=study)
    system_settings = cfg.install_config

    HOME_DIR = homeDir if homeDir else DEFAULT_HOME.format(user=getpass.getuser())
    CONTAINER = os.path.join(system_settings['CONTAINERS'],CONTAINER)
    QUEUE = system_settings['QUEUE']

    #Get source paths
    nii_path = cfg.get_path('nii')
    nrrd_path = cfg.get_path('nrrd')
    meta_path = cfg.get_path('meta')

    if not outDir:
        outDir = cfg.get_path('dtiprep')

    if not os.path.isdir(outDir):
        logger.info("Creating output path:{}".format(outDir))
        try:
            os.mkdir(outDir)
        except OSError:
            logger.error('Failed creating output dir:{}'.format(outDir))
            sys.exit(1)

    if not logDir:
        logDir = os.path.join(outDir, 'logs')

    if not os.path.isdir(logDir):
        logger.info("Creating log dir:{}".format(logDir))
        try:
            os.mkdir(logDir)
        except OSError:
            logger.error('Failed creating log directory"{}'.format(logDir))

    if not os.path.isdir(nrrd_path):
        logger.error("Src directory:{} not found".format(nrrd_path))
        sys.exit(1)

    if not session:
        sessions = [d for d in os.listdir(nrrd_path) if os.path.isdir(os.path.join(nrrd_path, d))]
    else:
        sessions = [session]

    for session in sessions:
        process_session(nrrd_path, outDir, meta_path, logDir, session, tags, nthreads)
