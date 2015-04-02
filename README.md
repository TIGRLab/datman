datman
------
<<<<<<< HEAD
A python project containing useful functions for managing imaging data from
collection through analysis.


### Some definitions

 - Exam/Scan: A series of MRI acquisitions completed in one sitting. 
 - Series/Acquisition: A single image of a subject in one modality
 - Exam archive: The raw data taken during an exam. For MRI, this could be a
   folder structure of DICOM images, or a tarball/zipfile of that same data, 
 - Type tag: A short, keyword that distinguishes a kind of acquisition from
   other kinds in a study. For instance, T1, DTI, REST. These type tags are
   used in the file naming and follow-on processing scripts to identify
   acquisitions without having to parse their headers/description/etc... 
=======
The development branch of a python project containing useful functions for managing imaging data from collection through analysis.

Depends on :

+ [NiNet](https://github.com/josephdviviano/ninet) for some NIFTI-handling functionsi and analysis.
+ [SciPy, NumPy, Matplotlib](http://www.scipy.org/stackspec.html) for general analysis.
+ [NiBabel](For NIFTI reading/writing.)

setup
-----

For interfacing with xnat, datman requires that each project's `Define Prearchive Settings` under `Manage` be set to 'All image data will be placed into the archive automatically and will overwrite existing files. Data which doesn't match a pre-existing project will be placed in an 'Unassigned' project.'

modules
-------

**utils**

General file-handling utilities.

**web**

An interface between our data and gh-pages to create online data reports.

**module**

A set of commands for interacting with GNU module.

**img**

A set of commands for handling imaging data.

**behav**

A set of commands for handling behavioural data. 
>>>>>>> dev

--- 

[Who's dat?](https://www.youtube.com/watch?v=OIjsSu_I4So) 
[Who dat](https://www.youtube.com/watch?v=5X0uSltBHhs)
[Who dat](https://www.youtube.com/watch?v=6o9dXLNuXic)
[Who dat](https://www.youtube.com/watch?v=7flZvy0uRV0)
[Who dat](https://www.youtube.com/watch?v=4-I1DNLbYR8)
[Who dat](https://www.youtube.com/watch?v=iKmYvXS7wM4)
[Who dat](https://www.youtube.com/watch?v=0bd2emv9fR4)
[Who dat](https://www.youtube.com/watch?v=FW5Q6Nt6cx0)
[Who dat man?](https://www.youtube.com/watch?v=whNGgz8e-8o)


