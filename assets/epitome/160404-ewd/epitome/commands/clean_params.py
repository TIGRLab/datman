#!/usr/bin/env python

import os
import epitome as epi

def run(expt, clean):

    dir_data = epi.config.find_data()
    dir_pipe = epi.config.find_epitome()

    print('\n *** Adding PARAMS PURGE to the cleanup Queue! ***')

    fname = os.path.join(dir_data, expt, clean)
    os.system('. {}/epitome/modules/cleanup/clean_params >> {}'.format(dir_pipe, fname))

