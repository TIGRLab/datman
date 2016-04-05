#!/usr/bin/env python

import epitome as epi

def run(input_name):
    output = 'ob'
    print('\nRotates images to have no obliquity, matches grids across images.')
    line = '. ${{DIR_PIPE}}/modules/pre/deoblique {}'.format(input_name)
    return line, output

