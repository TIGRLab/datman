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
    --blacklist FILE    Table listing series to ignore override the default metadata/blacklist.csv
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
import logging
import os
import sys
import tempfile
import shutil
import glob
import platform

import numpy as np
import nibabel as nib

from datman.docopt import docopt
import datman.config
import datman.scanid
import datman.utils

logger = logging.getLogger(__file__)
cfg = None

DRYRUN = False

def main():
    global cfg, DRYRUN
    arguments = docopt(__doc__)
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    quiet = arguments['--quiet']
    DRYRUN = arguments['--dry-run']
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
        add_session_PDT2s(files, images, base_dir)
    else:
        for root, dirs, files in os.walk(nii_dir):
            add_session_PDT2s(files, images, root)

    logger.info('Found {} splittable nifti files with tag "PDT2"'.format(
            len(images)))
    for image in images:
        split(image)

def add_session_PDT2s(files, images, base_dir):
    for f in files:
        try:
            ident, tag, series, desc = datman.scanid.parse_filename(f)
        except datman.scanid.ParseException:
            logger.info('Invalid scanid:{}'.format(f))
            continue
        ext = datman.utils.get_extension(f)
        if tag == 'PDT2' and 'nii' in ext:
            file_path = os.path.join(base_dir, f)
            f_shape = nib.load(file_path).shape
            # this will fail if we load a 3D image, though some 3D images also
            # report the 4th dimension as 1, so we need to check the value
            try:
                if f_shape[3] >= 2:
                    images.append(file_path)
            except:
                link_T2(file_path)

def split(image):

    if DRYRUN:
        logger.info('dry-run: Skipping split of image: {}'.format(image))
        return

    logger.info('Splitting image:{}'.format(image))
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

    with datman.utils.make_temp_directory(prefix='dm2-proc-split-pdt2') as tempdir:
        ret = datman.utils.run("fslsplit {} {}/".format(image, tempdir))
        if ret[0]:
            logger.error('pdt2 split failed in image:{} with fslsplit error:{}'
                         .format(image, ret[1]))
        vols = glob.glob('{}/*.nii.gz'.format(tempdir))
        if len(vols) != 2:
            logger.error('{}: Expected exactly 2 volumes, got: {}'
                         ' in tempfile: {} on system :{}'
                         .format(image, ", ".join(vols), tempdir, platform.node()))
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

def link_T2(pdt2_path):
    """
    This makes a link to a PDT2 file with the 'T2' tag for PDT2s that cant
    actually be split. This makes it explicit that the PDT2 only contains a T2
    series (despite being labeled at PDT2), and makes sure it shows up in the
    papaya viewer on the dashboard.
    """
    pdt2_file = os.path.basename(pdt2_path)
    t2_path = pdt2_path.replace('_PDT2_', '_T2_')
    os.symlink(pdt2_file, t2_path)

if __name__ == "__main__":
    main()
