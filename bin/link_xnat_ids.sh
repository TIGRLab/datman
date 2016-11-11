#!/bin/bash

# Uses transfer_scan_info.py to update the xnat database with any new
# scan completed surveys. For each scan that was found with alternate ids
# listed, runs dm-link-project-scans.py to create links between the main
# id and its pseudonyms.

function usage() {
  echo "
  Usage:
    link_xnat_id.sh [options] <credentials> <link_file>

  Arguments:
    <credentials>     Path to a file containing the XNAT username,
                      XNAT password, and REDCap token each on a separate line
                      and in that order.
    <link_file>       Path to an external-links.csv file. Will be created if
                      it doesn't exist.

  Options:
    -v                Verbose. Output extra information.
    -c <config_yaml>  Path to the config .yaml file for this site. [default:
                      /archive/code/config/tigrlab_config.yaml]
  "
  exit
}

VERBOSE=0
CONFIG=""

# Handle options
while getopts ":c:v" option
do
  case $option in
    v)
        VERBOSE=1
        ;;
    c)
        CONFIG=$OPTARG
        ;;
    \?)
        echo "ERROR: invalid option -$OPTARG"
        usage
        exit 1
        ;;
    :)
        echo "ERROR: -$OPTARG requires an argument."
        usage
        exit 1
        ;;
  esac
done

# shift to remove all options and their parameters from $@
shift "$((OPTIND-1))"


# Check the expected arguments are present.
if [ $# -ne 2 ]
then
  usage
  exit 1
fi

credentials="$1"
link_file="$2"

# Run transfer_scan_info to move any new redcap information into xnat. Tee the
# log output to the terminal and commands that process only log messages
# related to alt ids and cut out the relevant source and target(s) for linking
transfer_scan_info.py -v ${credentials} 2>&1 | tee /dev/tty | grep "alternate ids" |
    cut -d ":" -f2 | cut -d " " -f1,5- |
  while read subject_id id_list
  do

    if [ $VERBOSE -ne 0 ]
    then
      echo "Creating links for id(s) $id_list pointing to $subject_id data"
    fi

    # Split the id list and store it in the array ids
    IFS=", "
    read -ra ids <<< "$id_list"

    # Run dm-link-project-scans once for each pseudonym in the ids array
    for linked_id in "${ids[@]}"
    do

      if [ ! ${CONFIG} == "" ]
      then

        # Use the provided config-yaml file
        LINK_OUTPUT=`dm-link-project-scans.py \
                      --config-yaml ${CONFIG} \
                      ${link_file} \
                      ${subject_id} \
                      ${linked_id} 2>&1`
      else

        # Run with default project config-yaml file
        LINK_OUTPUT=`dm-link-project-scans.py \
                      ${link_file} \
                      ${subject_id} \
                      ${linked_id} 2>&1`
      fi

      # Suppress any error messages from creating a link that already exists
      echo -n $LINK_OUTPUT | grep -v "File exists"
    done

    # Reset file separator for the while loop's next call to cut
    IFS=" "

  done
