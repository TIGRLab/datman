init_basic
----------
Usage: init_basic <data_quality> <del_tr>

+ data_quality -- 'low' for poor internal contrast, otherwise 'high'.
+ del_tr -- number of TRs to remove from the beginning of the run.

Works from the raw data in each RUN folder, and prepares the data for the rest of epitome. This is the most basic form of initialization, which:

+ Orients data to RAI
+ Regresses physiological noise using McRetroTS
+ Deletes initial time points (optionally, set to 0 to skip)

To use physiological noise regression, you must have a *.phys (respiration) and *.card (cardiac) file in each RUN folder. This module will automatically perform noise regression if these are available.

For those sites with a BioPak system, epi-physio can parse the outputs to create these *.phys and *.card files.

Prerequisites: None.

Outputs: del
