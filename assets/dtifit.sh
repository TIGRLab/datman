#!/bin/bash
function usage {
echo "
Runs eddy_correct, bet and dtifit on a dwi image

If phantom = 1, we skip eddy_correct.

Usage:
   dtifit.sh <dwifile.nii.gz> <outputdir> <ref_vol> <fa_thresh> <phantom>

"
}
set -e

dwifile="$1"
outputdir="$2"
ref_vol="$3"
fa_thresh="$4"
phantom="$5"

if [ $# -ne 5 ]; then
  usage;
  exit 1;
fi

if [ -z "$FSLDIR" ]; then
    echo "FSLDIR environment variable is undefined. Try again."
    echo "(ﾉಥ益ಥ）ﾉ ┻━┻"
    exit 1;
fi

# input files
stem=$(basename $dwifile .nii.gz)
dwidir=$(dirname $dwifile)
bvec=${dwidir}/${stem}.bvec
bval=${dwidir}/${stem}.bval

# output files
eddy=${outputdir}/${stem}_eddy_correct
b0=${eddy}_b0
bet=${b0}_bet
mask=${bet}_mask
dtifit=${eddy}_dtifit

if [ ${phantom} -ne 1 ]; then
    echo "MSG: analyzing ${dwifile} as a Human."
    input=${eddy}
    if [ ! -e ${eddy}.nii.gz ]; then
        eddy_correct ${dwifile} ${eddy} ${ref_vol}
    fi
else
    echo "MSG: analyzing ${dwifile} as a Phantom."
    input=${dwifile}
fi

if [ ! -e ${b0}.nii.gz ]; then
  fslroi ${input} ${b0} ${ref_vol} 1
fi

if [ ! -e ${bet}.nii.gz ]; then
  bet ${b0} ${bet} -m -f ${fa_thresh} -R
fi

if [ ! -e ${dtifit}_FA.nii.gz ]; then
  dtifit -k ${input} -m ${mask} -r ${bvec} -b ${bval} --save_tensor -o ${dtifit}
fi

if [ "${input}" = "${eddy}" ]; then
    if [ ! -e ${eddy}.bvec ]; then
        cp ${bvec} ${eddy}.bvec
    fi
    if [ ! -e ${eddy}.bval ]; then
        cp ${bval} ${eddy}.bval
    fi
fi

