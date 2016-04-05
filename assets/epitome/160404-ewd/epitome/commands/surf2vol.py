#!/usr/bin/env python

def run(input_name):
    output = 'ctx'

    print('\nProjecting surface data to volume space.')

    line = '. ${{DIR_PIPE}}/modules/pre/surf2vol {}'.format(input_name)

    return line, output
