lowpass
-------
Usage: lowpass <func_prefix> <mask_prefix> <filter> <cutoff>

+ func_prefix -- functional data prefix (eg.,smooth in func_smooth). 
+ mask_prefix -- mask data prefix (eg., epi_mask in anat_epi_mask). 
+ filter -- filter type: `median', `average', `kaiser', or `butterworth'. 
+ cutoff -- filter cuttoff: either window length, or cutoff frequency.

This low-passes input data using the specified filter type and cutoff. 

Both `median' and 'average' filters operate in the time domain and therefore, the best cutoff values are odd (and must be larger than 1 to do anything). Time-domain filters are very good at removing high-frequency noise from the data without introducing any phase-shifts or ringing into the time series. When in doubt, a moving average filter with window length of 3 is a decent and conservative choice.

Alternatively, the 'kaiser' and 'butterworth' filters work in the frequency domain and accept a cutoff in Hz (people tend to use a default of 0.1). Both are implemented as bi-directional FIR filters. The kaiser window is high order and permits reasonably sharp rolloff with minimal passband ringing for shorter fMRI time series. The butterworth filter is of low order and achieves minimal passband ringing at the expense of passband roll off (in layman's terms, butterworth filters will retain more high-frequency content than a kaiser filter with equivalent cutoff). The effect of the passband ringing is an empirical question that would be best tested by the User.

Prerequisites: init_*, motion_deskull.

Outputs: lowpass.

