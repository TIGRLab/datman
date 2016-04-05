#!/usr/bin/env python

import epitome as epi

def run(input_name):
    output = 'volsmooth'

    print('\nVolumetric smoothing within a defined mask.')

    try:
        print('\nInput mask prefix (default = EPI_mask):')
        mask_prefix = epi.utilities.selector_list(
                          ['EPI_mask', 'EPI_mask_MNI-lin',
                                       'EPI_mask_MNI-nonlin',
                                                   'custom'])
        if mask_prefix == 'custom':
            mask_prefix = raw_input('Custom Mask Prefix: ')
        if mask_prefix == '':
            raise ValueError

        print('\nInput smoothing kernel FWHM (mm):')
        fwhm = epi.utilities.selector_float()

        print('\nSelect mode:')
        mode = epi.utilities.selector_dict(
                   {'normal': ': AFNIs 3dBlurToFWHM',
                    'multimask': ': AFNIs 3dBlurInMask'})

    # if we messed any of these up, we return None
    except ValueError as ve:
        return '', None

    # otherwise we print the command and return it
    line = '. ${{DIR_PIPE}}/modules/pre/volsmooth {} {} {} {}'.format(input_name, mask_prefix, fwhm, mode)

    return line, output

