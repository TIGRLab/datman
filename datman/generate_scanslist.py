#!/usr/bin/env python
"""
Given a directory to unprocessed archives (directly from MR server), generate a scans.csv file.
Assumptions:
1. All sessions are named incorrectly and thus should all be added to the scans.csv file.
2. No follow-up or repeat scans. If you notice duplicate patient names, you must compare the dates manually. This will be done automatically in a future update.

Usage:
	generate_scanslist.py <archive_dir> <study_name> <site_name>


"""

import os
import glob
import csv
from docopt import docopt
import subprocess

if __name__ == '__main__':
    args = docopt(__doc__)
    curr_dir = os.getcwd()
    with open(os.path.join(curr_dir, "scans.csv"),"wb") as outfile:
    	writer = csv.writer(outfile, delimiter=" ")
    	writer.writerow(["source_name", "target_name", "dicom_PatientName", "dicom_StudyID"])
    	archives = glob.glob(os.path.join(args['<archive_dir>'], "*.zip"))
    	for archive in archives:
    		#TODO: --headers=StudyDate,StudyTime and compare these to automatically assign repeats
    		header_vals = subprocess.check_output(["archive-manifest.py", "--oneseries", archive])
    		reader = csv.reader(header_vals.splitlines())
    		#Skip header line
    		reader.next()
    		patient_vals = reader.next()
    		p_name = patient_vals[1]
    		s_id = patient_vals[5]
    		a_name = os.path.basename(archive).split(".")[0]
    		writer.writerow([a_name, args["<study_name>"] + "_" + args["<site_name>"] + "_" + p_name.upper() + "_01_01", p_name, s_id])



