#!/usr/bin/env python

'''
Helper script for transferring motion files generated from feenics over to fMRIPREP (version >= 1.3.2)

Usage:
    transfer_feenics_motion.py [options] [-s SUBJECT]...  <study> <output_dir>

Arguments:
        <study>                             DATMAN study ID
        <output_dir>                        Directory to output new confounds files

Optional:
    -s, --subject SUBJECT                   Repeatable list of subjects
    -f, --fmriprep FMRIPREP                 fMRIPREP derivatives directory
                                            (default is PROJECT_DIR/pipelines/feenics)
    -d, --debug                             Debug level logging
    -v, --verbose                           Verbose level logging
    -q, --quiet                             Quiet mode
'''

from datman.bids.check_bids import BIDSEnforcer
from datman.config import config as dm_cfg
from datman import scanid
from bids import BIDSLayout
from docopt import docopt
import numpy as np
import pandas as pd
import os

def combine_sprl_motion(sprl_in, sprl_out):

    motion_in = np.genfromtxt(sprl_in)
    motion_out = np.genfromtxt(sprl_out)

    motion_comb = (motion_in+motion_out)/2
    return motion_comb


def proc_subject(s, pipeline_dir):
    '''
    Given a subject locate FeenICS confounds in pipeline directory
    '''

    #Get motion files
    sub_dir = os.path.join(pipeline_dir,s)
    sprl_in = os.path.join(sub_dir,'sprlIN','motion_corr.par')
    sprl_out = os.path.join(sub_dir,'sprlOUT','motion_corr.par')

    #Average the motion traces
    motion_comb = combine_sprl_motion(sprl_in,sprl_out)

    return motion_comb

def combine_confounds(confound, motion):
    '''
    Given a confound file and motion array:
        - Replace the existing translation/rotation parameters in confounds with those in motion
        - Return a pandas dataframe containing the final dataframe to be outputted

    Should support both versions of fMRIPREP...=>1.3.2 first
    '''

    #Get columns to replace
    dirs = ['x','y','z']
    trans = ['trans_{}'.format(d) for d in dirs]
    rots = ['rot_{}'.format(d) for d in dirs]
    cols = trans + rots

    #Load in confounds
    df = pd.read_csv(confound,delimiter='\t')

    #Drop columns to be replaced
    df.drop(cols,axis=1,inplace=True)

    #Replace with motion information
    motion_df = pd.DataFrame(motion,columns=cols)

    #Append to dataframe
    df = df.join(motion_df)

    #Return dataframe
    return df





def main():


    arguments       =   docopt(__doc__)
    study           =   arguments['<study>']
    output          =   arguments['<output_dir>']

    #Default directories
    cfg = dm_cfg(study=study)
    feenics_dir = cfg.get_path('feenics')

    fmriprep        =   arguments['--fmriprep'] or cfg.get_path('fmriprep')
    subjects        =   arguments['--subject']

    debug           =   arguments['--debug']
    verbose         =   arguments['--verbose']
    quiet           =   arguments['--quiet']

    #Step 1: Loop through subjects available in the feenics pipeline directory
    if not subjects:
        subjects = [s for s in os.listdir(feenics_dir)
                    if os.path.isdir(os.path.join(feenics_dir,s))]

    #Step 1a: Get BIDS subjects
    layout = BIDSLayout(fmriprep,validate=False)
    confounds = layout.get(suffix=['confounds','regressors'],extension='tsv')

    #Process each subject
    for s in subjects:

        #Get session info

        #Combine motion files
        motion_comb = proc_subject(s,feenics_dir)

        #Get subject BIDS name and session
        ident = scanid.parse(s)
        bids = ident.get_bids_name()
        ses = ident.timepoint

        #Get confound file if exists
        try:
            confound = [c.path for c in confounds if
                    (c.entities['subject'] == bids) and (c.entities['session'] == ses)][0]
        except IndexError:
            continue

        #Combine confound file using pandas
        updated_confound = combine_confounds(confound, motion_comb)

        #Write dataframe to output
        confound_name = os.path.basename(confound)
        updated_confound.to_csv(os.path.join(output,confound_name),sep='\t')


if __name__ == '__main__':
    main()

