#!/usr/bin/env python

import epitome as epi
import os

def run(input_name):
    output =  'fix'

    print('\nAdding FSL ICA X-Noisifier calculation.')

    try:
        # set the training data
        print('\nCost function: (see AFNI align_EPI_anat.py for help)')
        train_data = {'Standard.RData' : '= use on "standard" fMRI datasets / analyses: TR=3s, Resolution=3.5x3.5x3.5mm, Session=6mins, 5mm FWHM spatial smoothing)',
                      'HCP_hp2000.RData' : '= use on "minimally-preprocessed" HCP-like datasets, e.g., TR=0.7s, Resolution=2x2x2mm, Session=15mins, no spatial smoothing, minimal (2000s FWHM) highpass temporal filtering',
                      'WhII_MB6.RData' : '= use on multiband x6 EPI acceleration: TR=1.3s, Resolution=2x2x2mm, Session=10mins, no spatial smoothing, 100s FWHM highpass temporal filtering',
                      'WhII_Standard.RData' : '= use on no EPI acceleration: TR=3s, Resolution=3x3x3mm, Session=10mins, no spatial smoothing, 100s FWHM highpass temporal filtering.',
                      'autohawko.RData' : '(in assests) = trained using Colin Hawko (of TIGRLab)\'s labels of noisy real data / TR=3s, Resolution=3x3x3mm, Session~5mins, no spatial smoothing, 100s FWHM highpass temporal filtering.'}
        train_data = epi.utilities.selector_dict(train_data)

        # set the ICA THRESHOLD WTF IS THIS EVEN
        print('\nThresholding. We normally go with 20. See FSL FIX for help')
        threshold = epi.utilities.selector_int()

        print('\nHave fix regress out motion paramaters?:')
        motionregress = epi.utilities.selector_list(['off', 'on'])

        print('\nDelete intermediate files?:')
        fixcleanup = epi.utilities.selector_list(['off', 'on'])

    # if we messed any of these up, we return None
    except ValueError as ve:
        return '', None

    # convet the train_data to the full path to the training data...
    if train_data in ['Standard.RData', 'HCP_hp2000.RData',
                        'WhII_MB6.RData', 'WhII_Standard.RData']:
        train_data_path = os.path.join(epi.config.find_fix(),
                                'training_files',train_data)
    if train_data in ['autohawko.RData']:
        train_data_path = os.path.join(epi.config.find_epitome(),
                        'assets','fix_training_data',train_data)

    # otherwise we print the command and return it
    line = '. ${{DIR_PIPE}}/modules/pre/ica_fix {} {} {} {} {}'.format(
            input_name, train_data_path, threshold, motionregress, fixcleanup)
    return line, output
