#!/usr/bin/env python
"""
Splits up a PDT2 image into two images, a PD and a T2 image.

Usage:
    dm-proc-split-pdt2.py <image.nii>...

Output images are put in the same folder as the input image.

It is expected that the input image is named according to the Scan ID filename
format, and has the tag 'PDT2'. The output PD file has the tag "PD" and the
output T2 file has the tag "PD".

The PD volume is the volume with a higher mean intensity.
"""
from docopt import docopt
import numpy as np
import nibabel as nib
import datman as dm
import tempfile
import shutil
import glob
import os.path


def main():
    arguments = docopt(__doc__)
    images = arguments['<image.nii>']

    for image in images:
        split(image)

def split(image):
    try:
        ident, tag, series, description = dm.scanid.parse_filename(image)
    except dm.scanid.ParseException:
        print "{}: not a properly formatted filename".format( image)
        return

    ext = dm.utils.get_extension(image)

    pd_path = os.path.join(os.path.dirname(image),
            dm.scanid.make_filename(ident, "PD", series, description, ext))
    t2_path = os.path.join(os.path.dirname(image),
            dm.scanid.make_filename(ident, "T2", series, description, ext))

    if os.path.exists(pd_path) and os.path.exists(t2_path):
        return

    tempdir = tempfile.mkdtemp()

    dm.utils.run("fslsplit {} {}/".format(image, tempdir))

    vols = glob.glob('{}/*.nii.gz'.format(tempdir))
    if len(vols) != 2:
        print "{}: Expected exactly 2 volumes, got: {}".format(
                image, ", ".join(vols))
        print tempdir
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
