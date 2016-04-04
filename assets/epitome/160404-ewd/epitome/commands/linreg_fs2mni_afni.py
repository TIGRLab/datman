#!/usr/bin/env python

import copy

def run(input_name):
    output = copy.copy(input_name) # return output unharmed
    print('\nMoving Freesurfer atlases to MNI space using AFNI.')
    line = '. ${DIR_PIPE}/modules/pre/linreg_fs2mni_afni'
    return line, output

