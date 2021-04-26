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
import nibabel as nib
import numpy as np
from docopt import docopt

import datman.config


def image_cropping(imgpath):
    t1_data = nib.load(imgpath).get_fdata()
    idx = list(range(80, 101, 10))
    t1_slices = t1_data[idx, :, :]
    img = np.transpose(t1_slices, (0, 2, 1))
    img = np.moveaxis(img, 0, 1)
    img = np.reshape(img, (256, -1))
    return img


def get_all_subjects(config):
    qc_dir = config.get_path('nii')
    subject_qc_dirs = glob.glob(os.path.join(qc_dir, '*'))
    all_subs = [os.path.basename(path) for path in subject_qc_dirs]
    return all_subs


def main():
    arguments = docopt(__doc__)
    study = arguments['<study>']
    participant = arguments['<participant>']
    output = arguments['<output>']

    config = datman.config.config(study=study)
    outdir = '/projects/jwong/tshirt'

    if participant:
        subs = [participant]
        print('Creating brain pictures for subject', participant,
              'from', study, 'project.')
    else:
        subs = get_all_subjects(config)
        print('Creating brain pictures for all subjects for',
              study, 'project.')

    if output:
        outdir = output

    if not os.path.exists(outdir):
        os.makedirs(outdir)

    for subject in subs:

        # Set Path
        nii_dir = config.get_path('nii')
        nii_dir = os.path.join(nii_dir, subject, '*Sag-MPRAGE-T1.nii*')
        imgpath = glob.glob(nii_dir)[0]
        outpath = os.path.join(outdir, subject + '_T1.pdf')

        # Crop Image and Remove Direction Label
        img = image_cropping(imgpath)

        # Output Image
        plt.figure(num=None, figsize=(5, 15), dpi=600,
                   facecolor='w', edgecolor='k')
        plt.axis('off')
        plt.imshow(img[::-1], cmap='gray', vmin=100, vmax=1100)
        plt.savefig(outpath, bbox_inches='tight', pad_inches=0)

    print('Saved all output at', outdir)


if __name__ == "__main__":
    main()
