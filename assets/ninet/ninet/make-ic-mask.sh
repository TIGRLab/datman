#!/bin/bash

3dcalc \
    -a IC0000.nii.gz \
    -expr 'astep(a, 3.0) * ispositive(a)' \
    -prefix DMN_POS_IC0000.nii.gz

