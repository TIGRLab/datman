#!/bin/bash
# Liberates nifti sprl scans from the RESOURCES folder
#
# Usage:
#   sprl.sh <datadir>
#
  datadir="$1"
outputdir=$datadir/nii
resources=$datadir/RESOURCES
      tag="VN-SPRL"
   series="00"   # something unused

for i in $resources/*; do
  exam=$(basename $i)
  timepoint=$(echo $exam | sed 's/_..$//g')
  find $i -name '*.nii' | while read sprl; do

    # Take the path to the file, and mangle it so that we have a unique
    # "description" to use in the final name.
    #
    # For instance, the path:
    #
    #     data/RESOURCES/DTI_CMH_H001_01_01/A/B/C/sprl.nii
    #
    # will get mangled like so:
    #
    #   1. Strip off 'data/RESOURCES/DTI_CMH_H001_01_01/'
    #   2. Convert all / to dashes -
    #   3. Convert all _ to dashes -
    #
    # the result is the string:
    #
    #     A-B-C-sprl.nii
    #
    tail=$(echo $sprl | sed "s@.*RESOURCES/${exam}/@@g; s@[/_]@-@g;")

    # The final filename
    filename=${exam}_${tag}_${series}_${tail}
    target=$outputdir/$timepoint/$filename

    if [ ! -e $target ]; then
      ln -s $sprl $target
    fi
  done
done
