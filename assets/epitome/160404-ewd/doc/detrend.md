detrend
------
Usage: detrend <func_prefix> <det>

+ func_prefix -- functional data prefix (eg.,smooth in func_smooth). 
+ det -- polynomial order to detrend each voxel against. 

Detrends data with specified polynomial, retaining the mean.

Prerequisites: init_*.

Outputs: detrend, mean. 