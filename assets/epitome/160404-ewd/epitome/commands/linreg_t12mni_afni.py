#!/usr/bin/env python

import epitome as epi

def run(input_name):
    output = 'MNI'

    # give us some feedback
    print('\nResampling input T1 data to MNI space using AFNI.')

    try:
        # get the reslice dimensions
        print('\nSelect target dimensions (isotropic mm):')
        dims = epi.utilities.selector_float()

    # if we messed any of these up, we return None
    except ValueError as ve:
        return '', None

    # otherwise we print the command and return it
    line = '. ${{DIR_PIPE}}/modules/pre/linreg_t12mni_afni {} {}'.format(input_name, dims)

    return line, output
