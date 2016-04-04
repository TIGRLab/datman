#!/usr/bin/env python

import epitome as epi

def run(input_name):
    output = 'despike'
    print('\nRemoving time series outliers.')
    line = '. ${{DIR_PIPE}}/modules/pre/despike {}'.format(input_name)
    return line, output
