#!/usr/bin/env python

def run(dir_data, expt, mode):
    output = ''
    print('\nAdding T1-to-MNI registration checking QC to the outputs.')
    line = '. ${DIR_PIPE}/modules/qc/qc_t12mni ${DIR_DATA} ${DIR_EXPT} ${DATA_TYPE}'
    return line, output
