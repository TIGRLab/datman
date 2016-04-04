#!/usr/bin/env python

import epitome as epi

def run(input_name):
    output = 'smooth'

    print('\nSmoothing functional data on a cortical surface.')

    try:
        print('\nInput smoothing kernel FWHM (mm):')
        fwhm = epi.utilities.selector_float()

    # if we messed any of these up, we return None
    except ValueError as ve:
        return '', None

    # otherwise we print the command and return it
    line = '. ${{DIR_PIPE}}/modules/pre/surfsmooth {} {}'.format(input_name, fwhm)

    return line, output
