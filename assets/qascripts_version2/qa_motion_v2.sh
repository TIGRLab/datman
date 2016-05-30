#!/bin/bash
# ---------------------------------------------------------------
# QA_MOTION.sh - compute motion metrics from 4D Nifti
#
# M. Elliott - 6/2013

# --------------------------
Usage() {
	echo "usage: `basename $0` [-append] [-keep] <4Dinput> <resultfile>"
    exit 1
}
# --------------------------

# --- Perform standard qa_script code ---
source qa_preamble.sh

# --- Parse inputs ---
if [ $# -ne 2 ]; then Usage; fi
infile=`imglob -extension $1`
if [ "X$infile" == "X" ]; then echo "ERROR: Cannot find file $1 or it is not a NIFTI file."; exit 1; fi
indir=`dirname $infile` 
inbase=`basename $infile`
inroot=`remove_ext $inbase`
resultfile=$2
outdir=`dirname $resultfile`

# --- start result file ---
if [ $append -eq 0 ]; then 
    echo -e "modulename\t$0"      > $resultfile
    echo -e "version\t$VERSION"  >> $resultfile
    echo -e "inputfile\t$infile" >> $resultfile
fi

# --- Check for enough time points ---
nreps=`fslval $infile dim4`
if [ $nreps -lt 3 ]; then 
    echo "ERROR. Need at least 3 volumes to calculate motion metrics."
    if [ $append -eq 1 ]; then 
        echo -e "meanABSrms\t-1" >> $resultfile
        echo -e "meanRELrms\t-1" >> $resultfile
        echo -e "maxABSrms\t-1"  >> $resultfile
        echo -e "maxRELrms\t-1"  >> $resultfile
    fi
    exit 1
fi

# --- moco ---
mcflirt -rmsrel -rmsabs -verbose 0 -in $infile -refvol 0 -out $outdir/${inroot}_mc >&/dev/null
meanABSrms=`cat $outdir/${inroot}_mc_abs_mean.rms`
meanRELrms=`cat $outdir/${inroot}_mc_rel_mean.rms`
echo -e "meanABSrms\t$meanABSrms" >> $resultfile
echo -e "meanRELrms\t$meanRELrms" >> $resultfile
mv $outdir/${inroot}_mc_abs.rms $outdir/${inroot}_mc_abs.1D   # strange behavior of 3dTstat - needs file to end in .1D
mv $outdir/${inroot}_mc_rel.rms $outdir/${inroot}_mc_rel.1D
maxABSrms=`3dTstat -max -prefix - $outdir/${inroot}_mc_abs.1D\' 2>/dev/null`  
maxRELrms=`3dTstat -max -prefix - $outdir/${inroot}_mc_rel.1D\' 2>/dev/null`  
echo -e "maxABSrms\t$maxABSrms" >> $resultfile
echo -e "maxRELrms\t$maxRELrms" >> $resultfile

# --- clean up ---
if [ $keep -eq 0 ]; then 
    #imrm $outdir/${inroot}_mc # need to keep this for mean moco image 
    rm -f $outdir/${inroot}_mc_abs.rms $outdir/${inroot}_mc_rel.rms $outdir/${inroot}_mc_abs_mean.rms $outdir/${inroot}_mc_rel_mean.rms
    rm -f $outdir/${inroot}_mc_abs.1D $outdir/${inroot}_mc_rel.1D
    rm -rf $outdir/${inroot}_mc.mat*
fi

exit 0
