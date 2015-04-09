combine_volumes
---------------
Usage: combine_volumes <func1_prefix> <func2_prefix>

+ func1_prefix -- functional data prefix (eg., smooth in func_smooth).
+ func2_prefix -- functional data prefix (eg., smooth in func_smooth).

Combines two functional files via addition. Intended to combine the outputs of `surfsmooth` & `surf2vol` with `volsmooth`, but could be used to combine other things as well. The functional files should not have non-zeroed regions that overlap, or the output won't make much sense.

Prerequisites: Two epi modules with unique output prefixes. Intended to be used to combine the outputs of volsmooth and surfsmooth in a single volume. 
