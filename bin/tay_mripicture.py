#!/usr/bin/env python
"""
Creates MRI axial pictures for custom T-shirt.

Usage:
    mripicture.py [options] <study>
    mripicture.py [options] <study> <participant>
    mripicture.py [options] <study> <participant> <output>

Arguments:
    <study>             Nickname of the study to process
    <participant>       Full ID of the participant
    <output>            Output Directory

Options:
    -h --help           Show this screen
"""

import os
import glob
import matplotlib.pyplot as plt
from docopt import docopt

import datman.config


def image_cropping(imgpath):
    img = plt.imread(imgpath)[800:1290, :, :]
    img[:, 0:10, :] = 0
    img[:, 205:220, :] = 0
    img[:, 410:425, :] = 0
    img[:, 620:635, :] = 0
    img[:, 830:845, :] = 0
    img[:, 1040:1055, :] = 0
    img[:, 1245:1260, :] = 0
    return img


def get_all_subjects(config):
    qc_dir = config.get_path('qc')
    subject_qc_dirs = glob.glob(os.path.join(qc_dir, '*'))
    all_subs = [os.path.basename(path) for path in subject_qc_dirs]
    return all_subs


def main():

    arguments = docopt(__doc__)
    study = arguments['<study>']
    participant = arguments['<participant>']
    output = arguments['<output>']

    config = datman.config.config(study=study)
    outdir = '/external/mgmt3/imaging/home/kimel/jwong/Tshirt'

    if participant:
        subs = [participant]
    else:
        subs = get_all_subjects(config)

    if output:
        outdir = output

    if not os.path.exists(outdir):
        os.makedirs(outdir)

    for subject in subs:

        # Set Path
        qc_dir = config.get_path('qc')
        png_dir = os.path.join(qc_dir, subject, '/*Sag-MPRAGE-T1.png')
        imgpath = glob.glob(png_dir)[0]
        outpath = os.path.join(outdir, ''.join(subject, '_T1.png'))

        # Crop Image and Remove Direction Label
        img = image_cropping(imgpath)

        # Output Image
        plt.figure(num=None, figsize=(10, 10), dpi=300,
                   facecolor='w', edgecolor='k')
        plt.axis('off')
        plt.imshow(img)
        plt.savefig(outpath, bbox_inches='tight', pad_inches=0)


if __name__ == "__main__":
    main()
