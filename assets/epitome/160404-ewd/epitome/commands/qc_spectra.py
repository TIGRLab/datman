#!/usr/bin/env python

def run(dir_data, expt, mode):
    output = ''
    print('\nAdding subject-wise regressor spectra QC to the outputs.')
    line = '. ${DIR_PIPE}/modules/qc/qc_spectra ${DIR_DATA} ${DIR_EXPT} ${DATA_TYPE} ${ID}'
    return line, output
