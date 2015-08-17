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

if [ $# -ne 4 ]; then
  echo "Usage: $0 <studyname> <archivedir> <zipdir> <xnatcredfile>"
  exit 1
fi 

if [ ! -e ${XNAT_ARCHIVE} -a ! -e $(dirname ${XNAT_ARCHIVE}) ]; then
  # neither the arc001 folder nor the study folder exist, so something is wrong
  # If the arc001 folder doesn't exist, but the study folder does, then we 
  #   are uploading subjects for the first time. 
  exit 1
fi

for zip in ${ZIPFOLDER}/*.zip; do 
  scanid=$(basename ${zip} .zip)
  if [ -e ${XNAT_ARCHIVE}/${scanid} ]; then 
    continue
  fi
  xnat-upload.py -v --credfile ${CREDFILE} ${STUDYNAME} ${zip} 
done

