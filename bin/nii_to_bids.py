#!/usr/bin/env python
"""
This copies and converts files in nii folder to a bids folder in BIDS format

Usage:
  to_bids.py [options] <study>

Arguments:
    <study>             study name defined in master configuration .yml file
                        to convert to BIDS format

Options:
    --nii_dir PATH     Path to directory to copy nifti data from
    --bids_dir PATH     Path to directory to store data in BIDS format
    --log-to-server     If set, all log messages are sent to the configured
                        logging server.
    --debug             debug logging
"""
import datman.config as config
import datman.scanid as scanid
import logging, logging.handlers
import os, sys
import json
import re
import datetime
import traceback
import nibabel
from docopt import docopt
from shutil import copyfile
from queue import *
from collections import Counter

logger = logging.getLogger(os.path.basename(__file__))

bid_types = ["anat", "func", "fmap", "dwi"]
tags_pattern = re.compile(r'^T1$|^T2$|^FMRI-DAP$|^FMRI-DPA$|^RST$|^FACES$|^DTI-[A-Z]+')
tag_map = dict()
needed_json = set()

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
    timepoint = to_ses(ident.timepoint)
    run_num = to_run(cnt_run[tag], tag)

    if ex == ".gz":
        ext = ".nii.gz"
    else:
        ext = ex

    if (tag == "T1" or tag == "T2"):
        return type_folder["anat"] + "{}_{}_{}w{}".format(subject, timepoint, tag, ext)
    elif (tag in tag_map["fmri"]):
        name = "{}_{}_task-{}_{}_bold{}"
        if (tag == "RST" or tag == "VN-SPRL"):
            run_num = to_run(cnt_run["RST"] + cnt_run["VN-SPRL"], tag)
            task = "rest"
        else:
            if run_num[-2:] > "01":
                logger.warning("More than one session of {} in {}".format(tag, str(ident)))
            if (tag == "FACES"):
                task = "faces"
            elif (tag == "TMS-FMRI"):
                task = "tmsfmri"
            else:
                task = tag.lower()
        return type_folder["func"] + name.format(subject, timepoint, task, run_num, ext)
    elif (tag in tag_map["dmap_fmri"]):
        if ("-DAP" in tag):
            return type_folder["fmap"] + "{}_{}_dir-{}_{}_epi{}".format(subject, timepoint, "AP", run_num, ext)
        elif ("-DPA" in tag):
            return type_folder["fmap"] + "{}_{}_dir-{}_{}_epi{}".format(subject, timepoint, "PA", run_num, ext)
    elif (tag in tag_map["dti"]):
        return type_folder["dwi"] + "{}_{}_{}_dwi{}".format(subject, timepoint, run_num, ext)
    else:
        raise ValueError("File could not be changed to bids format:{} {}".format(str(ident), tag))



def validify_file(path, file_list):
    global needed_json

    series_list = [scanid.parse_filename(x)[2] for x in file_list]
    valid_files = { k : list() for k in series_list }
    blacklist_files = set()
    num_faces = 0

    dap_queue = Queue()
    dpa_queue = Queue()
    fmap_dict = dict()
    for filename in sorted(file_list, key=lambda x: scanid.parse_filename(x)[2], reverse=True):
        ident, tag, series, description = scanid.parse_filename(filename)
        valid_files[series].append(filename)
        ext = os.path.splitext(path + filename)[1]

        # anat validation
        if (tag == "T1" or tag == "T2") and (ext == ".json"):
            json_data = json.load(open(path + filename))
            if "NORM" in json_data["ImageType"]:
                logger.info("File has ImageType NORM and will be excluded from conversion: {}".format(
                    scanid.make_filename(ident, tag, series, description)))
                blacklist_files.add(series)
        elif ((tag in tag_map["fmri"]) and ext == ".gz"):
            dap_queue.put(series)
            dpa_queue.put(series)
            needed_json.add(tag)
        elif (tag in tag_map["dmap_fmri"] and ext == ".json"):
            fmap_dict[filename] = list()
            if ("-DAP" in tag):
                while not dap_queue.empty():
                    func_file = sorted(valid_files[dap_queue.get()])[1]
                    logger.info("{} has been mapped to {}".format(filename, func_file))
                    fmap_dict[filename].append(func_file)
            elif ("-DPA" in tag):
                while not dpa_queue.empty():
                    func_file = sorted(valid_files[dpa_queue.get()])[1]
                    logger.info("{} has been mapped to {}".format(filename, func_file))
                    fmap_dict[filename].append(func_file)
        # general validation
        # else:
        #     logger.error("File does not match tag pattern to convert to BIDS format: {}".format(
        #         scanid.make_filename(ident, tag, series, description, ext=ext)))
        #     blacklist_files.add(series)


    for key in blacklist_files:
        valid_files.pop(key, None)

    file_list = list()
    for f in valid_files.values():
        file_list += f

    return file_list, fmap_dict

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

def create_bids_dirs(bids_folder, ident):
    type_folder = dict()
    sub_folder = bids_folder + to_sub(ident) + "/"
    create_dir(sub_folder)
    ses_folder = sub_folder + to_ses(ident.timepoint) + "/"
    create_dir(ses_folder)
    for bid_type in bid_types:
        type_folder[bid_type] = ses_folder + bid_type + "/"
        create_dir(type_folder[bid_type])
    return type_folder

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

    formatter = logging.Formatter("[%(name)s] %(levelname)s: %(message)s")

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


def init_setup(study, to_server, debug, bids_folder, nii_folder):
    cfg = config.config(study=study)
    logger.info("Study to convert to BIDS Format: {}".format(study))

    if not bids_folder:
        bids_folder =  cfg.get_path('data') + "bids/"
        create_dir(bids_folder)

    bidsignore_path = bids_folder + ".bidsignore"
    bidsignore = 'echo "*-opt_to_bids.log" > {}'.format(bidsignore_path)
    os.system(bidsignore)


    setup_logger(bids_folder, to_server, debug, cfg)
    logger.info("BIDS folder will be {}".format(bids_folder))

    data = dict()
    data["Name"] = "Optimum Neuro"
    data["BIDSVersion"] = "1.0.2"

    create_json(bids_folder + "dataset_description.json", data )
    logger.info("Location of Dataset Description: {}".format(bids_folder + "dataset_description.json"))

    all_tags = cfg.get_tags()
    global tag_map
    tag_map = {all_tags.get(x, "qc_type") : [] for x in all_tags.keys()}
    for tag in all_tags.keys():
        tag_map[all_tags.get(tag, "qc_type")].append(tag)

    if not nii_folder:
        nii_folder = cfg.get_path('nii')
        logger.info("Nii files to be converted to BIDS format will be from: {}".format(nii_folder))
    to_delete = set()
    return cfg, bids_folder,all_tags.keys(), nii_folder, to_delete


def main():
    arguments = docopt(__doc__)

    study  = arguments['<study>']
    nii_folder = arguments['--nii_dir']
    bids_folder = arguments['--bids_dir']
    to_server = arguments['--log-to-server']
    debug  = arguments['--debug']

    cfg, bids_folder,all_tags, nii_folder, to_delete = init_setup(study, to_server, debug, bids_folder, nii_folder)

    logger.info("Beginning to iterate through folders/files in {}".format(nii_folder))
    study_tags = set()
    for item in os.listdir(nii_folder):
        if scanid.is_phantom(item):
            logger.info("File is phantom and will be ignored: {}".format(item))
            continue
        parsed = scanid.parse(item)

        type_folders = create_bids_dirs(bids_folder, parsed)
        item_list_path = nii_folder + item + "/"
        item_list = os.listdir(item_list_path)
        logger.info("Will now begin creating files in BIDS format for: {}".format(item_list_path))
        valid_files, fmap_dict = validify_file(item_list_path, item_list)
        cnt = {k : 0 for k in all_tags}
        for initem in sorted(valid_files, key=lambda x: scanid.parse_filename(x)[2]):
            ident, tag, series, description =scanid.parse_filename(initem)
            ext = os.path.splitext(item_list_path + initem)[1]
            if tag in tag_map["fmri"]:
                study_tags.add(tag)
            try:
                bids_name = to_bids_name(ident, tag, cnt, type_folders, ext)
            except ValueError, err:
                logger.error(err)
                continue
            copyfile(item_list_path + initem,bids_name)
            logger.info("{:<80} {:<80}".format(initem, to_bids_name(ident, tag, cnt, type_folders, ext)))
            cnt[tag] +=1
            if ext == ".json":
                try:
                    with open(bids_name, "r+") as jsonFile:
                        data = json.load(jsonFile)

                        if initem in fmap_dict.keys():
                            data["Intended For"] = fmap_dict[initem]

                        if "TotalReadoutTime" not in data.keys():
                            try:
                                nii_file = str.replace(item_list_path + initem, 'json', 'nii.gz')
                                data["TotalReadoutTime"] = calculate_trt(data, nii_file)
                            except KeyError, key:
                                logger.warning(
                                "Total readout time cannot be calculated due to missing information {} in JSON for: {}".format(key, initem))
                                continue
                        jsonFile.seek(0)  # rewind
                        json.dump(data, jsonFile, sort_keys=True, indent=4, separators=(',', ': '))
                        jsonFile.truncate()

                except IOError:
                    logger.error('Failed to open: {}'.format(bids_name), exc_info=True)

        for key in type_folders.keys():
            if os.listdir(type_folders[key]) == []:
                to_delete.add(type_folders[key])

    create_task_json(bids_folder, study_tags)


    logger.info("Deleting unecessary BIDS folders")
    for folder in to_delete:
        logger.info("Deleting: {}".format(folder))
        os.rmdir(folder)


if __name__ == '__main__':
    main()
