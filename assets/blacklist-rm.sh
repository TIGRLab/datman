#!/bin/bash
#
# Finds and removes anything listed on the given blacklist.
#
# Author: Dawn E.A. Smith     Email: Dawn.Smith@camh.ca

function usage() {
echo "
Usage:
    blacklist-rm.sh <datadir> <blacklist>

    All inputs should be full paths.

    <datadir> is the location of the parent directory of all data
    being managed for this project (e.g. /archive/data-2.0/ANDT/data).

    <blacklist> is the full path to the blacklist.csv file
    (e.g. /archive/data-2.0/ANDT/metadata/blacklist.csv).
"
exit
}

if [ $# -ne 2 ]
then
  usage
  exit 1;
fi

data="${1}"
bl="${2}"

# Temp file to store all found file names
tmp=$(mktemp /tmp/series.XXXXXX)

while IFS=" ", read series reason
do
  # Skip the first line column headers
  if [ $series != "series" ]
  then
    find $data -name $series* >> $tmp
  fi
done < $bl

while read fname
do
  echo "Deleting $fname"
  rm "$fname"
done < "$tmp"

rm "$tmp"
