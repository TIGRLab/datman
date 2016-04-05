#!/usr/bin/env python

import epitome as epi

def run():
    output = 'del'
    print('\nInitializing basic fMRI pre-processing.')

    try:
        # get the data-quality option
        print('\nSelect data quality:')
        quality = epi.utilities.selector_list(['low', 'high'])

        # get the number of TRs to delete
        print('\nNumber of TRs to delete:')
        deltr = epi.utilities.selector_int()

    # if we messed any of these up, we return None
    except ValueError as ve:
        return '', None

    line = '. ${{DIR_PIPE}}/modules/pre/init_basic {} {}'.format(quality, deltr)
    return line, output
