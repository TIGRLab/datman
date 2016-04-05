trdrop
------
Usage: trscrub <func_prefix> <head_size> <FD_thresh> <DV_thresh> <mode>

+ func_prefix -- functional data prefix (eg.,smooth in func_smooth). 
+ head_size -- head radius in mm (def. 50 mm). 
+ thresh_FD -- censor TRs with $\Delta$ motion > $x$ mm (def. 0.3 mm). 
+ thresh_DV -- censor TRs with $\Delta$ GS change > $x$ \% (def. [1000000](http://upload.wikimedia.org/wikipedia/en/1/16/Drevil_million_dollars.jpg). 
+ mode -- 'drop' removes TRs from output file, 'interp' replaces TRs with a linear interpolate between the TR before and after the removed region.

This removes motion-corrupted TRs from fMRI scans and outputs modified versions for connectivity analysis (mostly). By default, DVARS regression is set of OFF by using a very, very high threshold. The interp version is best used before lowpass filtering, and is the only reasonable option if you are analyzing some form of task data.

Prerequisites: init_*, motion_deskull.

Outputs: scrubbed

