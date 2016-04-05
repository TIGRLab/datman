#!/usr/bin/env python

import copy

def run(input_name):
    output = copy.copy(input_name) # return output unharmed
    print('\nAdding global correlation calculation')
    line = '. ${{DIR_PIPE}}/modules/pre/gen_gcor {}'.format(input_name)
    return line, output

