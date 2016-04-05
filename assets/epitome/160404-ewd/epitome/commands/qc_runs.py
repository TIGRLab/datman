#!/usr/bin/env python

def run(dir_data, expt, mode):
    output = ''
    print('\nAdding NIFTI dimension-checking QC to the outputs.')
    line = '. ${DIR_PIPE}/modules/qc/qc_runs ${DIR_DATA} ${DIR_EXPT}'
    return line, output
