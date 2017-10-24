#!/usr/bin/env python
"""Launch the DTIPrep pipeline"""

import datman.config
import datman.utils
import logging
import argparse
import os
import tempfile
import sys
import subprocess
import re

CONTAINER = '/archive/code/containers/DTIPREP/dtiprep.img'

JOB_TEMPLATE = """
#####################################
#$ -S /bin/bash
#$ -wd /tmp/
#$ -N {name}
#$ -e {errfile}
#$ -o {logfile}
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

    def run(self, code, name="DTIPrep", logfile="output.$JOB_ID", errfile="error.$JOB_ID", cleanup=True, slots=1):
        open(self.qs_n, 'w').write(JOB_TEMPLATE.format(script=code,
                                                       name=name,
                                                       logfile=logfile,
                                                       errfile=errfile,
                                                       slots=slots))
        logger.info('Submitting job')
        subprocess.call('qsub < ' + self.qs_n, shell=True)


def make_job(src_dir, dst_dir, protocol_dir, log_dir, scan_name, protocol_file=None, cleanup=True):
    # create a job file from template and use qsub to submit
    code = ("singularity run -B {src_dir}:/input -B {dst_dir}:/output -B {protocol_dir}:/meta {container} {scan_name}"
            .format(src_dir=src_dir,
                    dst_dir=dst_dir,
                    protocol_dir=protocol_dir,
                    container=CONTAINER,
                    scan_name=scan_name))

    if protocol_file:
        code = code + ' --protocolFile={protocol_file}'.format(protocol_file=protocol_file)

    with QJob() as qjob:
        #logfile = '{}:/tmp/output.$JOB_ID'.format(socket.gethostname())
        #errfile = '{}:/tmp/error.$JOB_ID'.format(socket.gethostname())
        logfile = os.path.join(log_dir, 'output.$JOB_ID')
        errfile = os.path.join(log_dir, 'error.$JOB_ID')
        logger.info('Making job DTIPrep for scan:{}'.format(scan_name))
        qjob.run(code=code, logfile=logfile, errfile=errfile)


def process_nrrd(src_dir, dst_dir, protocol_dir, log_dir, nrrd_file):
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
    make_job(src_dir, dst_dir, protocol_dir, log_dir, scan, protocol_file)


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
            rtn, msg = datman.utils.run('DWIConvert --inputVolume {d}/{nrrd} --allowLossyConversion --conversionMode NrrdToFSL --outputVolume {d}/{nii} --outputBVectors {d}/{bvec} --outputBValues {d}/{bval}'.format(
                d=dst_dir, nrrd=nrrd_file, nii=nii_file, bvec=bvec_file, bval=bval_file))
            if rtn != 0:
                logger.error('File:{} failed to convert to NII.GZ\n{}'.format(nrrd_file, msg))


def process_session(src_dir, out_dir, protocol_dir, log_dir, session, **kwargs):
    """Launch DTI prep on all nrrd files in a directory"""
    src_dir = os.path.join(src_dir, session)
    out_dir = os.path.join(out_dir, session)
    nrrds = [f for f in os.listdir(src_dir) if f.endswith('.nrrd')]

    if 'tags' in kwargs:
        tags = kwargs['tags']
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
        process_nrrd(src_dir, out_dir, protocol_dir, log_dir, nrrd)

    # convert output nrrd files to nifti
    convert_nii(out_dir, log_dir)

if __name__ == '__main__':
    parser = argparse.ArgumentParser("Run DTIPrep on a DTI File")
    parser.add_argument("study", help="Study")
    parser.add_argument("--session", dest="session", help="Session identifier")
    parser.add_argument("--outDir", dest="outDir", help="output directory")
    parser.add_argument("--logDir", dest="logDir", help="log directory")
    parser.add_argument("--tag", dest="tags",
        help="Tag to process, --tag can be specified more than once. Defaults to all tags containing 'DTI'",
        action="append")
    parser.add_argument("--quiet", help="Minimal logging", action="store_true")
    parser.add_argument("--verbose", help="Maximal logging", action="store_true")
    args = parser.parse_args()

    if args.quiet:
        logger.setLevel(logging.ERROR)
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    cfg = datman.config.config(study=args.study)

    nii_path = cfg.get_path('nii')
    nrrd_path = cfg.get_path('nrrd')
    meta_path = cfg.get_path('meta')

    if not args.outDir:
        args.outDir = cfg.get_path('dtiprep')

    if not os.path.isdir(args.outDir):
        logger.info("Creating output path:{}".format(args.outDir))
        try:
            os.mkdir(args.outDir)
        except OSError:
            logger.error('Failed creating output dir:{}'.format(args.outDir))
            sys.exit(1)

    if not args.logDir:
        args.logDir = os.path.join(args.outDir, 'logs')

    if not os.path.isdir(args.logDir):
        logger.info("Creating log dir:{}".format(args.logDir))
        try:
            os.mkdir(args.logDir)
        except OSError:
            logger.error('Failed creating log directory"{}'.format(args.logDir))

    if not os.path.isdir(nrrd_path):
        logger.error("Src directory:{} not found".format(nrrd_path))
        sys.exit(1)

    if not args.session:
        sessions = [d for d in os.listdir(nrrd_path) if os.path.isdir(os.path.join(nrrd_path, d))]
    else:
        sessions = [args.session]

    for session in sessions:
        process_session(nrrd_path, args.outDir, meta_path, args.logDir, session, tags=args.tags)

