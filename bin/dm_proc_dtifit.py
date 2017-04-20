#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Runs dtifit (on humans). Runs on files with the _DTI_ tag only.

Usage:
    dm-proc-dtifit.py [options]

Options:
    --inputdir DIR     Parent folder holding exported data [default: data/nii]
    --outputdir DIR    Output folder [default: data/dtifit]
    --logdir DIR       Logdir [default: logs]
    --ref_vol N        Registration volume index [default: 0]
    --fa_thresh N      FA threshold for bet [default: 0.3]
    --script PATH      Path to dtifit script. This script should accept the following arguments: dwifile outputdir ref_vol fa_threshold [default: dtifit.sh]
    --tag TAG          A string to filter inputs by [ex. site name]
    --walltime TIME    A walltime to pass to qbatch [default: 0:30:00]
    --debug            Be extra chatty
    --dry-run          Show, don't do
"""


from docopt import docopt
import logging as log
import datman as dm
import datman.utils
import datman.scanid
import os
import tempfile
import time

DRYRUN = False

def main():
    global DRYRUN
    arguments = docopt(__doc__)
    inputdir  = arguments['--inputdir']
    outputdir = arguments['--outputdir']
    logdir    = arguments['--logdir']
    ref_vol   = arguments['--ref_vol']
    fa_thresh = arguments['--fa_thresh']
    script    = arguments['--script']
    TAG       = arguments['--tag']
    walltime  = arguments['--walltime']
    quiet     = arguments['--quiet']
    debug     = arguments['--debug']
    verbose   = arguments['--verbose']
    DRYRUN    = arguments['--dry-run']

    if debug:
        log.basicConfig(level=log.DEBUG)
    else:
        log.basicConfig(level=log.WARN)

    nii_dir = os.path.normpath(inputdir)

    # get the list of subjects
    subjectnames = dm.utils.get_subjects(nii_dir)

    commands = []
    for subjectname in subjectnames:
        inputpath  = os.path.join(nii_dir, subjectname)
        outputpath = os.path.join(outputdir, subjectname)
        files = dm.utils.get_files_with_tag(inputpath, 'DTI', fuzzy = True)
        dwifiles = filter(lambda x: x.endswith('.nii.gz'), files)


        # skip phantoms
        if '_PHA_' in subjectname:
            log.debug('skipping subject {}, is phantom'.format(subjectname))
            continue

        log.debug('{} inputs found with tag "_DTI_" for subject {}'.format(len(dwifiles), subjectname))
        log.debug('processing dwi volumes: {}'.format(dwifiles))
        dm.utils.makedirs(outputpath)

        for dwi in dwifiles:
            # filter even further using an optional input tag
            if TAG and TAG not in dwi:
                log.debug('tag "{}" not found in file {}, skipping'.format(TAG, dwi))
                continue

            stem = os.path.basename(dwi).replace('.nii','').replace('.gz','')

            dtifit_output = '{}/{}_eddy_correct_dtifit_FA.nii.gz'.format(outputpath, stem)
            if os.path.exists(dtifit_output):
                log.debug('output {} exists, skipping'.format(dtifit_output))
            else:
                commands.append('{} {} {} {} {}'.format(
                    script, dwi, outputpath, ref_vol, fa_thresh))

    if commands:
        os.chdir(outputdir)
        log.debug("queueing up the following commands:\n"+'\n'.join(commands))
        jobname = "dm_dtifit_{}".format(time.strftime("%Y%m%d-%H%M%S"))
        with tempfile.NamedTemporaryFile() as tmp:
            tmp.write('\n'.join(commands))
            tmp.flush()
            cmd = "qbatch --walltime {} --logdir {} -N {} {} ".format(
                walltime, logdir, jobname, tmp.name)
            dm.utils.run(cmd, dryrun=DRYRUN)


if __name__ == '__main__':
    main()

