#!/bin/bash

# Slicer breaks everything else so dm_xnat_extract calls this to load
# it only as it's needed

module load slicer/4.4.0
DWIConvert -i "${1}" --conversionMode DicomToNrrd -o "${2}".nrrd --outputDirectory "${3}"
module unload slicer/4.4.0
