#!/usr/bin/env python
"""
Writes timing files for IMOB task.
"""

import numpy as np


def return_timings(data, trial_type):
    """
    Finds all trials matching the string 'trial_type',
    retrieves onset in seconds, and returns them as a list.
    """
    data = filter(lambda d: trial_type in d[0], data)

    onsets = []
    for trial in data:
        onsets.append(trial[5])

    return onsets


def write_afni_timings(task, offset):
    """
    This takes the CSV files supplied with the imitate/observe
    data and returns something that can be fed into AFNI's
    3dDeconvolve.
    """
    # import the original data as a list of lists of strings :D
    data = np.genfromtxt(task + '-timing.csv',
                         skip_header=1,
                         delimiter=',',
                         dtype=(str))
    # find all trial types
    trials = []

    for trial in range(len(data)):
        trials.append(data[trial][0])

    trial_types = np.unique(trials)

    for trial in trial_types:
        # now get the onsets vector
        onsets = return_timings(data, trial)

        # write an output file for this trial_type
        f = open(task + '_event-times_' + trial + '.1D', 'w')

        # this is for AFNI -- blank first line for first run if OB
        if task == 'OB':
            f.write('\n')
        for i in range(len(onsets)):
            on = float(onsets[i]) - offset
            f.write('{o:.2f} '.format(o=on))

        # this is for AFNI -- blank second line for second run if IM
        if task == 'IM':
            f.write('\n')

        print('Finished ' + task + ':' + trial)


def main():
    """
    This is just some slop that lets us seperate each take type.
    """
    task_types = ['IM', 'OB']

    for task in task_types:
        write_afni_timings(task, 12)

    print('Timing files generated. Please have a wonderful day.')


if __name__ == '__main__':
    print('Should be run in the folder with the *-timing.csv files.')
    main()
