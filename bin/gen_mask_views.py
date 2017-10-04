#!/usr/bin/env python

import PIL
import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont
import numpy as np
import nibabel as nib
from future.utils import viewitems
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="""
                    Takes a t1 and a mask file, produces a montage of slices
                    for each label in mask.
                    Currently a maximum of 12 mask regions can be uniqualy
                    identified.
                    """
    )
    parser.add_argument('-t1',
                        help="Full path to a T1 file in nifti format",
                        action="store",
                        required=True)
    parser.add_argument('--mask', '-m',
                        help="Full path to a Mask in nifti format",
                        action="store",
                        required=True)
    parser.add_argument('--output', '-o',
                        help="Full path to the output png file",
                        action="store")
    parser.add_argument('--title', '-t',
                        help="A title to put on top of the image",
                        action="store")
    parser.add_argument('--keep_orientation',
                        help="Dont try to reorient the inputs to standard space",
                        action="store_false",
                        default=True)
    # parser.add_argument('--slices', '-s',
    #                     help="Number of slices for each axis",
    #                     action="store",
    #                     type=int,
    #                     default=3)

    args = parser.parse_args()
    out_file = args.output

    t1 = load_nifti(args.t1, reorient=args.keep_orientation)
    mask = load_nifti(args.mask)

    assert t1.shape == mask.shape

    montage = process_regions(mask, t1)

    if args.title:
        montage = add_text(montage, args.title, 'title')

    if args.output:
        montage.save(out_file)
    else:
        montage.show()


def process_region(mask, t1, colors, region):
    centroid = get_region_centroid(mask, region)
    dim_count = len(centroid)
    t1_slices = get_slices(t1, centroid)
    mask_slices = get_slices(mask, centroid)

    t1_slices = [normalise_slice(slice) for slice in t1_slices]
    t1_slices = [get_4d(slice, [0, 1, 2]) for slice in t1_slices]

    mask_slices = [make_slice_mask_colored(slice, colors, transparancy=0.5)
                   for slice in mask_slices]

    overlays = [create_overlay_image(t1_slices[i], mask_slices[i])
                for i in range(dim_count)]

    txt_str = 'Region:{} Coords:{}'.format(region, np.array2string(centroid))
    montage = create_montage(overlays, direction='h')

    montage = add_text(montage, txt_str, 'caption')
    return(montage)


def process_regions(mask, t1, ignore_vals=[0]):
    """
    Locates the center of each mask region
    extracts sagittal, horizontal and occipital cuts centered
    on each regions
    returns a list where each item represents a region
    """
    regions = np.unique(mask)
    regions = [i for i in regions if i not in ignore_vals]
    colors = map_label_colors(regions)
    images = [process_region(mask, t1, colors, region) for region in regions]
    montage = create_montage(images, direction='v')
    return(montage)


def get_slices(arr, centroid):
    """
    Returns 2d slices from an nd array centered on centroid
    """
    assert len(centroid) == arr.ndim
    assert arr.ndim == 3
    slices = [np.rot90(np.rollaxis(arr, i)[v, ...])
              for i, v in enumerate(centroid)]
    return(slices)


def get_region_centroid(mask, region):
    """
    Returns the x,y,z coordinates representing the center
    of a box containing points in mask that match region
    """
    coords = np.column_stack(np.where(mask == region))
    coords = np.apply_along_axis(np.mean, 0, coords).round()
    coords = np.uint8(coords)
    return(coords)


def create_montage(images, direction='h', text=None):
    """
    Paste a bunch of PIL images into a montage
    """
    assert direction in ['h', 'v']
    black = (0, 0, 0)
    white = (255, 255, 255)
    widths = map((lambda x: x.width), images)
    heights = map((lambda x: x.height), images)

    left, upper, right, lower = 0, 0, 0, 0
    if direction == 'h':
        final_width = reduce((lambda x, y: x + y), widths)
        final_height = max(heights)

        isize = (final_width, final_height)
        montage = PIL.Image.new('RGBA', isize, black)

        for img in images:
            upper = (final_height - img.height) / 2
            right = left + img.width
            lower = upper + img.height
            montage.paste(img, (left, upper, right, lower))
            left = right
            upper = 0
    else:
        final_height = reduce((lambda x, y: x + y), heights)
        final_width = max(widths)

        isize = (final_width, final_height)
        montage = PIL.Image.new('RGBA', isize, black)

        for img in images:
            right = left + img.width
            lower = upper + img.height
            montage.paste(img, (left, upper, right, lower))
            upper = lower

    return montage


def make_slice_mask_colored(slice_mask, colors, transparancy=0.5):
    """
    Takes a n x m array and a color dict
    returns an n x m x 4 array
    >>> target = np.zeros((5,5,4))
    >>> colors = {1:(64,128,256)}
    >>> target[2,2,0:3] = colors[1]
    >>> mask = np.zeros((5,5))
    >>> mask[2,2] = 1
    >>> mc = make_slice_mask_colored(mask, colors)
    >>> mc == target
    True
    """
    slice_mask_4d = get_4d(slice_mask, transparancy=transparancy)

    for key, value in viewitems(colors):
        matches = (slice_mask == key)
        if matches.any():
            slice_mask_4d[matches, 0] = value[0]
            slice_mask_4d[matches, 1] = value[1]
            slice_mask_4d[matches, 2] = value[2]
    return(slice_mask_4d)


def load_nifti(fname, reorient=True):
    """
    Loads a nifti image,
    returns a ndarray()
    """
    img = nib.load(fname)
    if reorient:
        img = nib.as_closest_canonical(img)
    return(img.get_data())


def map_label_colors(array, ignore_vals=[0]):
    """
    Maps unique values in a mask to colors
    Colors from 12-class paired
    http://colorbrewer2.org/#type=qualitative&scheme=Paired&n=12
    """
    colset = [(166, 206, 227),
              (31, 120, 180),
              (178, 223, 138),
              (51, 160, 44),
              (251, 154, 153),
              (227, 26, 28),
              (253, 191, 111),
              (255, 127, 0),
              (202, 178, 214),
              (106, 61, 154),
              (255, 255, 153),
              (177, 89, 40)]
    levels = np.unique(array)
    levels = [l for l in levels if l not in ignore_vals]
    if len(levels) == 0:
        return
    if len(levels) == 1:
        return({levels[0]: colset[0]})
    step = len(colset) / (len(levels) - 1)

    col_idx = np.arange(0, len(colset), step)
    colors = {}
    for idx in range(len(levels)):
        colors[levels[idx]] = colset[col_idx[idx]]
    return colors


def get_slices_indices(nii, axis, count):
    """
    Returns count slices from an array
    """
    assert axis >= 0 and axis < 3, "Invalid axis"
    # roll the nifti so the dimension of interest is at the frontend
    nii = np.rollaxis(nii, axis)
    count = count + 2
    valid_slices = np.where([r.any() for r in nii])[0]
    step = int(np.ceil(len(valid_slices) / float(count)))
    slices = [valid_slices[idx] for idx in range(0, len(valid_slices), step)]
    slices = slices[1:-1]
    return(slices)


def get_4d(slice, copylayers=[], transparancy=0):
    """
    Creates a 4d array from a 2d slice
    if copylayers, duplicates slice into layers
    >>> s = np.ones((5,5))
    >>> new_s = get_4d(s)
    >>> assert new_s == np.zeros((5,5,4))
    >>> new_s = get_4d(s, (0,1,2))
    >>> assert new_s[:,:,0] == np.ones((5,5))
    >>> assert new_s[:,:,3] == np.zeros((5,5))
    """
    assert slice.ndim < 3
    img = np.zeros(slice.shape)
    img = img[:, :, np.newaxis]
    img = np.repeat(img, 4, 2)
    transparancy = 255 - (255 * transparancy)
    img[:, :, -1] = transparancy
    for layer in copylayers:
        img[:, :, layer] = slice
    return(img)


def convert_slice_to_RGBA(slice):
    """
    Converts a 2d slice into a 4d RGBA image
    """
    img = get_4d(slice)
    img = PIL.Image.fromarray(img)


def create_overlay_image(background, foreground):
    """
    Takes two n x m x 4 arrays, converts them to PIL images and merges them
    """
    bg = PIL.Image.fromarray(np.uint8(background), mode='RGBA')

    fg = PIL.Image.fromarray(np.uint8(foreground), mode='RGBA')
    img = PIL.Image.alpha_composite(bg, fg)

    return(img)


def normalise_slice(slice, max_val=255):
    """
    Normalises values to between 0 & max_val
    """
    slice = slice - slice.min()
    slice = slice / np.float(slice.max())
    slice = slice * max_val
    return(slice)


def add_text(img, text, type):
    """
    Add text to a PIL image
    currently 2 formats are accepted:
    type = 'caption' - small text, bottom left corner
    type = 'title' - larger text, top middle
    """
    assert type in ['title', 'caption']
    txt = PIL.Image.new('RGBA', img.size, (255,255,255,0))
    d = PIL.ImageDraw.Draw(txt)

    if type == 'caption':
        size = 10
    else:
        size = 25

    try:
        fnt = PIL.ImageFont.truetype('FreeSans.ttf', size=size)
    except IOError:
        fnt = PIL.ImageFont.load_default()

    font_size = fnt.getsize(text)

    if type == 'caption':
        tupper = txt.height - font_size[1] - 20
        tleft = 10
    elif type == 'title':
        tupper = 10
        tleft = (img.width / 2) - (font_size[0] / 2)

    d.text((tleft, tupper), text, font=fnt, fill=(255, 255, 255, 255))
    img = PIL.Image.alpha_composite(img, txt)

    return(img)

if __name__ == '__main__':
    main()
