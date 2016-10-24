'''
A collection of functions used in dm-proc*.py for running pipelines
'''
import os
import sys
import glob
import filecmp
import difflib
import logging

import pandas as pd

import datman as dm

logger = logging.getLogger(__name__)

def get_subject_list(input_dir, subject_filter, QC_file):
    """
    Returns a list of subjects in input_dir,
    minus any phantoms or not qced subjects,
    Also removes any subject ids that do not contain the subject_filter string
    """
    subject_list = dm.utils.get_subjects(input_dir)
    subject_list = remove_phantoms(subject_list)
    if subject_filter is not None:
        subject_list = remove_subjects_using_filter(subject_list, subject_filter)
    if QC_file is not None:
        subject_list = remove_unqced_subjects(subject_list, QC_file)
    return subject_list

def remove_phantoms(subject_list):
    subject_list = [ subid for subid in subject_list if "PHA" not in subid ]
    return subject_list

def remove_subjects_using_filter(subject_list, subject_filter):
    subject_list = [ subid for subid in subject_list if subject_filter in subid ]
    return subject_list

def remove_unqced_subjects(subject_list, QC_file):
    qced_list = get_qced_subjects(QC_file)
    subject_list = list(set(subject_list) & set(qced_list))
    return subject_list

def get_qced_subjects(qc_list):
    """
    reads the QC_list and returns a list of all subjects who have passed QC
    """
    qced_subs = []

    if not os.path.isfile(qc_list):
        logger.error("QC file for transfer not found.", exc_info=True)
        sys.exit(1)

    with open(qc_list) as f:
        for line in f:
            line = line.strip()
            fields = line.split(' ')
            if len(fields) > 1:
                qc_file_name = fields[0]
                subid = get_qced_subid(qc_file_name)
                qced_subs.append(subid)

    return qced_subs

def get_qced_subid(qc_file_name):
    subid = qc_file_name.replace('.pdf','')
    subid = subid.replace('.html','')
    subid = subid.replace('qc_', '')
    return subid

def load_checklist(checklist_file, cols):
    """
    Reads the checklist file for a dm-proc* analysis.
    If the checklist csv file does not exist, it will be created.
    Arguments:
         checklist_file:   the filename of the checklist
         cols:             the expected columns for this checklist
    """

    # if the checklist exists - open it, if not - create the dataframe
    if os.path.isfile(checklist_file):
    	checklist = pd.read_csv(checklist_file, sep=',', dtype=str, comment='#')
    else:
    	checklist = pd.DataFrame(columns = cols)

    return checklist

def add_new_subjects_to_checklist(subject_list, checklist, cols):
    """
    If any subjects are not in the analysis checklist, appends them to the end of
    the data frame.
    Arugments:
         subject_list:    A list of subjects to this analysis
         checklist:       A pandas dataframe of "checklist" info for this analysis
         cols:            The expected columns for the checklist pandas dataframe
    """
    # new subjects are those of the subject list that are not in checklist.id
    newsubs = list(set(subject_list) - set(checklist.id))

    # add the new subjects to the bottom of the dataframe
    newsubs_df = pd.DataFrame(columns = cols, index = range(len(checklist),
                              len(checklist)+len(newsubs)))
    newsubs_df.id = newsubs
    checklist = checklist.append(newsubs_df)

    return checklist

def find_images(checklist, checklist_col, input_dir, tag,
                subject_filter = None,
                image_filter = None,
                allow_multiple = False):
    """
    finds new files in the inputdir and add them to a list for the processing
    Arguments:
        checklist:        pandas dataframe of the analysis checklist
        checklist_col:    the column in the checklist dataframe to update
        input_dir:        the input directory to search through
        tag:              filename tag that can be used for search (ex. '_FA.nii.gs')
        subject_filter:   second tag that is also need (i.e. Site Name)
        image_filter:     optional filter for the image type (i.e. 'DTI-60')
        allow_multiple:   Wether to allow multiple images from one subject into
                          this analysis (default is False)
    """
    for row in range(0,len(checklist)):

        ## only look for files for subjects matching the subject_filter
        if subject_filter and subject_filter not in checklist['id'][row]:
            continue

        subject_dir = os.path.join(input_dir,checklist['id'][row])

	    #if no T1 file listed for this row
        if pd.isnull(checklist[checklist_col][row]):
            subject_files = []
            for fname in os.listdir(subject_dir):
                if tag in fname:
                    if not image_filter:
                        subject_files.append(fname)
                    elif image_filter in fname:
                        subject_files.append(fname)

            logger.debug("Found {} {} in {}".format(len(subject_files),
                                                tag, subject_dir))
            if len(subject_files) == 1:
                checklist[checklist_col][row] = subject_files[0]
            elif len(subject_files) > 1:
                if allow_multiple:
                    # if multiple matches are allowed add all to checklist
                    checklist[checklist_col][row] = ';'.join(subject_files)
                else:
                    checklist[checklist_col][row] = "> 1 {} found".format(tag)
            elif len(subject_files) < 1:
                checklist[checklist_col][row] = "No {} found.".format(tag)

    return checklist

def qbatchcmd_pipe(job_cmd, job_name_prefix, log_dir, wall_time, afterok = False):
    '''
    submits jobs (i.e. pipelines) to qbatch
    Arguments:
       joblist:    A string or the command for qbatch to submit
       job_name:   The array jobs' Name (i.e. what you will see in qstat)
       log_dir:    The array jobs logging directory
       wall_time:  The walltime for the job.
       afterok:    If using the "afterok" option, the job name that will be held for

    '''

    # make FS command for subject
    cmd = 'echo "{job_cmd}" | '\
          'qbatch -N {jobname} --logdir {logdir} --walltime {wt} '.format(
                job_cmd = job_cmd,
                jobname = job_name_prefix,
                logdir = log_dir,
                wt = wall_time)

    if afterok:
        cmd = cmd + '--afterok {} '.format(afterok)

    cmd = cmd + '-'

    return cmd

def qbatchcmd_file(jobs_txt, job_name_prefix, log_dir, wall_time, afterok = False):
    '''
    submits jobs (i.e. pipelines) to qbatch
    Arguments:
       jobs_txt:   A text file containing a list of commands to run
       job_name:   The array jobs' Name (i.e. what you will see in qstat)
       log_dir:    The array jobs logging directory
       wall_time:  The walltime for the job.
       afterok:    If using the "afterok" option, the job name that will be held for

    '''

    # make FS command for subject
    cmd = 'qbatch -N {jobname} --logdir {logdir} --walltime {wt} '.format(
                jobname = job_name_prefix,
                logdir = log_dir,
                wt = wall_time)

    if afterok:
        cmd = cmd + '--afterok {} '.format(afterok)

    cmd = cmd + jobs_txt

    return cmd
