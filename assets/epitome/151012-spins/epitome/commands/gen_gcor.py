#!/usr/bin/env python

import copy 

def run(input_name):
    output = copy.copy(input_name) # return output unharmed
    
    print('\nAdding global correlation calculation')

    line = ('. ${DIR_PIPE}/epitome/modules/pre/gen_gcor ' + str(input_name))

    return line, output
