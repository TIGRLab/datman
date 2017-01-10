#!/bin/bash
#
# Finds and removes anything listed on the given blacklist.


function usage() {
echo "
Usage:
    blacklist-rm.sh [options] <datadir> <blacklist>

    All inputs should be full paths.

Arguments:
    <datadir>     The location of the parent directory of all data
                  being managed for this project (e.g.
                  /archive/data-2.0/ANDT/data).

    <blacklist>   is the full path to the blacklist.csv file
                  (e.g. /archive/data-2.0/ANDT/metadata/blacklist.csv).

Options:
    -v            Verbose. Output message indicating name of every file
                  being deleted.
"
exit
}

VERBOSE=0

while getopts "v" OPTION
do
  case $OPTION in
    v)
      VERBOSE=1
      shift
      ;;
  esac
done

if [ $# -ne 2 ]
then
  usage
  exit 1;
fi

data="${1}"
bl="${2}"

# Temp file to store all found file names
tmp=$(mktemp /tmp/series.XXXXXX)

while read series reason
do
  # Skip the first line column headers
  if [ "${series}" != "series" ]
  then
    find $data -name "$series*" >> $tmp
  fi
done < $bl

while read fname
do
  # If blacklist accidentally lists same series twice, will
  # attempt to remove it twice. This stops "file does not exist" error
  if [ -e $fname ]
  then
    if [ $VERBOSE == 1 ]
    then
      echo "Deleting $fname"
    fi
    rm "$fname"
  fi
done < "$tmp"

rm "$tmp"
