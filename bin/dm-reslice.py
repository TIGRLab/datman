#!/usr/bin/env python
"""
This ensures that all data in the input list have the specified X, Y, and Z
dimensions (in number of voxels). If they don't, this will reslice them to the
specied dimensions using AFNI's 3dResample (nearest neighbour interpolation).

If any voxel size is 0, this script will ignore that dimension.

Usage:
    dm-reslice.py <x> <y> <z> [<files>...]

Arguments:
    <x>           voxel size in x dimension (mm).
    <y>           voxel size in y dimension (mm).
    <z>           voxel size in z dimension (mm).
    <files>       list of input files.

DEPENDENCIES

    + python
    + afni

This message is printed with the -h, --help flags.
"""

from glob import glob
from copy import copy
import os, sys
import datman as dm
import nibabel as nib
from datman.docopt import docopt

def get_extension(f):
    if f[-7:] == '.nii.gz':
        return '.nii.gz'
    elif f[-4:] == '.nii':
        return '.nii'
    else:
        return None

def reslice(target, f):
    # work on a copy since we overwrite values
    t = copy(target)

    # attempt to load data voxel sizes
    try:
        data = nib.load(f)
    except:
        print('ERROR: {} is not a valid NIFTI file'.format(f))
        return None
    dx = abs(float(data.affine[0,0]))
    dy = abs(float(data.affine[1,1]))
    dz = abs(float(data.affine[2,2]))
    dims = (dx, dy, dz)

    # Replace nones in target dimensions with file voxel sizes
    for i, val in enumerate(t):
        if val == None:
            t[i] = dims[i]

    # convert target to tuple
    t = tuple(t)

    # if voxel sizes aren't equal between target and file, run 3dresample
    if t != dims:
        ext = get_extension(f)
        if ext == None:
            return None

        orig_name = '{}_ORIG_RESOLUTION{}'.format(f.split(ext)[0], ext)
        if os.path.isfile(orig_name) == False:
            # save the original file with 'ORIG_RESOLUTION' in filename
            os.system('mv {} {}'.format(f, orig_name))
            # NB: defaults to nearest neighbour for now
            os.system('3dresample -dxyz {} {} {} -rmode NN -prefix {} -inset {}'.format(
                t[0], t[1], t[2], f, orig_name))

def main():

    arguments = docopt(__doc__)
    x = abs(float(arguments['<x>']))
    y = abs(float(arguments['<y>']))
    z = abs(float(arguments['<z>']))
    files = arguments['<files>']

    if x == 0: x = None
    if y == 0: y = None
    if z == 0: z = None
    target = [x, y, z]

    # remove all input files with ORIG_RESOLUTION in the name
    files = filter(lambda x: 'ORIG_RESOLUTION' not in x, files)

    # loop through files, reslice as necessary
    for f in files:
        reslice(target, f)

if __name__ == "__main__":
    main()

