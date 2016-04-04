#!/usr/bin/env python

import copy
import epitome as epi

def run(input_name):
    import numpy as np

    output = 'lowpass'

    print('\nLow-passing each voxel time series.')

    try:
        print('\nInput mask prefix (default = EPI_mask):')
        mask_prefix = raw_input('Mask Prefix: ')
        if mask_prefix == '':
            mask_prefix = 'EPI_mask'

        print('\nWhich filter type would you like to use (see documentation)?')
        filter_list = ['median', 'average', 'kaiser', 'butterworth']
        filter_type = epi.utilities.selector_list(filter_list)

        if filter_type in ['median', 'average']:
            flag = 0

            # ensures input length is odd
            while flag == 0:
                print('\nSelect window length (must be odd, default = 3):')
                lowpass_param = epi.utilities.selector_int()

                if np.remainder(lowpass_param, 2) != 0:
                    flag = 1
                else:
                    print('Window length must be odd!')

        elif filter_type in ['kaiser', 'butterworth']:

            print('\nInput cutoff frequency in Hz (default = 0.1 Hz):')
            lowpass_param = epi.utilities.selector_float()

    # if we messed any of these up, we return None
    except ValueError as ve:
        return '', None

    # otherwise we print the command and return it
    line = '. ${{DIR_PIPE}}/modules/pre/lowpass {} {} {} {}'.format(
               input_name, mask_prefix, filter_type, lowpass_param)
    return line, output
