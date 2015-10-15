## move to analysis folder
for SUBJECT in `ls -d WORKING/${DIR_EXPT}/*/`; do
    SUB=`basename ${SUBJECT}`
    cp WORKING/${DIR_EXPT}/${SUB}/${DATA_TYPE}/func_mni_concat.nii.gz \
       ANALYSIS/${DIR_EXPT}/func_mni_concat_${SUB}.nii.gz
done

## JDV Jan 30