#!/usr/bin/env python

import epitome as epi

def run(input_name):
    output =  'fix'

    print('\nAdding FSL ICA X-Noisifier calculation.')

    try:
        # set the training data
        print('\nCost function: (see AFNI align_EPI_anat.py for help)')
        train_data = {'Standard.RData' : '= use on "standard" fMRI datasets / analyses: TR=3s, Resolution=3.5x3.5x3.5mm, Session=6mins, 5mm FWHM spatial smoothing)', 
                      'HCP_hp2000.RData' : '= use on "minimally-preprocessed" HCP-like datasets, e.g., TR=0.7s, Resolution=2x2x2mm, Session=15mins, no spatial smoothing, minimal (2000s FWHM) highpass temporal filtering', 
                      'WhII_MB6.RData' : '= use on multiband x6 EPI acceleration: TR=1.3s, Resolution=2x2x2mm, Session=10mins, no spatial smoothing, 100s FWHM highpass temporal filtering', 
                      'WhII_Standard.RData' : '= use on no EPI acceleration: TR=3s, Resolution=3x3x3mm, Session=10mins, no spatial smoothing, 100s FWHM highpass temporal filtering.'}
        train_data = epi.utilities.selector_dict(train_data)

        # set the ICA THRESHOLD WTF IS THIS EVEN
        print('\nThresholding. Default 20. See FSL FIX for help. I just work here (WTF FSL, seriously).')
        threshold = epi.utilities.selector_int()

    # if we messed any of these up, we return None
    except ValueError as ve:
        return '', None

    # otherwise we print the command and return it
    line = ('. ${DIR_PIPE}/epitome/modules/pre/ica_fix ' +
                                      str(input_name) + ' ' +
                                      str(train_data) + ' ' +
                                      str(threshold))
    return line, output
