"""Classes and functions for generating QC metrics.
"""
import os
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

from datman.utils import run, make_temp_directory, nifti_basename
from datman.exceptions import QCException


@dataclass
class QCOutput:
    order: int = -1
    title: str = None
    caption: str = None


class Metric(ABC):

    requires = {
        "images": ["slicer"],
        "montage": ["slicer", "pngappend"]
    }

    @abstractmethod
    def outputs(self):
        pass

    @abstractmethod
    def generate(self):
        pass

    @property
    def manifest_path(self):
        return self.output_root + "_manifest.json"

    def __init__(self, input_nii, output_dir):
        self.input = input_nii
        self.output_root = os.path.join(output_dir, nifti_basename(input_nii))
        self.outputs = self.set_outputs()

    def write_manifest(self, overwrite=False):
        if os.path.exists(self.manifest_path):
            if not overwrite:
                return
            orig = self.read_json()
        else:
            orig = {}

        manifest = self.make_manifest()

        if orig != manifest:
            self._write_json(manifest)

    def _write_json(self, contents):
        with open(self.manifest_path, "w") as fh:
            json.dump(contents, fh, indent=4)

    def read_manifest(self):
        with open(self.manifest_path, "r") as fh:
            contents = json.load(fh)
        return contents

    def make_manifest(self):
        manifest = {}
        for command in self.outputs:
            for file_path in self.outputs[command]:
                output = self.outputs[command][file_path]
                if isinstance(output, QCOutput):
                    manifest[os.path.basename(file_path)] = vars(output)
        return manifest

    @classmethod
    def get_requirements(cls):
        requires = []
        for command in cls.outputs:
            try:
                found = cls.requires[command]
            except KeyError:
                found = [command]
            requires.extend(found)
        return list(set(requires))

    @classmethod
    def is_runnable(cls):
        requires = cls.get_requirements()
        for prereq in requires:
            code, _ = run(f"which {prereq}")
            if code != 0:
                return False
        return True

    def set_outputs(self):
        outputs = {}
        for command in self.outputs:
            outputs[command] = {}
            for ending in self.outputs[command]:
                full_path = os.path.join(self.output_root + ending)
                outputs[command][full_path] = self.outputs[command][ending]
        return outputs

    def exists(self):
        for command in self.outputs:
            if not self.command_succeeded(command)[0]:
                return False
        if not os.path.exists(self.manifest_path):
            return False
        return True

    def command_succeeded(self, command_name):
        if command_name not in self.outputs:
            return os.path.exists(command_name), command_name

        for output in self.outputs[command_name]:
            if not os.path.exists(output):
                return False, output
        return True, None

    def run(self, command, output):
        """Run a command if outputs are still needed.

        Args:
            command (str): The exact string command to run.
            output (str): A command name (as defined in self.commands) or a
                full path to a single file.

        Raises:
            QCException: If any expected outputs haven't been generated.
        """
        if self.command_succeeded(output)[0]:
            return

        run(command)

        success, last_output = self.command_succeeded(output)
        if not success:
            raise QCException(
                f"Failed generating {last_output} with command '{command}'")

    def make_image(self, output, img_gap=2, width=1600, nii_input=None):
        """Uses FSL's slicer function to generate a png from a nifti file.

        Args:
            output (str): The full path to write the output image to
            img_gap (int, optional): Size of the "gap" to insert between
                slices. Defaults to 2.
            width (int, optional): width (in pixels) of output image.
                Defaults to 1600.
            nii_input (str, optional): The nifti image to visualize. If not
                given, self.input will be used.
        """
        if not nii_input:
            nii_input = self.input
        self.run(f"slicer {nii_input} -S {img_gap} {width} {output}", output)

    def make_montage(self, output):
        """Uses FSL's slicer function to generate a montage of three slices.

        Args:
            output (str): The full path to write the result to.
        """
        if os.path.exists(output):
            return

        with make_temp_directory() as temp:
            img_command = "slicer {0} -s 1 "\
                "-x 0.4 {1}/grota.png "\
                "-x 0.5 {1}/grotb.png "\
                "-x 0.6 {1}/grotc.png "\
                "-y 0.4 {1}/grotd.png "\
                "-y 0.5 {1}/grote.png "\
                "-y 0.6 {1}/grotf.png "\
                "-z 0.4 {1}/grotg.png "\
                "-z 0.5 {1}/groth.png "\
                "-z 0.6 {1}/groti.png"\
                .format(self.input, temp)
            run(img_command)

            montage_command = "pngappend {0}/grota.png + {0}/grotb.png + "\
                "{0}/grotc.png + {0}/grotd.png + {0}/grote.png + "\
                "{0}/grotf.png + {0}/grotg.png + {0}/groth.png + "\
                "{0}/groti.png {1}"\
                .format(temp, output)
            run(montage_command)

        if not os.path.exists(output):
            raise QCException(f"Failed generating montage {output}")


class MetricDTI(Metric):
    def __init__(self, nii_input, output_dir, bval=None, bvec=None):
        input_root = os.path.join(os.path.dirname(nii_input),
                                  nifti_basename(nii_input))

        if not bvec:
            bvec = input_root + ".bvec"
        if not bval:
            bval = input_root + ".bval"

        self.bvec = bvec
        self.bval = bval
        if not os.path.exists(self.bvec) or not os.path.exists(self.bval):
            raise QCException(f"Can't process {nii_input} - bvec or bval file "
                              "missing.")

        super().__init__(nii_input, output_dir)


class IgnoreMetrics(Metric):
    outputs = {}

    def exists(self):
        return True

    def generate(self):
        return

    def write_manifest(self, overwrite=False):
        return


class DTIMetrics(MetricDTI):
    outputs = {
        "montage": {
            "_montage.png": QCOutput(1)
        },
        "images": {
            "_b0.png": QCOutput(2, "b0 Montage")
        },
        "qc-dti": {
            "_qascripts_dti.csv": None,
            "_stats.csv": None,
            "_directions.png": QCOutput(3, "bvec Directions")
        },
        "qc-spikecount": {
            "_spikecount.csv": None
        }
    }

    def generate(self, img_gap=2, width=1600):
        self.run(f"qc-dti {self.input} {self.bvec} {self.bval} "
                 f"{self.output_root}", "qc-dti")

        self.run(f"qc-spikecount {self.input} "
                 f"{self.output_root + '_spikecount.csv'} {self.bval}",
                 "qc-spikecount")

        self.make_montage(self.output_root + "_montage.png")
        self.make_image(self.output_root + "_b0.png", img_gap, width)


class AnatMetrics(Metric):
    outputs = {
        "images": {
            ".png": QCOutput(1)
        }
    }

    def generate(self, img_gap=5, width=1600):
        self.make_image(self.output_root + ".png", img_gap, width)


class FMRIMetrics(Metric):
    outputs = {
        "qc-scanlength": {
            "_scanlengths.csv": None
        },
        "qc-fmri": {
            "_fd.csv": None,
            "_qascripts_bold.csv": None,
            "_spectra.csv": None,
            "_stats.csv": None,
            "_sfnr.nii.gz": None,
            "_corr.nii.gz": None
        },
        "montage": {
            "_montage.png": QCOutput(1),
        },
        "images": {
            "_raw.png": QCOutput(2, "BOLD Montage"),
            "_sfnr.png": QCOutput(3, "SFNR Map"),
            "_corr.png": QCOutput(4, "Correlation Map")
        }
    }

    def generate(self, img_gap=2, width=1600):
        self.run(f"qc-scanlength {self.input}"
                 f" {self.output_root + '_scanlengths.csv'}",
                 "qc-scanlength")
        self.run(f"qc-fmri {self.input} {self.output_root}", "qc-fmri")

        self.make_montage(self.output_root + "_montage.png")
        self.make_image(self.output_root + "_raw.png", img_gap, width)
        self.make_image(self.output_root + "_sfnr.png",
                        img_gap,
                        width,
                        nii_input=self.output_root + "_sfnr.nii.gz")
        self.make_image(self.output_root + "_corr.png",
                        img_gap,
                        width,
                        nii_input=self.output_root + "_corr.nii.gz")


class AnatPHAMetrics(Metric):
    outputs = {
        "qc-adni": {
            "_stats.csv": None
        }
    }

    def generate(self):
        self.run(f"qc-adni {self.input} {self.output_root}", "qc-adni")


class FMRIPHAMetrics(Metric):
    outputs = {
        "qc-fbirn-fmri": {
            "_images.jpg": QCOutput(1),
            "_plots.jpg": QCOutput(2),
            "_stats.csv": None,
        }
    }

    def generate(self):
        self.run(f"qc-fbirn-fmri {self.input} {self.output_root}",
                 "qc-fbirn-fmri")


class DTIPHAMetrics(MetricDTI):
    outputs = {
        "qc-fbirn-dti": {}
    }

    def generate(self):
        self.run(f"qc-fbirn-dti {self.input} {self.bvec} {self.bval} "
                 f"{self.output_root}", "qc-fbirn-dti")


class QAPHAMetrics(MetricDTI):
    outputs = {
        "qa-dti": {
            "B0Distortion-PAR.jpg": QCOutput(1),
            "CentralSlice-PAR.jpg": QCOutput(2),
            "DiffImgs-PAR.jpg": QCOutput(3),
            "DiffMasks-PAR.jpg": QCOutput(4),
            "MaskCentralSlice-PAR.jpg": QCOutput(5),
            "NyquistRatio-PAR.jpg": QCOutput(6),
            "Plot-EddyCurrentDist-PAR.jpg": QCOutput(7),
            "SNRImgs-PAR.jpg": QCOutput(8),
            # SNRPlots-PAR.jpg missing
            "StdPlotsHist-PAR.jpg": QCOutput(9),
            "Section2.3.1_SNR_ADC.csv": None,
            "Section2.3.2_B0DistortionRatio.csv": None,
            "Section2.3.3_EddyCurrentDistortions.csv": None,
            "Section2.3.4_AveNyqRatio.csv": None,
            "Section2.3.5_FAvalues.csv": None
        }
    }

    def __init__(self, nii_input, output_dir, bval=None, bvec=None):
        self.accel = "NO" in nii_input
        if not self.accel:
            self.update_expected_outputs()
        super().__init__(nii_input, output_dir, bval, bvec)

    def update_expected_outputs(self):
        # Create a new dictionary or the class defaults will change
        new_outputs = {key: self.outputs[key] for key in self.outputs
                       if key != "qa-dti"}
        new_outputs["qa-dti"] = {
            fname.replace("-PAR.", "-NPAR."): self.outputs["qa-dti"][fname]
            for fname in self.outputs["qa-dti"]
        }
        self.outputs = new_outputs

    def generate(self):
        self.run(f"qa-dti {self.input} {self.bvec} {self.bval}"
                 f"{' --accel ' if self.accel else ''} "
                 f"{self.output_root}", "qa-dti")


class ABCDPHAMetrics(Metric):
    outputs = {
        "qc-abcd-fmri": {}
    }

    def generate(self):
        self.run(f"qc-abcd-fmri {self.input} {self.output_root}",
                 "qc-abcd-fmri")


QC_FUNC = {
    "anat": AnatMetrics,
    "fmri": FMRIMetrics,
    "dti": DTIMetrics,
    "ignore": IgnoreMetrics
}

PHA_QC_FUNC = {
    "anat": AnatPHAMetrics,
    "fmri": FMRIPHAMetrics,
    "dti": DTIPHAMetrics,
    "qa_dti": QAPHAMetrics,
    "abcd_fmri": ABCDPHAMetrics,
    "ignore": IgnoreMetrics
}


def get_handlers(subject):
    """Returns the set of QC functions to use for a subject.

    Args:
        subject (:obj:`datman.scan.Scan`): The session that metrics must be
            generated for.

    Returns:
        :obj:`dict`: A dictionary of string QC 'types' mapped to the function
            used to generate QC metrics for it.
    """
    if subject.is_phantom:
        return PHA_QC_FUNC
    return QC_FUNC
