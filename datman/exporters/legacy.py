"""Classes for the old-style datman exporters.

These classes allow a single scan to be exported to various file formats with
the datman naming scheme. They were datman's only export methods prior
to 2020ish, but have been phased out in favor of using exporters that use
the bids format.
"""
from glob import glob
import logging
import os
import re

import pydicom as dicom

from datman.utils import run, make_temp_directory, get_extension
from .base import SeriesExporter

logger = logging.getLogger(__name__)

__all__ = ["NiiExporter", "DcmExporter"]


class NiiExporter(SeriesExporter):
    """Export a series to nifti format with datman-style names.
    """

    ext = ".nii.gz"

    type = "nii"

    def export(self, raw_data_dir, **kwargs):
        if self.dry_run:
            logger.info(f"Dry run: Skipping export of {self.fname_root}")
            return

        if self.outputs_exist():
            logger.debug(f"Outputs exist for {self.fname_root}, skipping.")
            return

        self.make_output_dir()

        with make_temp_directory(prefix="export_nifti_") as tmp:
            _, log_msgs = run(f'dcm2niix -z y -b y -o {tmp} {raw_data_dir}',
                              self.dry_run)
            for tmp_file in glob(f"{tmp}/*"):
                self.move_file(tmp_file)
                stem = self._get_fname(tmp_file)
                self.report_issues(stem, str(log_msgs))

    def move_file(self, gen_file):
        """Move the temp outputs of dcm2niix to the intended output directory.

        Args:
            gen_file (:obj:`str`): The full path to the generated nifti file
                to move.
        """
        fname = self._get_fname(gen_file)

        if not fname:
            return

        out_file = os.path.join(self.output_dir, fname)
        if os.path.exists(out_file):
            logger.info(f"Output {out_file} already exists. Skipping.")
            return

        return_code, _ = run(f"mv {gen_file} {out_file}", self.dry_run)
        if return_code:
            logger.debug(f"Moving dcm2niix output {gen_file} to {out_file} "
                         "has failed.")

    def _get_fname(self, gen_file):
        """Get the intended datman-style name for a generated file.

        Args:
            gen_file (:obj:`str`): The full path to the generated nifti file
                to move.

        Result:
            str: A string filename (with extension) or an empty string.
        """
        ext = get_extension(gen_file)
        bname = os.path.basename(gen_file)

        if self.echo_dict:
            stem = self._get_echo_fname(bname, ext)
            if stem != self.fname_root:
                # File belongs to the wrong echo, skip it
                return ""
        else:
            stem = self.fname_root
        return stem + ext

    def _get_echo_fname(self, fname, ext):
        """Get a valid datman-style file name from a multiecho file.

        Args:
            fname (:obj:`str`): A filename to parse for an echo number.
            ext (:obj:`str`): The file extension to use.

        Returns:
            str: A valid datman-style file name or an empty string if one
                cannot be made.
        """
        # Match a 14 digit timestamp and 1-3 digit series num
        regex = "files_(.*)_([0-9]{14})_([0-9]{1,3})(.*)?" + ext
        match = re.search(regex, fname)

        if not match:
            logger.error(f"Can't parse valid echo number from {fname}.")
            return ""

        try:
            echo = int(match.group(4).split('e')[-1][0])
            stem = self.echo_dict[echo]
        except Exception:
            logger.error(f"Can't parse valid echo number from {fname}")
            return ""

        return stem

    def report_issues(self, stem, messages):
        """Write an error log if dcm2niix had errors during conversion.

        Args:
            stem (:obj:`stem`): A valid datman-style file name (minus
                extension).
            messages (:obj:`str`): Error messages to write.
        """
        if self.dry_run:
            logger.info(f"DRYRUN - Skipping write of error log for {stem}")
            return

        if 'missing images' not in messages:
            # The only issue we care about currently is if files are missing
            return

        dest = os.path.join(self.output_dir, stem) + ".err"
        self._write_error_log(dest, messages)

    def _write_error_log(self, dest, messages):
        """Write an error message to the file system.

        Args:
            dest (:obj:`str`): The full path of the file to write.
            messages (:obj:`str`): Intended contents of the error log.
        """
        try:
            with open(dest, "w") as output:
                output.write(messages)
        except Exception as exc:
            logger.error(f"Failed writing dcm2niix errors to {dest}. "
                         f"Reason - {type(exc).__name__} {exc} ")


class DcmExporter(SeriesExporter):
    """Export a single dicom from a scan.
    """

    type = "dcm"
    ext = ".dcm"

    def export(self, raw_data_dir, **kwargs):
        self.make_output_dir()

        if self.echo_dict:
            self._export_multi_echo(raw_data_dir)
            return

        dcm_file = self._find_dcm(raw_data_dir)
        if not dcm_file:
            logger.error(f"No dicom files found in {raw_data_dir}")
            return

        logger.debug(f"Exporting a dcm file from {raw_data_dir} to "
                     f"{self.output_dir}")
        output = os.path.join(self.output_dir, self.fname_root + self.ext)
        run(f"cp {dcm_file} {output}", self.dry_run)

    def _find_dcm(self, raw_data_dir):
        """Find the path to a valid dicom in the given directory.

        Args:
            raw_data_dir (:obj:`str`): The full path to the directory where
                raw dicoms were downloaded for the series.

        Returns:
            str: the full path to the first readable dicom found.
        """
        for path in glob(f"{raw_data_dir}/*"):
            try:
                dicom.read_file(path)
            except dicom.filereader.InvalidDicomError:
                pass
            else:
                return path
        return ""

    def _export_multi_echo(self, raw_data_dir):
        """Find a single valid dicom for each echo in a multiecho scan.

        Args:
            raw_data_dir (:obj:`str`): The full path to the directory where
                raw dicoms were downloaded for the series.
        """
        dcm_dict = {}
        for path in glob(f"{raw_data_dir}/*"):
            try:
                dcm_file = dicom.read_file(path)
            except dicom.filereader.InvalidDicomError:
                continue
            dcm_echo_num = dcm_file.EchoNumbers
            if dcm_echo_num not in dcm_dict:
                dcm_dict[int(dcm_echo_num)] = path
            if len(dcm_dict) == len(self.echo_dict):
                break

        for echo_num, dcm_echo_num in zip(self.echo_dict.keys(),
                                          dcm_dict.keys()):
            output_file = os.path.join(self.output_dir,
                                       self.echo_dict[echo_num] + self.ext)
            logger.debug(f"Exporting a dcm file from {raw_data_dir} to "
                         f"{output_file}")
            cmd = f"cp {dcm_dict[dcm_echo_num]} {output_file}"
            run(cmd, self.dry_run)
