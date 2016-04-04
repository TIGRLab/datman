#!/usr/bin/env python

import epitome as epi

def run(input_name):
    output = 'tshift'

    print('\nSlice time correction.')

    try:
        # get the slice timing
        print('\nSlice-timing pattern: (see AFNI 3dTshift for more help)')
        t_patterns = {'alt+z' : '= alternating in the plus direction',
                      'alt+z2' : '= alternating, starting at slice #1',
                      'alt-z' : '= alternating in the minus direction',
                      'alt-z2' : '= alternating, starting at slice #nz-2',
                      'seq+z' : '= sequential in the plus direction',
                      'seq-z' : '= sequential in the minus direction'}
        slice_timing = epi.utilities.selector_dict(t_patterns)

    # if we messed any of these up, we return None
    except ValueError as ve:
        return '', None

    # otherwise we print the command and return it
    line = '. ${{DIR_PIPE}}/modules/pre/slice_time_correct {} {}'.format(
                                                        input_name, slice_timing)
    return line, output
