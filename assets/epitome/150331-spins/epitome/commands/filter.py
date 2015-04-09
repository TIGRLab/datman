#!/usr/bin/env python

import epitome as epi

def run(input_name):
    output = 'filtered'

    print('\nAdding filter module.')

    try:
        print('\nSet detrend order:')
        polort = epi.utilities.selector_int()

        print('\nStandard regressors on? (White matter, csf):')
        std = epi.utilities.selector_list(['off', 'on'])

        print('\nGlobal mean regression on?:')
        gm = epi.utilities.selector_list(['off', 'on'])

        print('\nAnaticor on? (15 mm local white matter regression):')
        anaticor = epi.utilities.selector_list(['off', 'on'])

        print('\nCompcor on? (Regress top PCs of white matter, csf):')
        compcor = epi.utilities.selector_list(['off', 'on'])

        if compcor == 'on':
            print('\nCompcor on. How many components per ROI?')
            compnum = epi.utilities.selector_int()
        else:
            compnum = 'na'

        print('\nDraining vessel regression on?:')
        dv = epi.utilities.selector_list(['off', 'on'])

    # if we messed any of these up, we return None
    except ValueError as ve:
        return '', None

    # otherwise we print the command and return it
    line = ('. ${{DIR_PIPE}}/epitome/modules/pre/filter {input_name} {polort} '
               '{std} {gm} {anaticor} {compcor} {compnum} {dv}').format(
                              input_name=str(input_name),
                              polort=str(polort),
                              std=std,
                              gm=gm,
                              anaticor=anaticor,
                              compcor=compcor,
                              compnum=compnum,
                              dv=dv)

    return line, output
