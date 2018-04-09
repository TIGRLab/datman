#!/usr/bin/env python
"""
Scrapes the 'scripts' log files in a freesurfer output folder for information
about a run and reports any differences between the subjects and the expected
parameters.

The FSLog class aggregates/parses the most useful details from the log files.
"""
import os
import sys
import glob
import re
import datetime
import logging

from docopt import docopt
import datman.config

logger = logging.getLogger(os.path.basename(__file__))

def scrape_logs(fs_output_folders, standards=None, col_headers=False):
    """
    Takes a list of paths to freesurfer output folders and generates a list of
    log lines containing differences relative to a 'standard' subject.

    A field will be left empty if no differences are found
    """
    subject_logs = [FSLog(subject) for subject in fs_output_folders]

    if not standards:
        standard_sub = choose_standard_sub(subject_logs)
        standards = make_standards(standard_sub)

    verify_standards(standards, ['build', 'kernel', 'args'])

    scraped_data = []
    if col_headers:
        header = 'Name,Status,Start,End,Build,Kernel,Arguments,Nifti Inputs\n'
        scraped_data.append(header)

    standards_line = 'Expected Values,,,,{build},{kernel},{args},\n'.format(
        **standards)
    scraped_data.append(standards_line)

    for log in subject_logs:
        log.build = check_diff(log.build, standards['build'])
        log.kernel = check_diff(log.kernel, standards['kernel'])
        log.args = check_diff(log.args, standards['args'])
        entry_line = '{sub},{status},{start},{end},{build},{kernel},{args},' \
                '{nii}\n'.format(sub=log.subject,
                                 status=log.status,
                                 start=log.start,
                                 end=log.end,
                                 build=log.build,
                                 kernel=log.kernel,
                                 args=log.args,
                                 nii=log.nii_inputs)
        scraped_data.append(entry_line)
    return scraped_data

def choose_standard_sub(subject_logs):
    standard_sub = None
    for subject in subject_logs:
        if subject.status:
            # Dont choose a subject that has not successfully finished
            continue
        standard_sub = subject
    if not standard_sub:
        raise Exception("Could not create standards. No subjects have "
                "complete freesurfer outputs.")
    return standard_sub

def make_standards(standard_log):
    standards = {'build': standard_log.build,
                 'kernel': standard_log.kernel,
                 'args': standard_log.args}
    return standards

def verify_standards(standards_dict, expected_keys):
    for key in expected_keys:
        try:
            _ = standards_dict[key]
        except KeyError:
            raise KeyError("Missing expected field \"{}\" in given "
            "standards".format(key))

def check_diff(log_field, standards_field):
    diffs = ''
    if isinstance(log_field, str):
        sorted_args = sorted(log_field.split())
        sorted_standards = sorted(standards_field.split())
        if sorted_args != sorted_standards:
            diffs = log_field
    else:
        if log_field != standards_field:
            diffs = log_field
    return diffs

class FSLog(object):

    _MAYBE_HALTED = "FS may have halted."
    _RUNNING = "Job still running."
    _TIMEDOUT = "FS halted at {}"
    _ERROR = "Exited with error."

    def __init__(self, freesurfer_folder):
        self._path = freesurfer_folder
        fs_scripts = os.path.join(freesurfer_folder, 'scripts')
        self.status = self._get_status(fs_scripts)
        self.build = self._get_build(os.path.join(fs_scripts,
                'build-stamp.txt'))

        recon_contents = self.parse_recon_done(os.path.join(fs_scripts,
                'recon-all.done'))
        self.subject = self.get_subject(recon_contents.get('SUBJECT', ''))
        self.start = self.get_date(recon_contents.get('START_TIME', ''))
        self.end = self.get_date(recon_contents.get('END_TIME', ''))
        self.kernel = self.get_kernel(recon_contents.get('UNAME', ''))
        self.args = self.get_args(recon_contents.get('CMDARGS', ''))
        self.nii_inputs = self.get_niftis(recon_contents.get('CMDARGS', ''))

    def read_log(self, path):
        try:
            with open(path, 'r') as log:
                contents = log.readlines()
        except IOError:
            return []
        return contents

    def _get_status(self, scripts):
        error_log = os.path.join(scripts, 'recon-all.error')
        regex = os.path.join(scripts, '*')
        run_logs = [item for item in glob.glob(regex) if 'IsRunning' in item]
        recon_log = os.path.join(scripts, 'recon-all.done')

        if run_logs:
            status = self._parse_isrunning(run_logs[0])
        elif os.path.exists(error_log):
            status = self._ERROR
        elif os.path.exists(recon_log):
            status = ''
        else:
            raise Exception("No freesurfer log files found for "
                    "{}".format(scripts))

        return status

    def _parse_isrunning(self, isrunning_path):
        contents = self.read_log(isrunning_path)
        date_entry = [line for line in contents if line.startswith('DATE')]

        if not contents or not date_entry:
            status = self._MAYBE_HALTED
            return status

        _, date_str = date_entry[0].strip('\n').split(None, 1)
        date = self.get_date(date_str)
        now = datetime.datetime.now()
        diff = now - date
        if diff < datetime.timedelta(hours=24):
            status = self._RUNNING
            return status
        status = self._TIMEDOUT.format(os.path.basename(isrunning_path))
        return status

    def _get_build(self, build_stamp):
        contents = self.read_log(build_stamp)
        if not contents:
            return ''
        return contents[0].strip('\n')

    def parse_recon_done(self, recon_done):
        recon_contents = self.read_log(recon_done)

        if len(recon_contents) < 2:
            # If length is less than two, log is malformed and will cause a
            # crash when the for loop is reached below
            return {}

        parsed_contents = {}
        # Skip first line, which is just a bunch of dashes
        for line in recon_contents[1:]:
            fields = line.strip('\n').split(None, 1)
            parsed_contents[fields[0]] = fields[1]

        return parsed_contents

    def get_subject(self, subject_field):
        if subject_field:
            return subject_field
        subject = os.path.basename(self._path)
        return subject

    def get_date(self, date_str):
        if not date_str:
            return ''
        return datetime.datetime.strptime(date_str, '%a %b %d %X %Z %Y')

    def get_kernel(self, log_uname):
        if not log_uname:
            return ''
        return log_uname.split()[2]

    @staticmethod
    def get_args(cmd_args):
        if not cmd_args:
            return ''
        cmd_pieces = re.split('^-|\s-', cmd_args)
        args = cmd_pieces
        for item in ['i ', 'T2 ', 'subjid ']:
            args = filter(lambda x: not x.startswith(item), args)
        str_args = ' -'.join(sorted(args))
        return str_args.strip()

    @staticmethod
    def get_niftis(cmd_args):
        if not cmd_args:
            return ''
        # Will break on paths containing white space
        nifti_inputs = re.findall('-i\s*\S*|-T2\s*\S*', cmd_args)
        niftis = [item.strip('-i').strip('-T2').strip() for item in nifti_inputs]
        return '; '.join(niftis)

if __name__ == '__main__':
    main()
