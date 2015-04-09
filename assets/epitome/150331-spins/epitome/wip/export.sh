#!/bin/bash

# make this into an export module for EPITOME

for p in `ls -d SPINSPHA/*/`; do 
    subj=`basename ${p}`
    echo ${subj}
    cp ${p}/REST/SESS01/func_MNI.RSFC.01.nii.gz ${subj}_MNI.nii.gz   
done
