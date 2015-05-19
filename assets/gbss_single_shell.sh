#v1.0
#Written by Arash Nazeri
#April 2nd 2015

###############################################################
######### PART 0.1: Making Directories/Copying Files ##########
###############################################################


cd /external/dbgap/pnc_original/38504/NeurodevelopmentalGenomics/
preproc_dir=/scratch/arash/NODDI/singleshell/PNC
#6???????????
#Check 601022643472

export PATH=/projects/arash/Scripts/single_shell_NODDI/:$PATH

for i in 601*; do
(echo $i;
cd $i
mkdir $preproc_dir/$i

cp DTI_35dir/Dicoms/18991230*1.bvec  $preproc_dir/$i/DTI_35dir.bvec

cp DTI_36dir/Dicoms/18991230*1.bvec  $preproc_dir/$i/DTI_36dir.bvec

cp DTI_35dir/Dicoms/18991230*1.bval  $preproc_dir/$i/DTI_35dir.bval

cp DTI_36dir/Dicoms/18991230*1.bval  $preproc_dir/$i/DTI_36dir.bval

cp DTI_35dir/Dicoms/18991230*1.nii.gz  $preproc_dir/$i/DTI_35dir.nii.gz

cp DTI_36dir/Dicoms/18991230*1.nii.gz  $preproc_dir/$i/DTI_36dir.nii.gz

cd $preproc_dir/$i

paste -d" " DTI_35dir.bval DTI_36dir.bval>DWI.bval

fslmerge -t DTI_all DTI_35dir.nii.gz DTI_36dir.nii.gz

Rscript /projects/arash/Scripts/single_shell_NODDI/transpose.R

fsl_sub eddy_correct_bv DTI_all DTI_corr 0

)
done

###############################################################
######### PART 0.2: Preparing for Free Water Mapping ##########
###############################################################

module load python/2.7.9-anaconda-2.1.0-150119
module load python-extras/2.7.9
module load slicer/4.4.0
preproc_dir=/scratch/arash/NODDI/singleshell/PNC

cd $preproc_dir

for i in 601*; do
(cd $i

cp newdirs.dat DWI.bvec
gunzip DTI_corr.nii.gz
python /projects/utilities/nifti2nrrd -i DTI_corr.nii

DWIToDTIEstimation --enumeration WLS --shiftNeg DWI.nhdr estimatedDTIvolume.nrrd estimatedbaselinevolume.nrrd;


#DiffusionWeightedVolumeMasking --otsuomegathreshold 0.3 --removeislands DWI.nhdr estimatedbaselinevolume.nrrd volume_mask.nrrd
bet DTI_corr brain -m -f 0.3
#DWIConvert --inputVolume brain_mask.nii.gz --outputVolume FSL_mask.nrrd --conversionMode FSLToNrrd

echo "$i finished"
)
done

###############################################################
######### PART 0.3: Preparing for Free Water Mapping ##########
###############################################################

module load slicer/4.4.0
preproc_dir=/scratch/arash/NODDI/singleshell/PNC
cd $preproc_dir

#RUN matlab FW mapping
for i in 601*; do
(cd $i/FW
unu 2op x DWI_FW.nhdr 1000 -t float -o mul.nhdr
DWIConvert --inputVolume mul.nhdr --outputVolume mul_FW.nii.gz --conversionMode NrrdToFSL
fslmaths mul_FW -div 1000 FW_map
)
done

###############################################################
#################### PART 0.4: Fitting DTI ####################
###############################################################

preproc_dir=/scratch/arash/NODDI/singleshell/PNC
cd $preproc_dir

for i in 601*; do

(
cd $i

awk '
{
for (i=1; i<=NF; i++)  {
a[NR,i] = $i
}
}
NF>p { p = NF }
END {
for(j=1; j<=p; j++) {
str=a[1,j]
for(i=2; i<=NR; i++){
str=str" "a[i,j];
}
print str
}
}' DWI.bvec > FSL.bvec

dtifit -k DTI_corr.nii -o DTI -r FSL.bvec -b DWI.bval -m brain_mask.nii.gz

)
done

##OPTIONAL: if there is orientation mix up between FW maps and the original DWI files:
##Run the following code (RECHECK the data)!

for i in 601*

do

(
cd $i
fslorient -deleteorient FW_map
fslswapdim FW_map -x y z FW_map
fslorient -setqformcode 1 FW_map
)

done

###############################################################
################## PART 0.5: Fitting NODDI ####################
###############################################################



###############################################################
######### PART 1.1: Making Directories/Copying Files ##########
###############################################################

#making output directory/subdirectories for the analysis

out_dir=/scratch/arash/NODDI/PNC #output directory should be defined here

#rm -rf $out_dir #Deletes the output folder

mkdir ${out_dir}/
mkdir ${out_dir}/FA
mkdir ${out_dir}/CSF
mkdir ${out_dir}/ODI
mkdir ${out_dir}/MNI

sub_dirs=${out_dir}/subdirs #The list of subject directories (in full path)

#Copying files to the output directories (from the list of subject directories). CAUTION: Only the last 4 characters in the folder names will be used as the subject IDs.


for a in 601*

do

cp ${a}/DTI_FA.nii.gz ${out_dir}/FA/${a}.nii.gz ;
 
fslmaths ${a}/FW_map.nii.gz -mul ${a}/brain_mask.nii.gz ${out_dir}/CSF/${a}.nii.gz ;
#cp ${a}/*${string}_odi.nii.gz ${out_dir}/ODI/${a}.nii.gz ;

echo "$a copied"

done

#OPTIONAL: If there is an additional selection criteria to restrict analysis
#Provide only the subject ids (sub_incl) that need to be included in the analysis

cd ${out_dir}/FA

mkdir included
while read line
do

cp ${line}.nii.gz included

done<sub_incl
mkdir all
mv *nii.gz all/
mv included/*gz ./

###############################################################
################## PART 1.2: tbss_1_preproc ###################
###############################################################

#Starting TBSS preproc to discard the high intensity rim of the FA files.
#out_dir=/scratch/arash/NODDI/allPsych

tbss_1_preproc *nii.gz

###############################################################
### PART 1.3: GM/WM PVE estimation/Creating PseudoT1 Images ###
###############################################################

out_dir=/scratch/arash/NODDI/PNC
cd ${out_dir}/FA/FA

#GM probability map is created by subtracting WM and CSF probabilities maps form 1.
module load FSL/5.0.6


for i in *_FA.nii.gz
do

a=`echo $i |cut -f1 -d"_"`
fslmaths ${i} -bin ${a}_mask


Atropos -d 3 -a ${i} -x  ${a}_mask.nii.gz -c[5,1.e-5] -i Kmeans[2] -o [segmentation.nii.gz, ${a}_%02d.nii.gz]

fslmaths  ${a}_02 ${a}_WM_frac

cluster --in=${a}_WM_frac --thresh=0.3 --osize ${a}_temp

fslmaths ${a}_temp -uthr 200 -bin -sub 1 -mul -1 ${a}_temp

#fslmaths ${a:0:4}_mask -mul ${out_dir}/ODI/${a:0:4}.nii ${out_dir}/ODI/${a:0:4}_m.nii

fslmaths ${a}_WM_frac -add ../../CSF/${a} -sub 1 -mul -1 -thr 0 -mul ${a}_mask  ${a}_GM_frac

fslmaths ${a}_WM_frac -mul 2 ${a}_WM_con
fslmaths ${a}_GM_frac -mul 1 ${a}_GM_con
fslmaths ../../CSF/${a} -mul 0 -add ${a}_GM_con -add ${a}_WM_con -mul ${a}_temp ${a}_psuedoT1

done

###############################################################
######### PART 1.4: Applying Warp Fields to Images  ###########
###############################################################

cd ${out_dir}/FA/FA
mkdir ../D1
cp *_psuedoT1.nii.gz ../D1/
cd ../D1
buildtemplateparallel.sh  -d 3 -j 1 -o D1_ -n 0 -s MI -i 8 -m 30x50x20 -t GR -z /projects/arash/NODDI/NODDI-G/newPsych/FA/D1_template.nii.gz  *_psuedoT1.nii.gz
#buildtemplateparallel.sh -c 1 -j 1 -d 3 -o D1_ -n 0 -s MI -i 8 -m 30x50x20 -t GR -z /scratch/arash/NODDI_PD/GBSS/FA/D1_template.nii.gz  p0*.nii.gz
#buildtemplateparallel.sh  -d 3 -j 1 -o D1_ -n 0 -s MI -i 8 -m 30x50x20 -t GR *GM*.nii.gz



###############################################################
######### PART 1.5: Applying Warp Fields to Images  ###########
###############################################################

module load ANTS
out_dir=/scratch/arash/NODDI/PNC
cd ${out_dir}/FA/FA

D1_folder=FA/D1 #Warp field/Affine Transfrom Directory
ref=$out_dir/FA/D1/D1_template.nii.gz

for FAs in  *_FA.nii.gz
do
a=`echo ${FAs} |cut -f1 -d"_"` # No "_" is permitted in the subject IDs

fsl_sub antsApplyTransforms -i ${a}_GM_frac.nii.gz -d 3 -e 0 -n BSpline -r ${ref} -t ${out_dir}/${D1_folder}/*${a}_psuedoT1Warp.nii.gz -t ${out_dir}/${D1_folder}/*${a}_psuedoT1Affine.txt -o ${out_dir}/tmpspace/${a}_GM.nii.gz --float

fsl_sub antsApplyTransforms -i  ${a}_WM_frac.nii.gz -d 3 -e 0 -n BSpline -r ${ref} -t ${out_dir}/${D1_folder}/*${a}_psuedoT1Warp.nii.gz -t ${out_dir}/${D1_folder}/*${a}_psuedoT1Affine.txt -o ${out_dir}/tmpspace/${a}_WM.nii.gz --float

fsl_sub antsApplyTransforms -i  ${out_dir}/fIC/${a}_m.nii.gz -d 3 -e 0 -n BSpline -r ${ref} -t ${out_dir}/${D1_folder}/*${a}_psuedoT1Warp.nii.gz -t ${out_dir}/${D1_folder}/*${a}_psuedoT1Affine.txt -o ${out_dir}/tmpspace/${a}_fIC.nii.gz --float

fsl_sub antsApplyTransforms -i  ${out_dir}/ODI/${a}_m.nii.gz -d 3 -e 0 -n BSpline -r ${ref} -t ${out_dir}/${D1_folder}/*${a}_psuedoT1Warp.nii.gz -t ${out_dir}/${D1_folder}/*${a}_psuedoT1Affine.txt -o ${out_dir}/tmpspace/${a}_ODI.nii.gz --float

fsl_sub antsApplyTransforms -i  ${out_dir}/CSF/${a}.nii.gz -d 3 -e 0 -n BSpline -r ${ref} -t ${out_dir}/${D1_folder}/*${a}_psuedoT1Warp.nii.gz -t ${out_dir}/${D1_folder}/*${a}_psuedoT1Affine.txt -o ${out_dir}/tmpspace/${a}_CSF.nii.gz --float

done
