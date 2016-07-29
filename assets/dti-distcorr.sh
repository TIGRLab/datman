#!/bin/bash
#
# Generalized Distortion Correction 
#
# NB: FNIRT selected for non-linear registration
# David Rotenberg, david.rotenberg@camh.ca

function usage() {
echo "
Usage: 
    dti-distcor.sh <dwifile.nii.gz> <t2file.nii.gz> <outputdir>
    
    All inputs should be full paths, files must be nifti.

DEPENDENCIES

    + FSL 5.0.6 or above.
"
exit
}

# ensure we got the right number of inputs
if [ $# -ne 3 ]; then 
  usage;
  exit 1;
fi

dwi="${1}"
t2="${2}"
outputdir="${3}"

dwi_base=$(basename $dwi .nii.gz)

# Run standard FSL eddy_correct and masking
eddy_correct ${dwi} eddy_corr 0 
echo "betting eddy-corrected ${dwi}"
bet eddy_corr ${dwi_base}_mask -m -f 0.3 

# Calculate eddy-corrected FA (useful for comparrisons and as standard output)
dtifit \
    -k eddy_corr \
    -m ${dwi_base}_mask_mask \
    -r ${dwi_base}.bvec \
    -b ${dwi_base}.bval \
    -o ${dwi_base}_Fdti

# Split Uncorrected Original Volume
echo "Splitting DWI Volume"
fslsplit ${dwi}

# Copy First bzero as reference volume
# For registrations
cp vol0000.nii.gz bzero_base.nii.gz

# Perform all affine registrations: Motion + Eddy-Current Correction
for vol in vol*.nii.gz; do 
	  base=$(basename $vol .nii.gz)
	  echo "Affine Registration of volume: $vol"
	  flirt \
        -in $vol \
        -ref bzero_base.nii.gz \
        -o "$base"_reg.nii.gz \
        -nosearch \
        -paddingsize 1 \
        -omat "$base"_mat.xfm 
done

echo "Creating b0 average ${dwi_base}"
fslmaths \
    vol0000_reg.nii.gz \
    -add vol0001_reg.nii.gz \
    -add vol0002_reg.nii.gz \
    -add vol0003_reg.nii.gz \
    -add vol0004_reg.nii.gz \
    -add vol0005_reg.nii.gz \
    -div 5 \
    ${dwi_base}_average
fslmaths \
    ${dwi_base}_average.nii.gz \
    -mul ${dwi_base}_mask_mask.nii.gz \
    ${dwi_base}_average_brain

echo 'Linear Registration of T2 to b0 average'
cp T2.nii.gz ${dwi_base}_T2.nii.gz
bet ${dwi_base}_T2.nii.gz T2.nii.gz -f 0.2
cp  T2.nii.gz  ${dwi_base}_T2.nii.gz
flirt \
    -in ${dwi_base}_T2.nii.gz \
    -dof 9 \
    -ref  ${dwi_base}_average_brain \
    -out ${dwi_base}_T2_to_b0avg.nii.gz \
    -omat ${dwi_base}_T2_to_b0avg.mat

ref_image=${dwi_base}_T2_to_b0avg.nii.gz
float_image=${dwi_base}_average_brain
output_xfm=${dwi_base}_FNIRTxfm.nii.gz

echo "Non-linear transformation using mutual information of subject ${dwi_base}"
fnirt \
    --ref=${ref_image} \
    --in=${float_image} \
    --iout=FNIRT_NL.nii \
    --fout=field_xyz.nii

# Recombine Field with null XX and ZZ components:
fslsplit field_xyz.nii NL
mv NL0001.nii.gz Y_deform.nii.gz
cp Y_deform.nii.gz X.nii.gz
cp Y_deform.nii.gz Z.nii.gz
fslmaths Z.nii.gz -mul 0 ZZ.nii.gz -odt float
fslmaths X.nii.gz -mul 0 XX.nii.gz -odt float
fslmerge \
    -t ${dwi_base}_FNIRTxfmInverseWarp_FNIRT.nii.gz \
    XX.nii.gz \
    Y_deform.nii.gz \
    ZZ.nii.gz

# Merge Registered Data "Revised Eddy-Current"
mkdir REG
fslmerge -t EDDY vol00*reg.nii.gz
mv *reg* REG/

for i in vol00*.nii.gz; do 
    bet ${i} ${i} -f 0.1; 
done

echo 'Running: Applywarp on DWI volumes'
for j in vol00*.nii.gz; do 
	base=$(basename ${j} .nii.gz)
	applywarp \
      -i ${j} \
      -o warped_${j} \
      -r ${j} \
      --premat=${base}_mat.xfm \
      -w ${dwi_base}_FNIRTxfmInverseWarp_FNIRT.nii.gz
done


echo 'Merging epicorr images'
fslmerge \
    -t ${dwi_base}_dwi_epicorr_FNIRT warped_vol00*.nii.gz 
rm *vol00*

echo "Betting Corrected Image"
bet \
    ${dwi_base}_dwi_epicorr_FNIRT.nii.gz \
    ${dwi_base}_dwi_epicorr_brain2 \
    -m -f 0.2

echo "Calculating Corrected FA"
dtifit \
    -k ${dwi_base}_dwi_epicorr_FNIRT.nii.gz \
    -m ${dwi_base}_dwi_epicorr_brain2_mask.nii.gz \
    -r *.bvec \
    -b *.bval -\
    o ${dwi_base}_epicorr_Fdti

echo "Cleaning"
rm -rf REG
