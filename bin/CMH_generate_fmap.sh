#!/usr/bin/env bash

set -x
tmp_dir=$(mktemp -d)

subPath=${tmp_dir}/${4}
if [ ! -d "$subPath" ]; then
  mkdir $subPath
fi

tempPath=${subPath}/tmp/
if [ ! -d "$tempPath" ]; then
  mkdir $tempPath
fi


FM65=$1
FM85=$2


cd $tempPath
#split (pre) fieldmap files
fslsplit ${FM65} split65 -t
bet split650000 65mag -R -f 0.7 -m
fslmaths split650002 -mas 65mag_mask 65realm
fslmaths split650003 -mas 65mag_mask 65imagm

fslsplit ${FM85} split85 -t
bet split850000 85mag -R -f 0.7 -m
fslmaths split850002 -mas 85mag_mask 85realm
fslmaths split850003 -mas 85mag_mask 85imagm

#calc phase difference
fslmaths 65realm -mul 85realm realeq1
fslmaths 65imagm -mul 85imagm realeq2
fslmaths 65realm -mul 85imagm imageq1
fslmaths 85realm -mul 65imagm imageq2
fslmaths realeq1 -add realeq2 realvol
fslmaths imageq1 -sub imageq2 imagvol

#create complex image and extract phase and magnitude
fslcomplex -complex realvol imagvol calcomplex
fslcomplex -realphase calcomplex phasevolume 0 1
fslcomplex -realabs calcomplex $3_magnitude 0 1

#unwrap phase
prelude -a 65mag -p phasevolume -m 65mag_mask -o phasevolume_maskUW

#divide by TE diff in seconds -> radians/sec
fslmaths phasevolume_maskUW -div 0.002 $3_fieldmap

fslcpgeom ${FM65} ${3}_fieldmap.nii.gz -d
fslcpgeom ${FM65} ${3}_magnitude.nii.gz -d

rm $1
rm $2
rm -r ${tmp_dir}
