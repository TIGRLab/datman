#!/usr/bin/env python

import epitome as epi

def run(input_name):
    output = 'scaled'
    print('\nTime series scaling and/or normalization.')

    try:
        # normalize
        print('\nTime series normalization method: (see documentation for help)')
        norm_dict = {'pct' : ': 1% = 1, normalize to 100 mean voxelwise',
                     'scale':': scale run mean to = 1000, arbitrary units'}
        normalization = epi.utilities.selector_dict(norm_dict)

    # if we messed any of these up, we return None
    except ValueError as ve:
        return '', None

    # otherwise we print the command and return it
    line = '. ${{DIR_PIPE}}/modules/pre/scale {} {} '.format(
                                               input_name, normalization)

    return line, output
