#!/usr/bin/env python

def run(dir_data, expt, mode):
    output = ''

    print('\nAdding EPI-to-T1 registration checking QC to the outputs.')

    line = ('. ${DIR_PIPE}/epitome/modules/qc/qc_epi2t1 ' + 
             str(dir_data) + ' ' + str(expt) + ' ' +  str(mode))

    return line, output
