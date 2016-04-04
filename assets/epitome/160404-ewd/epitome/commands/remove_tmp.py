#!/usr/bin/env python

import copy

def run(input_name):
    output = copy.copy(input_name) # return output unharmed
    print('\nRemoving temporary files.')
    line = '. ${{DIR_PIPE}}/modules/pre/remove_tmp {}'.format(input_name)
    return line, output

