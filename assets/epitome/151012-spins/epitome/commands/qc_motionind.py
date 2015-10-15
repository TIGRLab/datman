#!/usr/bin/env python

def run(dir_data, expt, mode):
    output = ''

    print('\nAdding subject-wise motion QC to the outputs.')

    line = ('. ${DIR_PIPE}/epitome/modules/qc/qc_motionind ' + 
             str(dir_data) + ' ' + str(expt) + ' ' + str(mode) + ' ${ID}')

    return line, output
