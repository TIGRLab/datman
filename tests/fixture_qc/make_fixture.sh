# T1
3dresample -dxyz 4 4 4 -inset /archive/data-2.0/SPINS/data/nii/SPN01_CMH_PHA_ADN0001/SPN01_CMH_PHA_ADN0001_T1_02_SagT1-BRAVO-ADNI-ONLY.nii.gz -prefix data/nii/SPN01_CMH_T001/SPN01_CMH_T001_01_01_T1_01_test.nii.gz

# T2
3dresample -dxyz 6 6 6 -inset /archive/data-2.0/SPINS/data/nii/SPN01_CMH_PHA_FBN0001/SPN01_CMH_PHA_FBN0001_DTI60-1000_04_Ax-DTI-60-5-NOASSET.nii.gz -prefix data/nii/SPN01_CMH_T001/SPN01_CMH_T001_01_01_DTI_02_test.nii.gz 
cp /archive/data-2.0/SPINS/data/nii/SPN01_CMH_PHA_FBN0001/SPN01_CMH_PHA_FBN0001_DTI60-1000_04_Ax-DTI-60-5-NOASSET.bvec data/nii/SPN01_CMH_T001/SPN01_CMH_T001_01_01_DTI_02_test.bvec
cp /archive/data-2.0/SPINS/data/nii/SPN01_CMH_PHA_FBN0001/SPN01_CMH_PHA_FBN0001_DTI60-1000_04_Ax-DTI-60-5-NOASSET.bval data/nii/SPN01_CMH_T001/SPN01_CMH_T001_01_01_DTI_02_test.bval

# RST 
3dresample -dxyz 10 10 10 -inset /archive/data-2.0/SPINS/data/nii/SPN01_CMH_PHA_FBN0001/SPN01_CMH_PHA_FBN0001_RST_03_Ax-EPI-RestingState.nii.gz -prefix data/nii/SPN01_CMH_T001/SPN01_CMH_T001_01_01_RST_03_test.nii.gz
fslroi data/nii/SPN01_CMH_T001/SPN01_CMH_T001_01_01_RST_03_test.nii.gz data/nii/SPN01_CMH_T001/SPN01_CMH_T001_01_01_RST_03_truncated.nii.gz 3 60
rm data/nii/SPN01_CMH_T001/SPN01_CMH_T001_01_01_RST_03_test.nii.gz
