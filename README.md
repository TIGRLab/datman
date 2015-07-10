datman
------
A python project containing useful functions for managing imaging data from
collection through analysis.

+ [Introduction](#introduction)
+ [Quality Control](#quality-control)
+ [CAMH XNAT Documentation](http://imaging-genetics.camh.ca/programs/xnat/)

For instructions on how to use the CAMH XNAT server, our file naming convetions, etc., please see CAMH XNAT Documentation. DATMAN relies on these conventions being followed.

Introduction
------------

**definitions**

 - Exam/Scan: A series of MRI acquisitions completed in one sitting. 
 - Series/Acquisition: A single image of a subject in one modality
 - Exam archive: The raw data taken during an exam. For MRI, this could be a
   folder structure of DICOM images, or a tarball/zipfile of that same data, 
 - Type tag: A short, keyword that distinguishes a kind of acquisition from
   other kinds in a study. For instance, T1, DTI, REST. These type tags are
   used in the file naming and follow-on processing scripts to identify
   acquisitions without having to parse their headers/description/etc... 

**dependencies**

+ [NiNet](https://github.com/josephdviviano/ninet) for some NIFTI-handling functionsi and analysis.
+ [SciPy, NumPy, Matplotlib](http://www.scipy.org/stackspec.html) for general analysis.
+ [NiBabel](For NIFTI reading/writing.)

**setup**

For interfacing with xnat, datman requires that each project's `Define Prearchive Settings` under `Manage` be set to 'All image data will be placed into the archive automatically and will overwrite existing files. Data which doesn't match a pre-existing project will be placed in an 'Unassigned' project.'

Your environment needs to be set up as so:

+ Add datman to your `PYTHONPATH`.
+ Add datman/bin to your `PATH`.
+ Add datman/assets to your `PATH`, `PYTHONPATH`, & `MATLABPATH`.
+ Set `DATMAN_ASSETS` to point to datman/assets.

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

Quality Control
---------------
We've built a number of quality control pipelines to help track quality across sites and image modalities. The outputs are `.PDF` files typically containing many plots. Below is a brief description on the outputs of each.

**T1-contrast, BOLD contrast, B0 contrast**

A set of axial slices designed to give an overview of the sequence. This is useful for identifying geometric distortions in the image, severe inhomogeneities, or orientation errors.

**Head Motion**

For functional scans. Uses the motion-correction realignment parameters to calculate the framewise displacement (in mm/TR) of the head. This calculation currently assumes a head radius of 50mm to convert degrees of rotation into millimeters of displacement. The red line denotes the cut-off for TR scrubbing suggested in [1] resting-state scans. Subjects with a lot of TRs above this line may need to be removed from downstream analysis.

> [1] Spurious but systematic correlations in functional connectivity MRI networks arise from subject motion. Jonathan D. Power et al. 2011. Neuroimage 59:3.

**SFNR**

Shows voxel-wise signal-to-fluctuation noise ratio, a measure from the fBIRN QC pipeline.

**Slice/TR Abnormalities**

Shows the average and standard deviation of all values within each acquisition slice across all TRs. This allows us to visualize large deviations from the average mean value on a slice wise basis. This can happen on only some slices, and can help detect the presense of localized artifacts that occour during acquisition or reconstruction. The slice-dependent effects are particularly obvious in the DTI sequences, where particular gradient directions may be more susceptible to spike-noise.

**DTI**

A compliment to the slice/TR abnormalities plot for DTI sequences, this shows a single coronal slice through the center of the acquisition for each TR. This can also help us identify artifactual spatial patterns that might not be obvious in the slice/TR plot.

**Phantom Scatterplots: ADNI**

This tracks the T1 weighted value across the 5 primary ROIs in the ADNI phantom, and the T1 ratios between each of the higher ones with the lowest one. For more information, please see http://www.phantomlab.com/library/pdf/magphan_adni_manual.pdf.

**Phantom Scatterplots: fBIRN fMRI**

This uses the fBIRN pipeline to define % signal fluctuation, linear drift, signal to noise ratio, signal-to-fluctuation noise ratio, and radius of decorrelation. For more information, please see [1], http://www.ncbi.nlm.nih.gov/pubmed/16649196.

> [2] Report on a multicenter fMRI quality assurance protocol. Friedman L et al. 2006. J Magn Reson Imaging 23(6).

--- 

[Who dat](https://www.youtube.com/watch?v=OIjsSu_I4So) 
[Who dat](https://www.youtube.com/watch?v=5X0uSltBHhs)
[Who dat](https://www.youtube.com/watch?v=6o9dXLNuXic)
[Who dat](https://www.youtube.com/watch?v=7flZvy0uRV0)
[Who dat](https://www.youtube.com/watch?v=4-I1DNLbYR8)
[Who dat](https://www.youtube.com/watch?v=iKmYvXS7wM4)
[Who dat](https://www.youtube.com/watch?v=0bd2emv9fR4)
[Who dat](https://www.youtube.com/watch?v=FW5Q6Nt6cx0)
[Who dat man?](https://www.youtube.com/watch?v=whNGgz8e-8o)


