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

from datman.docopt import docopt
import datman.config

logger = logging.getLogger(os.path.basename(__file__))

def scrape_logs(fs_output_folders, standards=None, col_headers=False):
    """
    Takes a list of paths to freesurfer output folders and generates a list of
    log lines containing differences relative to a 'standard' subject.

    For the log data that's checked against a standard, the field will be left
    empty if no differences are found
    """
    subject_logs = [FSLog(subject) for subject in fs_output_folders]

    if not standards:
        standards = make_standards(subject_logs[0])

    verify_standards(standards, ['build', 'kernel', 'args'])

    scraped_data = []
    if col_headers:
        header = 'Name,Start,End,Build,Kernel,Arguments,Nifti Inputs\n'
        scraped_data.append(header)

    standards_line = 'Expected Values,,,{build},{kernel},{args},\n'.format(
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
    if log_field != standards_field:
        return log_field
    return ''

class FSLog(object):

    def __init__(self, freesurfer_folder):
        fs_scripts = os.path.join(freesurfer_folder, 'scripts')
        self.status = self._get_status(fs_scripts)
        self.build = self._get_build(os.path.join(fs_scripts,
                'build-stamp.txt'))

        recon_contents = self._parse_recon_done(os.path.join(fs_scripts,
                'recon-all.done'))
        self.subject = recon_contents.get('SUBJECT', '')
        self.start = self._get_date(recon_contents.get('START_TIME', ''))
        self.end = self._get_date(recon_contents.get('END_TIME', ''))
        self.kernel = self._get_kernel(recon_contents.get('UNAME', ''))
        self.args = self._get_args(recon_contents.get('CMDARGS', ''))
        self.nii_inputs = self._get_niftis(recon_contents.get('CMDARGS', ''))

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
            status = 'Exited with error'
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
            status = "FS may have halted.".format(isrunning_path)
            return status

        _, date_str = date_entry[0].strip('\n').split(None, 1)
        date = self._get_date(date_str)
        now = datetime.datetime.now()
        diff = now - date
        if diff < datetime.timedelta(hours=24):
            status = "Still running."
            return status
        status = "FS halted at {}".format(os.path.basename(isrunning_path))
        return status

    def _get_build(self, build_stamp):
        contents = self.read_log(build_stamp)
        if not contents:
            return ''
        return contents[0].strip('\n')

    def _parse_recon_done(self, recon_done):
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

    def _get_date(self, date_str):
        if not date_str:
            return datetime.datetime.min
        return datetime.datetime.strptime(date_str, '%a %b %d %X %Z %Y')

    def _get_kernel(self, log_uname):
        if not log_uname:
            return ''
        return log_uname.split()[2]

    def _get_args(self, cmd_args):
        if not cmd_args:
            return ''
        cmd_pieces = cmd_args.split(None)
        non_args = ['-subjid', '-i', '-T2']
        args = filter(lambda item: item.startswith('-') and item not in non_args,
                cmd_pieces)
        return ' '.join(sorted(args))

    def _get_niftis(self, cmd_args):
        if not cmd_args:
            return ''
        # Will break on paths containing white space
        nifti_inputs = re.findall('-i\s*\S*|-T2\s*\S*', cmd_args)
        niftis = [item.strip('-i').strip('-T2').strip() for item in nifti_inputs]
        return '; '.join(niftis)

if __name__ == '__main__':
    main()
