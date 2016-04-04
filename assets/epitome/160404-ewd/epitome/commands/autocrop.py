#!/usr/bin/env python

import epitome as epi

def run(input_name):
    output = 'box'
    print('Removes zeros outside brain on a per session basis.')
    line = '. ${{DIR_PIPE}}/modules/pre/autocrop {}'.format(input_name)
    return line, output

