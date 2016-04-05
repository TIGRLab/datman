despike
-------
Usage: deoblique <func_prefix>

+ func_prefix -- functional data prefix (eg., smooth in func_smooth).

Removes any obliquity from the images, and reslices all images to be on the
same grid as run 1 from each session. This is helpful if your data is in
different shapes for different runs.

For more details, see the help of AFNI's 3dWarp.

Prerequisites: init_*.

Outputs: ob.
