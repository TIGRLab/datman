#!/usr/bin/env python

import copy

def run(input_name):

    output = copy.copy(input_name)
    print('\nCalculating DVARS.')
    line = '. ${{DIR_PIPE}}/modules/pre/calc_dvars {}'.format(input_name)

    return line, output

