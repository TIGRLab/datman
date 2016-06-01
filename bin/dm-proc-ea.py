#!/usr/bin/env python
"""
This analyzes empathic accuracy behavioural data for all subjects. 

It submits a job for each subject to be processed (see dm-proc-ea-sub.py)

Usage:
    dm-proc-ea.py [options] <project> <script> <assets>

Arguments: 
    <project>           Full path to the project directory containing data/.
    <script>            Full path to an epitome-style script.
    <assets>            Full path to an assets folder containing 
                             EA-timing.csv, EA-vid-lengths.csv.

Options:
    --walltime TIME    Walltime for each subject job [default: 4:00:00]
    -v,--verbose       Verbose logging
    --debug            Debug logging
    --dry-run          Don't do anything.

DETAILS

    Each subject is run through this pipeline if the outputs do not already exist.

DEPENDENCIES

    Requires dm-proc-freesurfer.py to be completed.

This message is printed with the -h, --help flags.
"""

from datman.docopt import docopt
import datetime
import datman as dm
import logging
import os
import tempfile

logging.basicConfig(level=logging.WARN, 
    format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))


def main():
    """
    Finds subjects that have not been processed and runs dm-proc-ea-sub.py on them. 
    """

    arguments  = docopt(__doc__)
    project    = arguments['<project>']
    script     = arguments['<script>']
    assets     = arguments['<assets>']
    walltime   = arguments['--walltime']
    dryrun     = arguments['--dry-run']
    verbose    = arguments['--verbose']
    debug      = arguments['--debug']

    if verbose: 
        logging.getLogger().setLevel(logging.INFO)
    if debug: 
        logging.getLogger().setLevel(logging.DEBUG)

    data_path = dm.utils.define_folder(os.path.join(project, 'data'))
    nii_path = dm.utils.define_folder(os.path.join(project, 'data', data_path, 'nii'))
    func_path = dm.utils.define_folder(os.path.join(data_path, 'ea'))
    _ = dm.utils.define_folder(os.path.join(project, 'logs'))
    log_path = dm.utils.define_folder(os.path.join(project, 'logs/ea'))

    commands = []
    for sub in dm.utils.get_subjects(nii_path):
        if dm.scanid.is_phantom(sub): 
            logger.debug("Scan {} is a phantom. Skipping", sub)
            continue
        if os.path.isfile('{func_path}/{sub}/{sub}_analysis-complete.log'.format(func_path=func_path, sub=sub)):
            continue
        commands.append('dm-proc-ea-sub.py {opts} {prj} {script} {assets} {sub}'.format(
            opts = (verbose and ' -v' or '') + (debug and ' --debug' or ''),
            prj = project,
            script = script,
            assets = assets,
            sub = sub))

    if commands: 
        logger.debug("queueing up the following commands:\n"+'\n'.join(commands))
        jobname = "dm_ea_{}_{}".format(
            os.path.basename(os.path.realpath(project)),
            datetime.datetime.today().strftime("%Y%m%d-%H%M%S"))
       
        fd, path = tempfile.mkstemp() 
        os.write(fd, '\n'.join(commands))
        os.close(fd)

        rtn, out, err = dm.utils.run('qbatch --logdir {logdir} -N {name} --walltime {wt} {cmds}'.format(
            logdir = log_path,
            name = jobname,
            wt = walltime, 
            cmds = path), dryrun = dryrun)

        if rtn != 0:
            logger.error("Job submission failed. Output follows.")
            logger.error("stdout: {}\nstderr: {}".format(out,err))
            sys.exit(1)

if __name__ == "__main__":
    main()
