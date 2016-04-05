#!/usr/bin/env python

import epitome as epi

def run(input_name):
    output = 'deskull'
    print('\nMotion correction and brain masking.')

    try:

        # masking
        print('\nEPI masking: acquisition dependent')
        mask_list = ['loosest', 'loose', 'normal', 'tight']
        masking = epi.utilities.selector_list(mask_list)

        # mask method
        print('\nEPI masking: method')
        mask_method = epi.utilities.selector_list(['FSL', 'AFNI'])

    # if we messed any of these up, we return None
    except ValueError as ve:
        return '', None

    # otherwise we print the command and return it
    line = '. ${{DIR_PIPE}}/modules/pre/motion_deskull {} {} {}'.format(
                                             input_name, masking, mask_method)

    return line, output
