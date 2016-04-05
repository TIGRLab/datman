#!/usr/bin/env python

import copy

def run(input_name):
    output = copy.copy(input_name) # return output unharmed

    print('\nAdding MELODIC ICA calculation')

    try:
        # masking
        print('\nInput mask prefix (default = EPI_mask):')
        mask_prefix = raw_input('Mask Prefix: ')
        if mask_prefix == '':
            mask_prefix = 'EPI_mask'
    # if we messed any of these up, we return None
    except ValueError as ve:
        return '', None

    # otherwise we print the command and return it
    line = '. ${{DIR_PIPE}}/modules/pre/ica {} {}'.format(input_name, mask_prefix)
    return line, output
