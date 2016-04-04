#!/usr/bin/env python

import copy

def run(input_name):
    output = copy.copy(input_name) # return output unharmed
    print('\nCalculates a thalamus mask using the freesurfer segmentation.')
    line = '. ${DIR_PIPE}/modules/pre/make_thal_mask'
    return line, output

