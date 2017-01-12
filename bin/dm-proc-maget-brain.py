#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Runs MAGeT Brain

Usage:
    dm-proc-maget-brain.py [options] [--tag=TAG]...

Options:
    --inputdir DIR     Parent folder holding exported data [default: data/nii]
    --outputdir DIR    Output folder [default: pipelines/magetbrain]
    --logdir DIR       Logdir [default: logs]
    --tag TAG          A string to filter T1 images by [default: T1]
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
import glob
import os
import re
import tempfile
import time

def main():
    arguments = docopt(__doc__)
    inputdir = arguments['--inputdir']
    outputdir = arguments['--outputdir']
    logdir = arguments['--logdir']
    tags = arguments['--tag']
    quiet = arguments['--quiet']
    debug = arguments['--debug']
    verbose = arguments['--verbose']
    dryrun = arguments['--dry-run']

    loglevel = log.WARN
    if verbose:
        loglevel = log.INFO
    if debug:
        loglevel = log.DEBUG
    if quiet:
        loglevel = log.ERROR
    log.basicConfig(level=loglevel)

    # link new scans
    niidir = os.path.normpath(inputdir)
    outputdir = os.path.normpath(outputdir)

    subjectsdir = os.path.normpath("{}/input/subject".format(outputdir))

    if not os.path.exists(subjectsdir):
        log.error(
            "MAGeT-Brain input subjects dir {} does not exist.\n"
            "Has MAGeT-Brain been setup for this project?".format(subjectsdir))
        sys.exit(1)

    # for tag in tags:
    #     scans = glob.glob("{}/*/*{}*.nii.gz".format(niidir, tag))
    #     for scan in scans:
    #         # append _t1 to the end of the name of the scan
    #         basename = os.path.basename(scan)
    #         extension = ".nii.gz"
    #         filestem = basename[:-len(extension)]
    #         target = os.path.join(subjectsdir, filestem + '_t1' + extension)
    #
    #         if os.path.exists(target):
    #             continue
    #         log.info("linking {} to {}".format(
    #             os.path.relpath(scan, subjectsdir),
    #             target))
    #         if not dryrun:
    #             os.symlink(
    #                 os.path.relpath(scan, subjectsdir),
    #                 target)
    #
    # # run MAGeT-Brain
    # cwd = os.getcwd()
    # os.chdir(outputdir)
    # dm.utils.run("mb.sh -n run", dryrun = dryrun)
    # os.chdir(cwd)

    # link scans back into datman output folders, e.g.
    #   pipelines/magetbrain/SPN01_CMH_0001_01/SPN01_CMH_0001_01_01_T1_blah_labels_hc.nii.gz
    for label in glob.glob("{}/output/labels/majorityvote/*labels*".format(outputdir)):

        # some dirty tricks to clean up the filename
        # we assume it looks something like this:
        #   SPN01_CMH_0026_01_01_T1_02_SagT1Bravo-09mm_t1.nii.gz_labels_hc.nii.gz

        # get scan id up to the timepoint for the output folder
        ident, tag, series, description = dm.scanid.parse_filename(label)
        targetdir = os.path.join(outputdir, "_".join(
            [ident.study, ident.site, ident.subject, ident.timepoint]))

        # extract the label type
        match = re.match(".*_(labels*?.nii)$", label)
        if match is None:
            log.error(
                "Label {} does not look like a label. Wut. Skipping.".format(label))
            continue

        labelext = "_" + match.group(1)

        # build the full filename
        description = description.replace("_t1", "")
        targetname = dm.scanid.make_filename(
            ident, tag, series, description, labelext)
        target = os.path.join(targetdir, targetname)

        # link if it doesn't already exist
        if os.path.exists(target):
            continue

        if not os.path.exists(targetdir):
            os.makedirs(targetdir)

        log.info("linking {} to {}".format(
            os.path.relpath(label, targetdir),
            target))

        if not dryrun:
            os.symlink(
                os.path.relpath(label, targetdir),
                target)

if __name__ == '__main__':
    main()

# vim: ts=4 sw=4:
