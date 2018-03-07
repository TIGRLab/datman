#!/usr/bin/env python
"""
Will complete both dtifit and enigmaDTI pipelines.

There are two levels of tasks:
    Individual - Tasks that need to be completed for each subject individually.
    Group - Tasks that involve the subjects as a whole.
        Ex. Creating summary csv files and html pages

Will complete tasks for both levels unless otherwise specified.

Usage:
    dm_proc_dti.py [options] [dtifit|enigma] [-n DIR -d DIR -e DIR] <study>
    dm_proc_dti.py [options] [dtifit|enigma] [-n DIR -d DIR -e DIR] <study> group
    dm_proc_dti.py [options] [dtifit|enigma] [-n DIR -d DIR -e DIR] <study> individual [<subject_id>...]
    dm_proc_dti.py [options] [dtifit|enigma] -n DIR -d DIR -e DIR
    dm_proc_dti.py [options] [dtifit|enigma] -n DIR -d DIR -e DIR group
    dm_proc_dti.py [options] [dtifit|enigma] -n DIR -d DIR -e DIR individual [<subject_id>...]



Arguments:
    <study>                             Study to process. Only for TIGRLab.
    group                               Will only complete group tasks such as summarizing csv files and creating html pages
    individual [<subject_id>...]        Will only complete individual subject tasks. If no subject ids are given,


Options:
    -n DIR, --nii_dir DIR               Input folder holding nii data within subject subfolders
    -d DIR, --dtifit_dir DIR            Output folder for dtifit data
    -e DIR, --enigma_dir DIR            Output folder for enigmaDTI data
    --reg_vol N                         Registration volume index. For dtifit. [default: 0]
    --fa_thresh N                       FA threshold for bet. For dtifit. [default: 0.3]
    --output_nVox                       Change output value from "Average" to "nVoxels". For
                                        enigma
    --DPA_tags DPA DAP                  Tags for diffusion maps
    --FMAP_tag FMAP                     Tag for fmap
    --dtifit_walltime TIME              A walltime for the dtifit stage [default: 0:30:00]
    --enigma_walltime TIME              A walltime for the enigma stage [default: 2:00:00]
    --enigma_post_walltime TIME         A walltime for the post-enigma stage [default: 2:00:00]

    --log-to-server                     Log to server
    --debug                             Debug logging mode
    --dry_run                           Dry-run
"""
from docopt import docopt
import os

def main():
    arguments = docopt(__doc__)
    print arguments
    study = arguments['<study>']
    group = arguments['group']
    individual = arguments['individual']
    sub_ids = arguments['<subject_id>']
    nii_dir = arguments['--nii_dir']
    dtifit_dir = arguments['--dtifit_dir']
    enigma_dir = arguments['--enigma_dir']
    reg_vol = arguments['--reg_vol']
    fa_thresh = arguments['--fa_thresh']
    output_nVox = arguments['--output_nVox']
    dtifit_wt = arguments['--dtifit_walltime']
    enigma_wt = arguments['--enigma_walltime']
    enigma_post_wt = arguments['--enigma_post_walltime']
    debug = arguments['--debug']
    dry_run = arguments['--dry_run']
    dtifit = arguments['dtifit']
    enigma = arguments['enigma']
    if not (dtifit or enigma):
        dtifit = True
        enigma = True
    if not (group or individual):
        group = True
        individual = True

    print os.environ['ENIGMAHOME']





if __name__ == '__main__':
    main()
