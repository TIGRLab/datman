despike
-------
Usage: despike <func_prefix>

+ func_prefix -- functional data prefix (eg., smooth in func_smooth).

Removes time series outliers from each voxel. Specifically, this

+ L1 fit a smooth-ish curve to each voxel time series
+ Compute the MAD of the difference between the curve and the data time series.
+ Estimate the standard deviation 'sigma' of the residuals as sqrt(PI/2)*MAD.
+ For each voxel value, define s = (value-curve)/sigma.
+ Values with s > c1 are replaced with a value that yields a modified: 

                    s' = c1+(c2-c1)*tanh((s-c1)/(c2-c1))

      + c1 is the threshold value of s for a 'spike' [default c1=2.5].
      + c2 is the upper range of the allowed deviation from the curve: s=[c1..infinity) is mapped to s'=[c1..c2) [default c2=4].

For more details, see the help of AFNI's 3dDespike.

Prerequisites: init_*.

Outputs: despike.
