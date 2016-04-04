#!/usr/bin/env python

import copy

def run(input_name):
    output = copy.copy(input_name) # return output unharmed
    print('\nCalculating nonlinear registration pathways using FSL.')
    line = '. ${DIR_PIPE}/modules/pre/nonlinreg_calc_fsl'
    return line, output

