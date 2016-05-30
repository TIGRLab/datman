#!/bin/bash
# ---------------------------------------------------------------
# QA_PCASL.sh - do QA on pCASL 4D Nifti
#   return tab delimited QA metrics file
#
# M. Elliott - 6/2013

# --------------------------
Usage() {
	echo "usage: `basename $0` [-append] [-keep] [-example_dicom <dicomfile>] <4Dinput> [<maskfile>] <resultfile>"
    exit 1
}
# --------------------------

# --- Perform standard qa_script code ---
source qa_preamble.sh

# --- Parse inputs ---
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

# --- start result file ---
if [ $append -eq 0 ]; then 
    echo -e "modulename\t$0"      > $resultfile
    echo -e "version\t$VERSION"  >> $resultfile
    echo -e "inputfile\t$infile" >> $resultfile
fi

# --- Hand off to BOLD module ---
${EXECDIR}qa_bold_v${VERSION}.sh -append $keepswitch $infile $maskfile $resultfile

# --- Get info from dicom file ---
if [ "X${example_dicom}" != "X" ]; then
	dcminfo=(`dicom_hdr -sexinfo $example_dicom 2>/dev/null | grep "flReferenceAmplitude"`)
	np=${#dcminfo[@]}
	txref=${dcminfo[$np-1]}
	echo -e "TXref\t$txref" >> $resultfile
fi

# --- put the TR in ---
TR=`fslval $infile pixdim4`
echo -e "TR\t$TR" >> $resultfile

exit 0
