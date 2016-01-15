#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Runs dtifit  (╯°□°）╯︵ ┻━┻

Usage:
    dm-proc-dtifit.py [options]

Options:
    --inputdir DIR     Parent folder holding exported data [default: data/nii]
    --outputdir DIR    Output folder [default: data/dtifit]
    --logdir DIR       Logdir [default: logs]
    --ref_vol N        Registration volume index [default: 0]
    --fa_thresh N      FA threshold for bet [default: 0.3]
    --script PATH      Path to dtifit script.  [default: dtifit.sh]
                       This script should accept the following arguments:
                            dwifile outputdir ref_vol fa_threshold
    --tag TAG          A string to filter inputs by [ex. site name]
    --quiet            Be quiet
    --verbose          Be chatty
    --debug            Be extra chatty
    --dry-run          Show, don't do
"""


from docopt import docopt
import logging as log
import datman as dm
import datman.utils
import datman.scanid
import os

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
    quiet     = arguments['--quiet']
    debug     = arguments['--debug']
    verbose   = arguments['--verbose']
    DRYRUN    = arguments['--dry-run']

    loglevel = log.WARN
    if verbose: loglevel = log.INFO
    if debug:   loglevel = log.DEBUG
    if quiet:   loglevel = log.ERROR
    log.basicConfig(level=loglevel)

    nii_dir = os.path.normpath(inputdir)

    ## get the list of subjects
    subjectnames = dm.utils.get_subjects(nii_dir)

    for subjectname in subjectnames:
        inputpath  = os.path.join(nii_dir, subjectname)
        outputpath = os.path.join(outputdir, subjectname)
        files = dm.utils.get_files_with_tag(inputpath, 'DTI', fuzzy = True)
        dwifiles = filter(lambda x: x.endswith('.nii.gz'), files)

        log.info("Processing DWI volumes: {}".format(dwifiles))

        dm.utils.makedirs(outputpath)

        for dwi in dwifiles:
            if TAG and TAG not in dwi: 
                log.debug("Tag '{}' not found in file {}. Skipping".format(TAG, dwi))
                continue

            stem = os.path.basename(dwi).replace('.nii','').replace('.gz','')

            dtifit_output = outputpath+'/'+stem+'_eddy_correct_dtifit_FA.nii.gz'
            if os.path.exists(dtifit_output):
                log.debug("{} exists. Skipping.".format(dtifit_output))
            else:
                cmd = "qsub -cwd -o {logdir} -j y -V -b y -N dtifit " \
                    "{script} {dwi} {outputdir} {ref} {thresh}".format(
                        logdir = logdir,
                        script = script,
                        dwi = dwi,
                        outputdir= outputpath,
                        ref = ref_vol,
                        thresh = fa_thresh)
                log.debug("exec: {}".format(cmd))
                dm.utils.run(cmd, dryrun=DRYRUN)


if __name__ == '__main__':
    main()

# vim: ts=4 sw=4:
