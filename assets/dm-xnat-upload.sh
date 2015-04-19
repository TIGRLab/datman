#!/bin/bash
# Upload exam archive zips to XNAT
#
# Usage:
#   upload.sh studyname xnatstudyarchive zipfolder credfile
#
# Example: 
#   upload.sh \ 
#       ASDD \
#       /mnt/xnat/spred/archive/ASDD/arc001 \
#       /archive/data-2.0/ASDD/data/dicom \
#       /archive/data-2.0/ASDD/metadata/xnat-credentials
#   
STUDYNAME="${1}"
XNAT_ARCHIVE="${2}"
ZIPFOLDER="${3}"
CREDFILE="${4}"

if [ ! -e ${XNAT_ARCHIVE} ]; then
  exit 1
fi

for zip in ${ZIPFOLDER}/*.zip; do 
  scanid=$(basename ${zip} .zip)
  if [ -e ${XNAT_ARCHIVE}/${scanid} ]; then 
    continue
  fi
  xnat-upload.py -v --credfile ${CREDFILE} ${STUDYNAME} ${zip} 
done

