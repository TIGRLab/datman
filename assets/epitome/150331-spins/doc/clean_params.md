clean_params
------------
Usage: clean_params

If any error occurs while running the pipeline, faulty PARAMS file will be output (typically in 1D format). The presence of these files will confuse future runs of the pipeline, or downstream modules, resulting in cryptic errors. This module ONLY deletes PARAMS files with no content, allowing you to flush your experiment of faulty outputs to permit a re-run of the pipeline.

Prerequisites: clean_params.