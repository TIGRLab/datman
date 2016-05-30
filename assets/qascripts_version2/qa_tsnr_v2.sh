#!/bin/bash
# ---------------------------------------------------------------
# QA_TSNR.sh - compute tSNR metrics from 4D Nifti
#
# M. Elliott - 5/2013
#
# version 2. added Driftpercent to be in percent of gmean rather than absolute
#            added subfield option

# --------------------------
Usage() {
    echo "usage: `basename $0` [-append] [-keep] [-subfield <name>] <4Dinput> [<maskfile>] <resultfile>"
    exit 1
}
# --------------------------

# --- Perform standard qa_script code ---
source qa_preamble.sh

# --- Parse command line inputs ---
if [ $# -lt 2 -o $# -gt 3 ]; then Usage; fi
infile=`imglob -extension $1`
if [ "X$infile" == "X" ]; then echo "ERROR: Cannot find file $1 or it is not a NIFTI file."; exit 1; fi
indir=`dirname $infile` 
inbase=`basename $infile`
inroot=`remove_ext $inbase`
maskfile=""
if [ $# -gt 2 ]; then
    maskfile=`imglob -extension $2`
    shift
fi
resultfile=$2
outdir=`dirname $resultfile`

# --- start result file ---
if [ $append -eq 0 ]; then 
    echo -e "modulename${subfield}\t$0"      > $resultfile
    echo -e "version${subfield}\t$VERSION"  >> $resultfile
    echo -e "inputfile${subfield}\t$infile" >> $resultfile
fi

# --- Check for enough time points ---
nreps=`fslval $infile dim4`
if [ $nreps -lt 5 ]; then 
    echo "ERROR. Need at least 5 volumes to calculate tsnr metrics."
    if [ $append -eq 1 ]; then 
        echo -e "tsnr${subfield}\t-1"   >> $resultfile
        echo -e "gmean${subfield}\t-1" >> $resultfile
        echo -e "drift${subfield}\t-1" >> $resultfile
        echo -e "outmax${subfield}\t-1" >> $resultfile
        echo -e "outmean${subfield}\t-1" >> $resultfile
        echo -e "outcount${subfield}\t-1" >> $resultfile
        echo -e "outlist${subfield}\t-1" >> $resultfile    
    fi
    exit 1
fi

# --- mask ---
if [ "X${maskfile}" = "X" ]; then
    echo "Automasking for tSNR..." 
    maskfile=${outdir}/${inroot}_qamask.nii
    rm -f $maskfile
    3dAutomask -prefix $maskfile $infile  2>/dev/null
fi

# --- tsnr metrics ---
fslmaths $infile -Tmean ${outdir}/${inroot}_mean -odt float

#fslmaths $infile -Tstd  ${outdir}/${inroot}_std  -odt float
imrm ${outdir}/${inroot}_std
3dTstat -stdev -prefix ${outdir}/${inroot}_std.nii $infile 2>/dev/null      # this version of stdev removes slope first! 

fslmaths ${outdir}/${inroot}_mean -mas $maskfile -div ${outdir}/${inroot}_std  ${outdir}/${inroot}_tsnr -odt float
tsnr=`fslstats ${outdir}/${inroot}_tsnr -k $maskfile -m`         # average tSNR
gmean=`fslstats ${outdir}/${inroot}_mean -k $maskfile -m`        # global signal mean

#gsig=`fslstats -t $infile -k $maskfile -m`                     # global signal 
#drift=`3dTstat -slope -prefix - "1D: $gsig"\' 2>/dev/null`     # drift of global signal
fslstats -t $infile -k $maskfile -m > ${outdir}/${inroot}_gsig.1D     # strange bug in 3dTstat - crashes reading from stdin - so use .1D file           
drift=`3dTstat -slope -prefix - ${outdir}/${inroot}_gsig.1D\' 2>/dev/null`  # drift of global signal
driftpercent=`echo "scale=4; $drift*100/$gmean" | bc`

#outlist=`3dToutcount -mask $maskfile $infile 2>/dev/null`   # AFNI temporal outlier metric
#outmean=`3dTstat -mean -prefix - "1D: $outlist"\' 2>/dev/null` 
3dToutcount -mask $maskfile $infile > ${outdir}/${inroot}_outlist.1D 2>/dev/null
outmean=`3dTstat -mean -prefix - ${outdir}/${inroot}_outlist.1D\' 2>/dev/null`

#outmax=`3dTstat -max -prefix - "1D: $outlist"\' 2>/dev/null`  
#outsupra=`1deval -a "1D: $outlist" -expr "ispositive(a-1000)"`   # boolean for outlist > 1000
#outcount=`3dTstat -sum -prefix - "1D: $outsupra"\' 2>/dev/null`  # count number above thresh
#outlist_with_commas=`1deval -1D -a "1D: $outlist" -expr "a"`     # transposes and separates vals with commas

outmax=`3dTstat -max -prefix - ${outdir}/${inroot}_outlist.1D\' 2>/dev/null`  
#outsupra=`1deval -a ${outdir}/${inroot}_outlist.1D -expr "ispositive(a-1000)"`   # boolean for outlist > 1000
#outcount=`3dTstat -sum -prefix - "1D: $outsupra"\' 2>/dev/null`  # count number above thresh
1deval -a ${outdir}/${inroot}_outlist.1D -expr "ispositive(a-1000)" > ${outdir}/${inroot}_outsupra.1D   # boolean for outlist > 1000
outcount=`3dTstat -sum -prefix - ${outdir}/${inroot}_outsupra.1D\' 2>/dev/null`  # count number above thresh
outlist_with_commas=`1deval -1D -a ${outdir}/${inroot}_outlist.1D -expr "a"`     # transposes and separates vals with commas

outlist2=(`echo $outlist_with_commas | tr ":" "\n"`)             # separate from the "1D:" at beginning of string
outlist3=${outlist2[1]}

echo -e "tsnr${subfield}\t${tsnr}"   >> $resultfile
echo -e "gmean${subfield}\t${gmean}" >> $resultfile
echo -e "drift${subfield}\t${drift}" >> $resultfile
echo -e "driftpercent\t${driftpercent}" >> $resultfile
echo -e "outmax${subfield}\t${outmax}" >> $resultfile
echo -e "outmean${subfield}\t${outmean}" >> $resultfile
echo -e "outcount${subfield}\t${outcount}" >> $resultfile
echo -e "outlist${subfield}\t${outlist3}" >> $resultfile

if [ $keep -eq 0 ]; then 
    imrm ${outdir}/${inroot}_tsnr ${outdir}/${inroot}_mean ${outdir}/${inroot}_std
    rm -f ${outdir}/${inroot}_gsig.1D ${outdir}/${inroot}_outlist.1D ${outdir}/${inroot}_outsupra.1D
fi

exit 0

