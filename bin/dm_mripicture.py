#!/usr/bin/env python
"""
Creates MRI axial pictures for custom T-shirt.

Usage:
    mripicture.py [options] <study>
    mripicture.py [options] <study> [-s <subject>]...
    mripicture.py [options] <study> [-s <subject>]... [-t <tag>]

Arguments:
    <study>             Nickname of the study to process

Options:
    -s --subject        Subjects
    -o --output=FOLDER  Output directory
    -t --tag=TAG        Scan tag [default: T1]
    -r --replace        Replace existing files [default: False]
    -h --help           Show this screen
    -q, --quiet         Show minimal output
    -d, --debug         Show debug messages
    -v, --verbose       Show intermediate steps
"""

import os
import glob
import logging
from nilearn import plotting
import numpy as np
from docopt import docopt

import datman.config
import datman.scan


logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))


def get_all_subjects(config):
    nii_dir = config.get_path('nii')
    subject_nii_dirs = glob.glob(os.path.join(nii_dir, '*'))
    all_subs = [os.path.basename(path) for path in subject_nii_dirs]
    return all_subs


def main():
    arguments = docopt(__doc__)
    study = arguments['<study>']
    outdir = arguments['--output']
    subs = arguments['<subject>']
    tag = arguments['--tag']
    overwrite = arguments['--replace']
    quiet = arguments['--quiet']
    debug = arguments['--debug']
    verbose = arguments['--verbose']
    config = datman.config.config(study=study)

    if verbose:
        logger.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)
    if quiet:
        logger.setLevel(logging.ERROR)

    if subs:
        logger.info('Creating pictures for subjects [ {} ] from {} project '
                    'using {} scans.'.format(', '.join(subs), study, tag))
    else:
        subs = get_all_subjects(config)
        logger.info('Creating pictures for all {} subjects from {} project '
                    'using {} scans.'.format(len(subs), study, tag))

    if not outdir:
        outdir = os.path.join(config.get_path('data'), 'tshirt')

    os.makedirs(outdir, exist_ok=True)
    logger.debug('Output location set to: {}'.format(outdir))

    if overwrite:
        logger.info('Overwriting existing files')

    for subject in subs:

        scan = datman.scan.Scan(subject, config)
        tagged_scan = scan.get_tagged_nii(tag)
        idx = np.argmax([ss.series_num for ss in tagged_scan])

        # Set Path
        imgpath = tagged_scan[idx].path
        outpath = os.path.join(outdir, subject + '_T1.pdf')

        if os.path.isfile(outpath) and not overwrite:
            logger.debug('Skipping subject {} as files already exist.'
                         .format(subject))
        else:
            # Output Image
            t1_pic = plotting.plot_anat(imgpath, cut_coords=(-20, -10, 2),
                                        display_mode='x', annotate=False,
                                        draw_cross=False, vmin=100,
                                        vmax=1100, threshold='auto')
            t1_pic.savefig(outpath, dpi=1000)
            logger.debug('Created new brain pictures for subject {} from file '
                         '{} and saved as {}'.format(subject, imgpath, outpath))

    logger.info('Saved all output to: {}'.format(outdir))


if __name__ == "__main__":
    main()
