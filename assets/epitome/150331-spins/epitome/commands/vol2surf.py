#!/usr/bin/env python

def run(input_name):
    output = 'surface'

    print('\nProjecting data to cortical surface.')

    line = ('. ${DIR_PIPE}/epitome/modules/pre/vol2surf ' + str(input_name))

    return line, output
