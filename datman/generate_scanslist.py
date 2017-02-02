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

class Session:
    def __init__(self, p_name, s_id, date, time, a_name, timepoint):
        self.p_name = p_name
        self.s_id = s_id
        self.date = date
        self.time = time
        self.a_name = a_name
        self.timepoint = timepoint

if __name__ == '__main__':
    args = docopt(__doc__)
    curr_dir = os.getcwd()
    study = args["<study_name>"]
    site = args["<site_name>"]
    with open(os.path.join(curr_dir, "scans.csv"),"wb") as outfile:
        writer = csv.writer(outfile, delimiter=" ")
        writer.writerow(["source_name", "target_name", "dicom_PatientName", "dicom_StudyID"])
        archives = glob.glob(os.path.join(args['<archive_dir>'], "*.zip"))
        repeat_set = set()
        session_list = []
        for archive in archives:
            #TODO: --headers=StudyDate,StudyTime and compare these to automatically assign repeats
            header_vals = subprocess.check_output(["archive-manifest.py", "--headers=PatientName,StudyID,StudyDate,StudyTime", "--oneseries", archive])
            reader = csv.reader(header_vals.splitlines())
            #Skip header line
            reader.next()
            patient_vals = reader.next()
            #Order that archive-manifest returns these is not the expected order, thus the unexpected indicies below
            curr_patient = Session(patient_vals[1], patient_vals[3], patient_vals[2], patient_vals[4], os.path.basename(archive).split(".")[0], "01")
            print curr_patient.p_name

            if curr_patient.p_name in repeat_set:
                match = [x for x in session_list if x.p_name == curr_patient.p_name]
                if match[0].date < curr_patient.date or (match[0].date == curr_patient.date and match[0].time < curr_patient.time):
                    match[0].timepoint = "01"
                    curr_patient.timepoint = "02"
                else:
                    match[0].timepoint ="02"
                    curr_patient.timepoint = "01"
            else:
                repeat_set.add(curr_patient.p_name)
            session_list.append(curr_patient)
        for session in session_list:
            writer.writerow([session.a_name, study + "_" + site + "_" + session.p_name.upper() + "_" + session.timepoint + "_01", session.p_name, session.s_id])



