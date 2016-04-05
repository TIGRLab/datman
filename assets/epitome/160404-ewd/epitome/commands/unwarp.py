#!/usr/bin/env python

import epitome as epi

def run(input_name):
    output = 'unwarped'
    print('\nUsing fieldmap to unwarp EPI data (INSPECT OUTPUTS).')

    try:
        print('\nSelect scanner platform.')
        method = epi.utils.selector_list(['SIEMENS', 'GE'])
        print('\nSelect unwarp direction.')
        unwarpdir = ['x', 'x-', 'y', 'y-', 'z', 'z-']
        unwarpdir = epi.utils.selector_list(unwarpdir)

        if method == 'SIEMENS':
            print('\nInput dwell time: (default: 0.00133)')
            dwell = epi.utils.selector_float()
            print('\nInput delta TE in ms: (default: 2.46)')
            deltate = epi.utils.selector_float()
            mag = 0; real = 0; imag = 0

        elif method == 'GE':
            print('\nInput dwell time: (default: 0.000684)')
            dwell = epi.utils.selector_float()
            print('\nInput delta TE in seconds: (default: 0.002)')
            deltate = epi.utils.selector_float()
            print('\nMagnitude image sub-brick (0 = first volume)')
            mag = epi.utils.selector_int()
            print('\nReal image sub-brick (0 = first volume)')
            real = epi.utils.selector_int()
            print('\nImaginary image sub-brick (0 = first volume)')
            imag = epi.utils.selector_int()

    # if we messed any of these up, we return None
    except ValueError as ve:
        return '', None

    line = '. ${{DIR_PIPE}}/modules/pre/unwarp {} {} {} {} {} {} {} {}'.format(
                 input_name, method, unwarpdir, dwell, deltate, mag, real, imag)

    return line, output

