#!/bin/bash
# Fetch newest scans from the MRFTP server
# Usage: 
#   pull.sh user@host zipglob outputdir
#
# Example: 
#   pull.sh ASDD@mr-ftp ASDD*MR/* data/zips
#
host="${1}"
zipglob="${2}"
outputdir="${3}"
runsftp="sftp -q -b- ${host}"

echo "ls -1 ${zipglob}" | $runsftp | grep -v sftp | \
  while read scan; do 
    if [ ! -e ${outputdir}/$(basename $scan) ]; then
      echo "get $scan ${outputdir}" | $runsftp
    fi
  done 
