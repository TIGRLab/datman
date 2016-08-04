#!/usr/bin/env python
"""
Runs QAP on anatomical and functional scans

Usage: 
    dm-proc-qap.py [options]

Options: 
    --inputdir DIR       Parent folder holding exported data [default: data/nii]
    --outputdir DIR      Output folder [default: pipelines/qap]
    --logdir DIR         Logdir [default: logs]
                         
    --anat_config FILE   Anatomical pipeline configuration file 
                         [default: metadata/qap_anat_config.yml]
                         
    --func_config FILE   Funcational pipeline configuration file 
                         [default: metadata/qap_func_config.yml]
                         
    --anat_tags TAGS     A comma separated list of strings to filter anatomical
                         inputs by [default: T1]
                         
    --func_tags TAGS     A comma separated list of strings to filter functional 
                         inputs by [default: RST] 
                         
    --walltime TIME      A walltime to pass to qbatch for each subject processing
                         [default: 1:00:00]
                         
    --quiet              Be quiet
    --verbose            Be chatty
    --debug              Be extra chatty
    --dry-run            Show, don't do

"""

import collections
import datman
import docopt
import glob
import logging as log
import tempfile
import time
import os
import yaml


def main():
    arguments = docopt.docopt(__doc__)
    inputdir = arguments['--inputdir']
    outputdir = arguments['--outputdir']
    logdir = arguments['--logdir']
    anat_config = arguments['--anat_config']
    func_config = arguments['--func_config']
    anat_tags = arguments['--anat_tags'].split(',')
    func_tags = arguments['--func_tags'].split(',')
    walltime = arguments['--walltime']
    quiet = arguments['--quiet']
    debug = arguments['--debug']
    verbose = arguments['--verbose']
    dryrun = arguments['--dry-run']

    # configure logging
    loglevel = log.WARN
    if verbose:
        loglevel = log.INFO
    if debug:
        loglevel = log.DEBUG
    if quiet:
        loglevel = log.ERROR
    log.basicConfig(level=loglevel)

    # kickflip to create a recursive defaultdict, and register it with pyyaml
    # this makes making nested yaml dictionaries easy
    tree = lambda: collections.defaultdict(tree)
    yaml.add_representer(collections.defaultdict,
                         yaml.representer.Representer.represent_dict)

    # build mapping between tag and qap scan types
    image_types = dict([(tag, 'anatomical_scan') for tag in anat_tags] +
                       [(tag, 'functional_scan') for tag in func_tags])

    # generate the QAP commands
    commands = []
    for path in glob.glob('{}/*/*.nii.gz'.format(inputdir)):
        filename = os.path.basename(path)

        # exclude scans that don't match that tags
        try:
            scanid, kind, series, description = datman.scanid.parse_filename(
                filename)
            if kind not in image_types.keys():
                continue
        except datman.scanid.ParseException, e:
            continue

        image_type = image_types[kind]
        subjectid = scanid.get_full_subjectid()

        # graphviz doesn't like - in names
        filestem = filename.replace(".nii.gz", "").replace('-', '_')

        # the following bit of defaultdict magic sets up a chunk of yaml for
        # for QAP that specifies this scan, like so:
        #
        # SPN01_CMH_0001:
        #   01:
        #     functional_scan:
        # SPN01_CMH_0001_01_01_RST_07_Ax_RestingState:
        # blah/blah/SPN01_CMH_0001_01/SPN01_CMH_0001_01_01_RST_07_Ax-RestingState.nii.gz
        config = tree()
        config[subjectid][scanid.timepoint][image_type][filestem] = path

        suboutputdir = os.path.join(
            outputdir, scanid.get_full_subjectid_with_timepoint())
        if not os.path.exists(suboutputdir):
            os.makedirs(suboutputdir)

        subjectlistfile = os.path.join(suboutputdir, filestem + '.yml')
        if not dryrun:
            open(subjectlistfile, 'w').write(
                yaml.dump(config, default_flow_style=False))

        if image_type == 'functional_scan':
            commands.append("qap_functional_spatial.py --sublist {} {}".format(
                subjectlistfile, func_config))
            commands.append("qap_functional_temporal.py --sublist {} {}".format(
                subjectlistfile, func_config))
        if image_type == 'anatomical_scan':
            commands.append("qap_anatomical_spatial.py --sublist {} {}".format(
                subjectlistfile, anat_config))

    if commands:
        log.debug("queueing up the following commands:\n" + '\n'.join(commands))
        fd, path = tempfile.mkstemp()
        os.write(fd, '\n'.join(commands))
        os.close(fd)

        jobname = "dm_qap_{}".format(time.strftime("%Y%m%d-%H%M%S"))
        rtn, out, err = datman.utils.run(
            'qbatch --logdir {logdir} -N {name} --walltime {wt} {cmds}'.format(
                logdir=logdir,
                name=jobname,
                wt=walltime,
                cmds=path), dryrun=dryrun)

        if rtn != 0:
            log.error("Job {} submission failed. Output follows.".format(jobname))
            log.error("stdout: {}\nstderr: {}".format(out, err))

if __name__ == '__main__':
    main()
