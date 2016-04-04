autocrop
--------
Usage: autocrop <func_prefix>

+ func_prefix -- functional data prefix (eg., smooth in func_smooth).

Removes all-zero regions from the brain in run 1 of the session, and matches the
remaining runs in the session to this crop..

For more details, see the help of AFNI's 3dAutobox.

Prerequisites: init_*.

Outputs: box.
