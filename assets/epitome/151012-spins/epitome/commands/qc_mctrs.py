#!/usr/bin/env python

def run(dir_data, expt, mode):
    output = ''

    print('\nAdding Motion Correction TR checking QC to the outputs.')

    line = ('. ${DIR_PIPE}/epitome/modules/qc/qc_mctrs ' + 
             str(dir_data) + ' ' + str(expt) + ' ' + str(mode) + ' ${ID}')

    return line, output

