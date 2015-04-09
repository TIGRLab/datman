#!/usr/bin/env python

import os
import epitome as epi

def run(expt, clean):

    dir_data = epi.config.find_data()
    dir_pipe = epi.config.find_epitome()

    print('\n *** Adding DELETE POST MOTION CORRECT to the cleanup Queue! ***')

    fname = os.path.join(dir_data, expt, clean)
    line = ('. ' + str(dir_pipe) + 
            '/epitome/modules/cleanup/del_postmc >> ' + fname)
    os.system(line)
