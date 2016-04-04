#!/usr/bin/env python

import copy
import epitome as epi

def run(input_name):
    output = copy.copy(input_name) # return output unharmed

    print('\nCalculating linear registration pathways using AFNI.')

    try:
        # get the data-quality option
        print('\nSelect data quality:')
        data_quality = ['low', 'high']
        quality = epi.utilities.selector_list(data_quality)

        # set the cost function option
        print('\nCost function: (see AFNI align_EPI_anat.py for help)')
        cost_fxns = {'ls' : '= Least Squares [Pearson Correlation]',
                     'mi' : '= Mutual Information [H(b)+H(s)-H(b,s)]',
                     'crM' : '= Correlation Ratio (Symmetrized*)',
                     'nmi' : '= Normalized MI [H(b,s)/(H(b)+H(s))]',
                     'hel' : '= Hellinger metric',
                     'crA' : '= Correlation Ratio (Symmetrized+)',
                     'crU' : '= Correlation Ratio (Unsym)',
                     'sp' : '= Spearman [rank] Correlation',
                     'je' : '= Joint Entropy [H(b,s)]',
                     'lss' : '= Signed Pearson Correlation',
                     'lpc' : '= Local Pearson Correlation Signed (Default)',
                     'lpa' : '= Local Pearson Correlation Abs',
                     'lpc+' : '= Local Pearson Signed + Others',
                     'ncd' : '= Normalized Compression Distance',
                     'lpc+zz' : '= Local Pearson Correlation Signed + Magic'}
        cost = epi.utilities.selector_dict(cost_fxns)

        # get registration degrees of freedom
        print('\nDegrees of freedom: (see AFNI align_EPI_anat.py for help)')
        degrees_of_freedom = ['big_move', 'giant_move']
        reg_dof = epi.utilities.selector_list(degrees_of_freedom)

    # if we messed any of these up, we return None
    except ValueError as ve:
        return '', None

    # otherwise we print the command and return it
    line = '. ${{DIR_PIPE}}/modules/pre/linreg_calc_slab_afni {} {} {}'.format(
                                                         quality, cost, reg_dof)
    return line, output
