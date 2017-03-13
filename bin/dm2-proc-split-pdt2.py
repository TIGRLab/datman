#!/usr/bin/env python
"""
Splits up a PDT2 image into two images, a PD and a T2 image.

Usage:
    dm2-proc-split-pdt2.py [options] <study>
    dm2-proc-split-pdt2.py [options] <study> <session>

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

Output images are put in the same folder as the input image.

It is expected that the input image is named according to the Scan ID filename
format, and has the tag 'PDT2'. The output PD file has the tag "PD" and the
output T2 file has the tag "PD".

The PD volume is the volume with a higher mean intensity.
"""
from docopt import docopt
import numpy as np
import nibabel as nib
import datman.config
import datman.scanid
import datman.utils
import tempfile
import shutil
import glob
import os.path
import logging
import sys
import platform

logger = logging.getLogger(__file__)
cfg = None


def main():
    global cfg
    arguments = docopt(__doc__)
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    quiet = arguments['--quiet']
    study = arguments['<study>']
    session = arguments['<session>']

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

    formatter = logging.Formatter('%(asctime)s - %(name)s - '
                                  '%(levelname)s - %(message)s')
    ch.setFormatter(formatter)

    logger.addHandler(ch)

    # setup the config object
    logger.info('Loading config')

    cfg = datman.config.config(study=study)

    nii_dir = cfg.get_path('nii')
    images = []
    if session:
        base_dir = os.path.join(nii_dir, session)
        files = os.listdir(base_dir)
        for f in files:
            try:
                ident, tag, series, desc = datman.scanid.parse_filename(f)
            except datman.scanid.ParseException:
                logger.info('Invalid scanid:{}'.format(f))
                continue
            if tag == 'PDT2':
                images.append(os.path.join(base_dir, f))
    else:
        for root, dirs, files in os.walk(nii_dir):
            for f in files:
                try:
                    ident, tag, series, desc = datman.scanid.parse_filename(f)
                except datman.scanid.ParseException:
                    logger.info('Invalid scanid:{}'.format(f))
                    continue
                if tag == 'PDT2':
                    images.append(os.path.join(root, f))

    logger.info('Found {} files with tag "PDT2"'.format(len(images)))
    for image in images:
        split(image)


def split(image):
    logger.info('Spliting image:{}'.format(image))
    ext = datman.utils.get_extension(image)
    try:
        ident, tag, series, desc = datman.scanid.parse_filename(image)
    except datman.scanid.ParseException:
        logger.error('Invalid filename:{}, skipping.'.format(image))
        return

    pd_path = os.path.join(os.path.dirname(image),
                           datman.scanid.make_filename(ident,
                                                       "PD",
                                                       series,
                                                       desc,
                                                       ext))
    t2_path = os.path.join(os.path.dirname(image),
                           datman.scanid.make_filename(ident,
                                                       "T2",
                                                       series,
                                                       desc,
                                                       ext))

    if os.path.exists(pd_path) and os.path.exists(t2_path):
        logger.info('Image:{} is already split, skipping.'.format(image))
        return

    tempdir = tempfile.mkdtemp(prefix='dm2-proc-split-pdt2')

    ret = datman.utils.run("fslsplit {} {}/".format(image, tempdir))
    if ret[0]:
        logger.error('pdt2 split failed in image:{} with fslsplit error:{}'
                     .format(image, ret[1]))
    vols = glob.glob('{}/*.nii.gz'.format(tempdir))
    if len(vols) != 2:
        logger.error('{}: Expected exactly 2 volumes, got: {}'
                     ' in tempfile: {} on system :{}'
                     .format(image, ", ".join(vols), tempdir, platform.node()))

        #shutil.rmtree(tempdir)
        return

    vol0_mean = np.mean(nib.load(vols[0]).get_data())
    vol1_mean = np.mean(nib.load(vols[1]).get_data())

    if vol0_mean > vol1_mean:      # PD should have a higher mean intensity
        pd_tmp, t2_tmp = vols[0], vols[1]
    else:
        t2_tmp, pd_tmp = vols[0], vols[1]

    if not os.path.exists(pd_path):
        shutil.move(pd_tmp, pd_path)
    if not os.path.exists(t2_path):
        shutil.move(t2_tmp, t2_path)

    shutil.rmtree(tempdir)

if __name__ == "__main__":
    main()
