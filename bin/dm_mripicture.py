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
    -h --help           Show this screen
"""

import os
import glob
from nilearn import plotting
import numpy as np
from docopt import docopt

import datman.config
import datman.scan


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
    config = datman.config.config(study=study)

    if subs:
        print('Creating brain pictures for subjects [', ', '.join(subs),
              '] from', study, 'project using', tag, 'scans.')
    else:
        subs = get_all_subjects(config)
        print('Creating brain pictures for all subjects from',
              study, 'project using', tag, 'scans.')

    if not outdir:
        outdir = os.path.join(config.get_path('data'), 'tshirt')

    os.makedirs(outdir, exist_ok=True)

    for subject in subs:

        scan = datman.scan.Scan(subject, config)
        tagged_scan = scan.get_tagged_nii(tag)
        idx = np.argmax([ss.series_num for ss in tagged_scan])

        # Set Path
        imgpath = tagged_scan[idx].path
        outpath = os.path.join(outdir, subject + '_T1.pdf')

        # Output Image
        t1_pic = plotting.plot_anat(imgpath, cut_coords=(-20, -10, 2),
                                    display_mode='x', annotate=False,
                                    draw_cross=False, vmin=100,
                                    vmax=1100, threshold='auto')
        t1_pic.savefig(outpath, dpi=1000)

    print('Saved all output to', outdir)


if __name__ == "__main__":
    main()
