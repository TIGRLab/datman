fsrecon.py
----------
Usage: fsrecon.py <data_directory> <experiment> <modality> <cores>

+ data_directory -- full path to your MRI/WORKING directory.
+ experiment -- name of the experiment being analyzed.
+ modality -- image modality to import (normally T1).
+ cores -- number of cores to dedicate (one core per run).

This sends each subject's T1s through the Freesurfer pipeline. It uses multiple T1s per imaging session, but does not combine them between sessions. Data is output to the dedicated `FREESURFER` directory, and should be exported to the MRI analysis folders using `fsexport.py`.
