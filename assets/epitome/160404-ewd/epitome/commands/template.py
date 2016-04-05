#!/usr/bin/env python

import epitome as epi
from copy import copy

def run(input_name):
    output = copy(input_name)

    print('\nTemplate module does not actually do anything.')

    try:
        print('\nSelect a letter:')
        opt_list = epi.utilities.selector_list(['a', 'b', 'c'])

        print('\nInput a float:')
        opt_float = epi.utilities.selector_float()

        print('\nInput an int:')
        opt_int = epi.utilities.selector_int()

        print('\nSelect a name:')
        mode = epi.utilities.selector_dict(
                   {'Joseph': ': Master of the Universe',
                    'Dale': ': Assistant Master of the Universe'})

    # if we messed any of these up, we return None
    except ValueError as ve:
        return '', None

    # otherwise we print the command and return it
    line = '. ${{DIR_PIPE}}/modules/pre/template {} {} {} {} {}'.format(
                       input_name, opt_list, opt_float, opt_int, opt_dict)

    return line, output

