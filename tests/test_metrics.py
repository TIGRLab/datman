import os
from unittest.mock import patch

import pytest

import datman.metrics


class TestMetric:

    input_basename = "STUDY_SITE_SUBID_01_01_TAG_00_DESCR"
    nii_input = f"/tmp/{input_basename}.nii.gz"
    output_dir = "/tmp/test_metrics/"

    def test_manifest_path_set_to_expected_output_name(self):
        fmri = datman.metrics.FMRIMetrics(self.nii_input, self.output_dir)

        expected = self.output_dir + self.input_basename + "_manifest.json"
        assert fmri.manifest_path == expected

    @patch("datman.metrics.open")
    @patch("os.path.exists")
    def test_manifest_not_written_when_exists(self, mock_exist, mock_fh):
        mock_exist.return_value = True
        fmri = datman.metrics.FMRIMetrics(self.nii_input, self.output_dir)
        fmri.write_manifest()

        assert mock_fh.call_count == 0

    @patch("datman.metrics.open")
    @patch("os.path.exists")
    def test_manifest_written_when_overwrite_given_or_file_doesnt_exist(
            self, mock_exists, mock_fh):
        fmri = datman.metrics.FMRIMetrics(self.nii_input, self.output_dir)
        manifest = fmri.manifest_path
        mock_exists.side_effect = lambda x: x != manifest
        fmri.write_manifest()

        expected_call = f"call('{manifest}', 'w')"

        assert mock_fh.call_count == 1
        assert str(mock_fh.call_args) == expected_call

        mock_fh.reset_mock()
        mock_exists.return_value = True
        fmri.write_manifest(overwrite=True)

        assert mock_fh.call_count == 1
        assert str(mock_fh.call_args) == expected_call

    @patch("datman.metrics.open")
    @patch("os.path.exists")
    def test_manifest_written_even_if_no_imgs_to_display(
            self, mock_exists, mock_fh):
        pha_anat = datman.metrics.AnatPHAMetrics(
            self.nii_input, self.output_dir)
        manifest = pha_anat.manifest_path
        mock_exists.side_effect = lambda x: x != manifest
        pha_anat.write_manifest()

        expected_call = f"call('{manifest}', 'w')"
        assert mock_fh.call_count == 1
        assert str(mock_fh.call_args) == expected_call

    @patch("os.path.exists")
    def test_exists_is_false_when_at_least_one_file_missing(self, mock_exist):
        fmri = datman.metrics.FMRIMetrics(self.nii_input, self.output_dir)
        outputs = self.get_outputs(fmri)

        mid = len(outputs) // 2
        mock_exist.side_effect = lambda x: x != outputs[mid]
        assert not fmri.exists()

        mock_exist.side_effect = lambda x: x != fmri.manifest_path
        assert not fmri.exists()

    @patch("os.path.exists")
    def test_exists_is_true_when_outputs_and_manifest_found(self, mock_exist):
        fmri = datman.metrics.FMRIMetrics(self.nii_input, self.output_dir)
        outputs = self.get_outputs(fmri)
        outputs.append(fmri.manifest_path)

        mock_exist.side_effect = lambda x: x in outputs

        assert fmri.exists()

    @patch("datman.metrics.run")
    def test_is_runnable_returns_false_if_required_software_missing(
            self, mock_run):
        fmri = datman.metrics.FMRIMetrics(self.nii_input, self.output_dir)
        requires = fmri.get_requirements()

        mid = len(requires) // 2

        def mock_which(command):
            if "which" in command and command == f"which {requires[mid]}":
                return 1, b""
            return 0, b""

        mock_run.side_effect = mock_which
        assert not fmri.is_runnable()

    @patch("datman.metrics.run")
    def test_is_runnable_returns_true_if_requirements_met(self, mock_run):
        mock_run.return_value = (0, b"")

        anat = datman.metrics.AnatMetrics(self.nii_input, self.output_dir)
        assert anat.is_runnable()

    def test_get_requirements_doesnt_duplicate_requred_commands(self):
        class MockMetric(datman.metrics.Metric):
            outputs = {
                "montage": {"_montage.png": None},
                "images": {"_b0.png": None},
                "qc_func_1": {"_output1.csv": None},
                "slicer": {"output2.csv": None},
                "qc_func_2": {"output3.csv": None}
            }

            def generate(self):
                return

        metric = MockMetric("/some/path/nifti.nii.gz", "/some/path/qc")
        expected = sorted(["slicer", "qc_func_1", "qc_func_2", "pngappend"])

        assert sorted(metric.get_requirements()) == expected

    @patch("datman.metrics.run")
    @patch("os.path.exists")
    def test_run_raises_exception_if_outputs_not_found_after_command_run(
            self, mock_exist, mock_run):
        mock_exist.return_value = False
        anat = datman.metrics.AnatMetrics(self.nii_input, self.output_dir)

        assert not anat.exists()
        with pytest.raises(datman.exceptions.QCException):
            anat.generate()
        assert not anat.exists()

    @patch("datman.metrics.run")
    @patch("os.path.exists")
    def test_run_skips_command_if_expected_outputs_found(
            self, mock_exist, mock_run):
        mock_exist.return_value = True
        anat = datman.metrics.AnatMetrics(self.nii_input, self.output_dir)

        assert anat.exists()
        anat.generate()

        assert mock_run.call_count == 0

    @patch("datman.metrics.run")
    @patch("os.path.exists")
    def test_make_montage_does_nothing_when_output_exists(
            self, mock_exist, mock_run):
        mock_exist.return_value = True

        fmri = datman.metrics.FMRIMetrics(self.nii_input, self.output_dir)
        test_output = fmri.output_root + "_montage_test.png"

        fmri.make_montage(test_output)
        assert mock_run.call_count == 0

    @patch("datman.metrics.run")
    @patch("os.path.exists")
    def test_make_montage_raises_exception_if_output_not_created(
            self, mock_exist, mock_run):

        fmri = datman.metrics.FMRIMetrics(self.nii_input, self.output_dir)
        test_output = fmri.output_root + "_montage_test.png"

        mock_exist.side_effect = lambda x: x != test_output

        assert not os.path.exists(test_output)
        with pytest.raises(datman.exceptions.QCException):
            fmri.make_montage(test_output)

    def get_outputs(self, metric):
        outputs = []
        for command in metric.outputs:
            outputs.extend(metric.outputs[command])
        return outputs


class TestDTIMetric:
    input_basename = "STUDY_SITE_SUBID_01_01_DTI60-1000_00_DESCR"
    nii_input = f"/tmp/{input_basename}.nii.gz"
    bval = f"/tmp/{input_basename}.bval"
    bvec = f"/tmp/{input_basename}.bvec"
    output_dir = "/tmp/test_metrics/"

    @patch("os.path.exists")
    def test_dti_metric_defaults_bvec_and_bval_to_expected_paths(
            self, mock_exist):
        mock_exist.return_value = True

        dti = datman.metrics.DTIMetrics(self.nii_input, self.output_dir)

        assert dti.bval == self.bval
        assert dti.bvec == self.bvec

    @patch("os.path.exists")
    def test_dti_metric_allows_override_for_bvec_and_bval_paths(
            self, mock_exist):
        mock_exist.return_value = True
        diff_bvec = f"/some/other/folder/{self.input_basename}.bvec"
        diff_bval = f"/a/third/folder/{self.input_basename}.bval"

        dti = datman.metrics.DTIMetrics(self.nii_input, self.output_dir,
                                        bvec=diff_bvec, bval=diff_bval)

        assert dti.bval == diff_bval
        assert dti.bvec == diff_bvec

    def test_dti_metric_raises_exception_if_bvec_or_bval_missing(self):
        assert not os.path.exists(self.bval)
        assert not os.path.exists(self.bvec)

        with pytest.raises(datman.exceptions.QCException):
            datman.metrics.DTIMetrics(self.nii_input, self.output_dir)


class TestQAPHAMetrics:

    input_basename = "STUDY_SITE_SUBID_01_01_DTI60-1000_00_DESCR"
    nii_input = f"/tmp/{input_basename}.nii.gz"
    output_dir = "/tmp/test_metrics/"

    @patch("os.path.exists")
    def test_npar_output_ending_used_without_accel(self, mock_exist):
        mock_exist.return_value = True
        qa = datman.metrics.QAPHAMetrics(self.nii_input, self.output_dir)

        assert not qa.accel

        accel_outputs = ["-PAR." in fname for fname in qa.outputs["qa-dti"]]
        assert not any(accel_outputs)

        nonaccel_outputs = [
            "-NPAR." in fname for fname in qa.outputs["qa-dti"]
        ]
        assert any(nonaccel_outputs)

    @patch("os.path.exists")
    def test_par_output_ending_used_with_accel(self, mock_exist):
        accel_nii = self.nii_input.replace("_DESCR", "_NOASSET")
        mock_exist.return_value = True
        qa = datman.metrics.QAPHAMetrics(accel_nii, self.output_dir)

        assert qa.accel

        nonaccel_outputs = [
            "-NPAR." in fname for fname in qa.outputs["qa-dti"]
        ]
        assert not any(nonaccel_outputs)

        accel_outputs = ["-PAR." in fname for fname in qa.outputs["qa-dti"]]
        assert any(accel_outputs)
