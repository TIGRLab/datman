#!/usr/bin/env python
"""
This run CIVET on stuff

Usage:
  run-proc-CIVET.py [options] <inputdir> <targetdir>

Arguments:
    <inputpath>     Path to input directory (usually a project directory inside /data-2.0)
    <targetdir>     Path to directory that will contain CIVET inputs (links) and outputs
    <prefix>`       Prefix for CIVET input (see details)    `

Options:
  --1T                     Use CIVET options for 1-Telsa data (default = 3T options)
  -v,--verbose             Verbose logging
  -vv                      Erin very verbose style logging (echo's commands before running them)
  --debug                  Debug logging
  -n,--dry-run             Dry run

DETAILS
Requires that CIVET module has been loaded.
"""


## find those subjects in input who have not been processed yet

##make links from the .mnc files in the archive to a temp links folder

##run CIVET and wait
	CIVET_Processing_Pipeline -sourcedir input -targetdir output -prefix ${prefix} -id-file file_ids.txt -run -animal -lobe_atlas -resample-surfaces -granular -VBM -thickness tlink 20 -queue main.q -3Tesla -N3-distance 75
	touch .doneCIVET
## check that CIVET actually ran

##run CIVET QC
CIVET_QC_Pipeline -sourcedir input -targetdir output -prefix ${prefix} -id-file file_ids.txt
##
if [ ! -e /output/QC/civet_${prefix}.html ]
then
	echo "QC ERROR. YOU FAILED."
	sleep 5
	echo "kidding CIVET failed"
fi
