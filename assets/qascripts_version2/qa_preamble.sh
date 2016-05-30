# -------------------------------------------------------------
# Common startup code for all qa_*_v#.sh scripts
#
#   MElliott 6/2103
# -------------------------------------------------------------

# --- Set AFNI/FSL stuff ---
export FSLOUTPUTTYPE=NIFTI
export AFNI_AUTOGZIP=NO
export AFNI_COMPRESSOR=

# --- get path to other scripts called by this one ---
OCD=$PWD
EXECDIR=`dirname $0`
if [ "X${EXECDIR}" != "X" ]; then
    cd ${EXECDIR}; EXECDIR=${PWD}/; cd $OCD # makes path absolute, leaves blank if none (i.e. this script is in the PATH)
fi

# --- Get version number of this script ---
scriptname=`basename $0`
parts=(`echo $scriptname | tr "_." "\n"  | tr -d "v"`)
VERSION=${parts[2]}

# --- Check switches ---
if [ $# -lt 1 ]; then Usage; fi
append=0
keep=0
example_dicom=""
subfield=""
check_switches=1
while [ $check_switches -eq 1 ]; do
  case $1 in 
    -append)            append=1; shift ;;
    -keep)              keep=1;   shift ;;
    -example_dicom)     example_dicom=$2; shift;  shift ;;
    -subfield)          subfield=$2; shift;  shift ;;
    -*)                 echo "Unrecognized switch: $1"; exit 1 ;;
     *)                 check_switches=0 ;; # done with switches
  esac
done
if [ $keep -eq 1 ]; then keepswitch="-keep"; else keepswitch=""; fi
