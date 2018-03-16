#!/usr/bin/env python
"""
This copies and converts files in nii folder to a bids folder in BIDS format

Usage:
  nii_to_bids.py [options] <study>

Arguments:
    <study>                     Study name defined in master configuration .yml file
                                to convert to BIDS format

Options:
    --nii-dir PATH              Path to directory to copy nifti data from
    --bids-dir PATH             Path to directory to store data in BIDS format
    --fmriprep-out-dir PATH     Path to fmriprep output. Will copy subject
                                freesurfer data in fmriprep format. Will let fmriprep
                                skip this part of its process
    --freesurfer-dir PATH       Path to freesurfer data to copy into fmriprep-out-dir
    --log-to-server             If set, all log messages are sent to the configured
                                logging server.
    --debug                     Debug logging
"""
import datman.config as config
import datman.scanid as scanid
import logging, logging.handlers
import os, sys
import json, csv
import re
import datetime
import traceback
import nibabel
from docopt import docopt
from shutil import copyfile, copytree
from distutils import dir_util
from queue import *
from collections import Counter

logger = logging.getLogger(os.path.basename(__file__))

tag_map = dict()

def calculate_trt(data, nii_file):
    axis = {'i':0, 'j':1, 'k':2}[data['PhaseEncodingDirection'][0]]
    npe = nibabel.load(nii_file).shape[axis]
    acc = 1.0
    if 'ParallelReductionFactorInPlane' in data.keys():
        acc = dat['ParallelReductionFactorInPlane']
    trt = str(float(data["EffectiveEchoSpacing"])*(npe/acc-1))
    return trt

def to_sub(ident):
    try:
        int(ident.subject[0])
        return "sub-" + ident.site + ident.subject
    except ValueError:
        return "sub-" + ident.subject

def to_ses(timepoint):
    return "ses-{:02}".format(int(timepoint))

def to_run(run, tag):
    if ("DTI" in tag):
        run_num = "run-{:02}".format(int(run//4)+1)
    else:
        run_num = "run-{:02}".format(int(run//2)+1)
    return run_num

def to_bids_name(ident, tag, cnt_run, type_folder, ex):
    subject = to_sub(ident)
    session = to_ses(ident.timepoint)
    acq = "acq-{}".format(ident.site)
    run_num = to_run(cnt_run[tag], tag)

    if ex == ".gz":
        ext = ".nii.gz"
    else:
        ext = ex

    if (tag in tag_map['anat']):
        name = "{}_{}_{}_{}_{}{}"
        if (tag == "T1" or tag == "T2"):
            mod = tag + 'w'
        else:
            mod = tag
        return type_folder["anat"] + name.format(subject, session, acq,run_num, mod, ext)
    elif (tag in tag_map["fmri"]):
        name = "{}_{}_task-{}_{}_{}_bold{}"
        if (tag == "RST" or tag == "VN-SPRL"):
            run_num = to_run(cnt_run["RST"] + cnt_run["VN-SPRL"], tag)
            task = "rest"
        else:
            if (tag == "FACES"):
                task = "faces"
                if run_num[-2:] > "01":
                    logger.warning("More than one session of {} in {}".format(tag, str(ident)))
            elif (tag == "TMS-FMRI"):
                task = "tmsfmri"
            else:
                task = tag.lower()
        return type_folder["func"] + name.format(subject, session, task, acq, run_num, ext)
    elif (tag in tag_map["dmap_fmri"]):
        if ("-DAP" in tag):
            return type_folder["fmap"] + "{}_{}_{}_dir-{}_{}_epi{}".format(subject, session, acq, "AP", run_num, ext)
        elif ("-DPA" in tag):
            return type_folder["fmap"] + "{}_{}_{}_dir-{}_{}_epi{}".format(subject, session, acq, "PA", run_num, ext)
    elif (tag in tag_map["dti"]):
        return type_folder["dwi"] + "{}_{}_{}_{}_dwi{}".format(subject, session, acq, run_num, ext)
    else:
        raise ValueError("File could not be changed to bids format:{} {}".format(str(ident), tag))



def validify_file(subject_nii_path, sites):
    file_list = os.listdir(subject_nii_path)
    series_list = [scanid.parse_filename(x)[2] for x in file_list]
    valid_files = { k : list() for k in series_list }
    blacklist_files = set()
    num_faces = 0

    dap_queue = {site: Queue() for site in sites}
    dpa_queue = {site: Queue() for site in sites}
    # dap_queue = Queue()
    # dpa_queue = Queue()
    fmap_dict = dict()
    for filename in sorted(file_list, key=lambda x: scanid.parse_filename(x)[2], reverse=True):
        ident, tag, series, description = scanid.parse_filename(filename)
        site = ident.site
        valid_files[series].append(filename)
        ext = os.path.splitext(subject_nii_path + filename)[1]

        # anat validation
        if (tag == "T1" or tag == "T2") and (ext == ".json"):
            json_data = json.load(open(subject_nii_path + filename))
            if "NORM" in json_data["ImageType"]:
                logger.info("File has ImageType NORM and will be excluded from conversion: {}".format(
                    scanid.make_filename(ident, tag, series, description)))
                blacklist_files.add(series)
        elif ((tag in tag_map["fmri"]) and ext == ".gz"):
            dap_queue[site].put(series)
            dpa_queue[site].put(series)
        elif (tag in tag_map["dmap_fmri"] and ext == ".json"):
            fmap_dict[filename] = list()
            if ("-DAP" in tag):
                while not dap_queue[site].empty():
                    func_file = sorted(valid_files[dap_queue[site].get()])[1]
                    logger.info("{} has been mapped to {}".format(filename, func_file))
                    fmap_dict[filename].append(func_file)
            elif ("-DPA" in tag):
                while not dpa_queue[site].empty():
                    func_file = sorted(valid_files[dpa_queue[site].get()])[1]
                    logger.info("{} has been mapped to {}".format(filename, func_file))
                    fmap_dict[filename].append(func_file)

    for key in blacklist_files:
        valid_files.pop(key, None)

    file_list = list()
    for f in valid_files.values():
        file_list += f

    return file_list, fmap_dict

def modify_json(subject_nii_path, orig_json, bids_json, fmap_dict):
    try:
        with open(bids_json, "r+") as jsonFile:
            data = json.load(jsonFile)

            data["Intended For"] = fmap_dict[orig_json]

            if "TotalReadoutTime" not in data.keys():
                try:
                    nii_file = str.replace(subject_nii_path + orig_json, 'json', 'nii.gz')
                    data["TotalReadoutTime"] = calculate_trt(data, nii_file)
                except KeyError, key:
                    logger.warning(
                    "Total readout time cannot be calculated due to missing information {} in JSON for: {}".format(key, item))
                    return
            jsonFile.seek(0)  # rewind
            json.dump(data, jsonFile, sort_keys=True, indent=4, separators=(',', ': '))
            jsonFile.truncate()

    except IOError:
        logger.error('Failed to open: {}'.format(bids_name), exc_info=True)


def create_task_json(file_path, tags_list):
    task_names = dict()
    for tag in tags_list:
        if tag == "RST" or tag == "VN-SPRL":
            task_names["RST"] = ["RestingState", "task-rest_bold.json"]
        elif tag == "FACES":
            task_names["FACES"] = ["Faces", "task-faces_bold.json"]
        elif (tag == "TMS-FMRI"):
            task_names["TMS-FMRI"] = ["TMS-FMRI", "task-tmsfmri_bold.json"]
        else:
            task_names[tag] = [tag.lower(), "task-{}_bold.json".format(tag.lower())]

    for task in task_names.keys():
        data = dict()
        data["TaskName"] = task_names[task][0]
        create_json(file_path + task_names[task][1], data)
        logger.info("Location of TaskName json for {} will be: {}".format(task_names[task][0], task_names[task][1]))

def create_json(file_path, data_dict):
    try:
        logger.info("Creating: {}".format(file_path))
        with open(file_path, "w+") as json_file:
            json.dump(data_dict, json_file, sort_keys=True, indent=4, separators=(',', ': '))
    except IOError:
        logger.critical('Failed to open: {}'.format(file_path), exc_info=True)
        sys.exit(1)

def create_bids_dirs(bids_dir, ident):
    type_dir = dict()
    sub_dir = bids_dir + to_sub(ident) + "/"
    create_dir(sub_dir)
    ses_dir = sub_dir + to_ses(ident.timepoint) + "/"
    create_dir(ses_dir)
    for bid_type in ["anat", "func", "fmap", "dwi"]:
        type_dir[bid_type] = ses_dir + bid_type + "/"
        create_dir(type_dir[bid_type])
    return type_dir

def create_dir(dir_path):
    if not os.path.isdir(dir_path):
        logger.info("Creating: {}".format(dir_path))
        try:
            os.mkdir(dir_path)
        except OSError:
            logger.critical('Failed creating: {}'.format(dir_path), exc_info=True)
            sys.exit(1)

def setup_logger(filepath, to_server, debug, config):

    logger.setLevel(logging.DEBUG)

    date = str(datetime.date.today())

    fhandler = logging.FileHandler(filepath +  date + "-opt_to_bids.log", "w")
    fhandler.setLevel(logging.DEBUG)

    shandler = logging.StreamHandler()
    if debug:
        shandler.setLevel(logging.DEBUG)
    else:
        shandler.setLevel(logging.WARN)

    formatter = logging.Formatter("[%(name)s] %(asctime)s - %(levelname)s: %(message)s")

    fhandler.setFormatter(formatter)
    shandler.setFormatter(formatter)
    logger.addHandler(fhandler)
    logger.addHandler(shandler)

    if to_server:
        server_ip = config.get_key('LOGSERVER')
        server_handler = logging.handlers.SocketHandler(server_ip,
                logging.handlers.DEFAULT_TCP_LOGGING_PORT)
        server_handler.setLevel(logging.CRITICAL)
        logger.addHandler(server_handler)


def init_setup(study, to_server, debug, bids_dir, nii_dir, fmriprep_dir, fs_dir):
    cfg = config.config(study=study)
    logger.info("Study to convert to BIDS Format: {}".format(study))

    if not bids_dir:
        bids_dir =  cfg.get_path('data') + "bids/"
        create_dir(bids_dir)

    if not nii_dir:
        nii_dir = cfg.get_path('nii')
        logger.info("Nii files to be converted to BIDS format will be from: {}".format(nii_dir))

    if fmriprep_dir:
        fmriprep_fs_dir = os.path.join(fmriprep_dir, 'freesurfer')
        create_dir(fmriprep_fs_dir)

    if not fs_dir:
        fs_dir = cfg.get_path('freesurfer')

    bidsignore_path = bids_dir + ".bidsignore"
    bidsignore = 'echo "*-opt_to_bids.log\nmatch.csv" > {}'.format(bidsignore_path)
    os.system(bidsignore)

    setup_logger(bids_dir, to_server, debug, cfg)
    logger.info("BIDS folder will be {}".format(bids_dir))

    data = dict()
    data["Name"] = "Optimum Neuro"
    data["BIDSVersion"] = "1.0.2"

    create_json(bids_dir + "dataset_description.json", data )
    logger.info("Location of Dataset Description: {}".format(bids_dir + "dataset_description.json"))

    all_tags = cfg.get_tags()
    global tag_map
    tag_map = {all_tags.get(x, "qc_type") : [] for x in all_tags.keys()}
    for tag in all_tags.keys():
        tag_map[all_tags.get(tag, "qc_type")].append(tag)


    to_delete = set()

    return cfg, bids_dir,all_tags.keys(), nii_dir, fmriprep_fs_dir, fs_dir, to_delete


def main():
    arguments = docopt(__doc__)

    study  = arguments['<study>']
    nii_dir = arguments['--nii-dir']
    bids_dir = arguments['--bids-dir']
    fmriprep_dir = arguments['--fmriprep-out-dir']
    fs_dir = arguments['--freesurfer-dir']
    to_server = arguments['--log-to-server']
    debug  = arguments['--debug']

    cfg, bids_dir,all_tags, nii_dir,fmriprep_fs_dir, fs_dir, to_delete = init_setup(study, to_server, debug, bids_dir, nii_dir, fmriprep_dir, fs_dir)
    sites = cfg.study_config['Sites'].keys()

    logger.info("Beginning to iterate through folders/files in {}".format(nii_dir))
    study_tags = set()

    csvfile = open(bids_dir + 'match.csv', 'wb')
    csvwriter = csv.writer(csvfile)
    csvwriter.writerow(['CAMH','BIDS'])


    for subject_dir in os.listdir(nii_dir):
        if scanid.is_phantom(subject_dir):
            logger.info("File is phantom and will be ignored: {}".format(subject_dir))
            continue
        parsed = scanid.parse(subject_dir)

        type_folders = create_bids_dirs(bids_dir, parsed)
        subject_nii_path = nii_dir + subject_dir + "/"
        logger.info("Will now begin creating files in BIDS format for: {}".format(subject_nii_path))
        valid_files, fmap_dict = validify_file(subject_nii_path, sites)

        if fmriprep_dir:
            fs_src = os.path.join(fs_dir, subject_dir)
            fs_dst = os.path.join(fmriprep_fs_dir, to_sub(parsed))
            if os.path.isdir(fs_src):
                dir_util.copy_tree(fs_src, fs_dst)

        cnt = {k : 0 for k in all_tags}
        for item in sorted(valid_files, key=lambda x: scanid.parse_filename(x)[2]):
            ident, tag, series, description =scanid.parse_filename(item)
            ext = os.path.splitext(subject_nii_path + item)[1]
            if tag in tag_map["fmri"]:
                study_tags.add(tag)
            try:
                bids_name = to_bids_name(ident, tag, cnt, type_folders, ext)
            except ValueError, err:
                logger.warning(err)
                continue
            copyfile(subject_nii_path + item, bids_name)
            logger.info("{:<80} {:<80}".format(item, bids_name))
            csvwriter.writerow([item, os.path.relpath(bids_name, start=bids_dir)])

            cnt[tag] +=1
            if (ext == ".json" and item in fmap_dict.keys()):
                modify_json(subject_nii_path, item, bids_name, fmap_dict)

        for key in type_folders.keys():
            if os.listdir(type_folders[key]) == []:
                to_delete.add(type_folders[key])

    create_task_json(bids_dir, study_tags)
    csvfile.close()

    logger.info("Deleting unecessary BIDS folders")
    for folder in to_delete:
        try:
            logger.info("Deleting: {}".format(folder))
            os.rmdir(folder)
        except Exception, e:
            logger.info("Folder {} contains multiple acquistions. Should not be deleted.")


if __name__ == '__main__':
    main()
