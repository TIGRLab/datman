#!/usr/bin/env python

import copy

def run(input_name):
    output = copy.copy(input_name) # return output unharmed
    print('\nCopying the registration for T1 to MNI152_T1_2mm template from HCP_DATA.')
    line = '. ${DIR_PIPE}/modules/hcp/t12mni_fsl_export'
    return line, output

