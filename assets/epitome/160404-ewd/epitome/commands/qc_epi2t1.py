#!/usr/bin/env python

def run(dir_data, expt, mode):
    output = ''
    print('\nAdding EPI-to-T1 registration checking QC to the outputs.')
    line = '. ${DIR_PIPE}/modules/qc/qc_epi2t1 ${DIR_DATA} ${DIR_EXPT} ${DATA_TYPE}'
    return line, output
