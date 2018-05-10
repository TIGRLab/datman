#!/usr/bin/env python

import os
from glob import glob
import errno

import dicom as dcm
import nibabel.nicom.csareader as csareader

import datman.config
import datman.utils
import datman.scanid


def create_json(dcm_file, nii_file):


def get_bids_phase_encoding_direction(dicom_path):
    """Return BIDS PhaseEncodingDirection string (i, j, k, i-, j-, k-) for
    DICOM at dicom_path.
    """
    rowcol_to_niftidim = {'COL': 'i', 'ROW': 'j'}
    pedp_to_sign = {0: '-', 1: ''}
    dcm = pydicom.read_file(dicom_path)
    inplane_pe_dir = dcm_pa[int('00181312', 16)].value
    csa_str = dcm[int('00291010', 16)].value
    csa_tr = csareader.read(csa_str)
    pedp = csa_tr['tags']['PhaseEncodingDirectionPositive']['items'][0]
    ij = rowcol_to_niftidim[inplane_pe_dir]
    sign = pedp_to_sign[pedp]
    return '{}{}'.format(ij, sign)


def create_header_dict(ds):
    headers = {}
    header_tags = ["Manufacturer",
                   "ManufacturerModelName",
                   # "ManufacturersModelName",
                   "ImageType",
                   "MagneticFieldStrength",
                   "FlipAngle",
                   "EchoTime",
                   "RepetitionTime",
                   "EffectiveEchoSpacing",
                   "SliceTiming",
                   "PhaseEncodingDirection"]
    for tag in header_tags:
        try:
            headers[tag] = getattr(ds, tag)
        except AttributeError:
            print("{}-{} does not have {}".format(
                ds.PatientName, ds.SeriesDescription, tag))
    return headers


def create_json(file_path, data_dict):
    try:
        logger.info("Creating: {}".format(file_path))
        with open(file_path, "w+") as json_file:
            json.dump(data_dict, json_file, sort_keys=True, indent=4, separators=(',', ': '))
    except IOError:
        logger.critical('Failed to open: {}'.format(file_path), exc_info=True)
        sys.exit(1)


def create_symlink(src, target_name, dest):
    datman.utils.define_folder(dest)
    target_path = os.path.join(dest, target_name)
    if os.path.islink(target_path):
        print("nifti ", target_path, "already exists")
    else:
        with datman.utils.cd(dest):
            rel_path = os.path.relpath(src, dest)
            try:
                os.symlink(rel_path, target_path)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise
                pass


study = 'OPT'

# setup the config object
cfg = datman.config.config(study=study)

# get paths
dir_nii = cfg.get_path('nii')
dir_res = cfg.get_path('resources')
dir_dcm = cfg.get_path('dcm')

site = 'CU1'

if site:
    sessions = [subject for subject in os.listdir(dir_res)
                if datman.scanid.parse(subject).site == site]
if session:
    sessions = [session]
else:
    sessions = os.listdir(dir_res)

print('Processing {} sessions'.format(len(sessions)))
for session in sessions:
    try:
        ident = datman.scanid.parse(session)
    except datman.scanid.ParseException:
        print('Invalid session:{}'.format(session))
        pass

    session_res_dir = os.path.join(dir_res, session)
    extensions = ('**/*.nii.gz', '**/*.bvec', '**/*.bval')
    session_res_files = []
    for extension in extensions:
        session_res_files.extend(
            glob(os.path.join(session_res_dir, extension), recursive=True)
        )

    session_name = ident.get_full_subjectid_with_timepoint()
    session_nii_dir = os.path.join(dir_nii, session_name)
    session_dcm_dir = os.path.join(dir_dcm, session_name)

    if session_res_files:
        datman.utils.define_folder(dir_nii)
        session_dcm_files = os.listdir(session_dcm_dir)
        dcm_dict = {int(datman.scanid.parse_filename(dcm)[2]):
                    dcm for dcm in session_dcm_files}
        for f in session_res_files:
            series_num = int(os.path.basename(f).split("_")[1][1:])
            try:
                scan_filename = os.path.splitext(dcm_dict[series_num])[0]
            except:
                print("dcm not found for ", f)
            ext = os.path.splitext(f)[1]
            nii_name = scan_filename + ext
            create_symlink(f, nii_name, session_nii_dir)
            if f.endswith('.nii.gz'):
                ds = dcm.read_file(
                    os.path.join(session_dcm_dir, dcm_dict[series_num])
                )
                header_dict = create_header_dict(ds)
                print(header_dict)
