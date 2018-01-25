#!/usr/bin/env python
import datman.config as config
import datman.scanid as scanid
import logging, logging.handlers
import os, sys
import json
import re
import datetime
import traceback
from datman.docopt import docopt
from shutil import copyfile
from queue import *
from collections import Counter

logger = logging.getLogger(os.path.basename(__file__))

bid_types = ["anat", "func", "fmap", "dwi"]
tags_pattern = re.compile(r'^T1$|^T2$|^FMRI-DAP$|^FMRI-DPA$|^RST$|^FACES$|^DTI-[A-Z]+')

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

def to_bids_name(ident, tag, run, type_folder, ex):
    subject = to_sub(ident)
    timepoint = to_ses(ident.timepoint)
    run_num = to_run(run, tag)

    if ex == ".gz":
        ext = ".nii.gz"
    else:
        ext = ex

    if not tags_pattern.match(tag):
        return "File could not be changed to bids format:{} {}".format(str(ident), tag)
    elif (tag == "T1" or tag == "T2"):
        return type_folder["anat"] + "{}_{}_{}w{}".format(subject, timepoint, tag, ext)
    elif (tag == "RST"):
        return type_folder["func"] + "{}_{}_task-{}_{}_bold{}".format(subject, timepoint, "rest", run_num, ext)
    elif (tag == "FACES"):
        return type_folder["func"] + "{}_{}_task-{}_bold{}".format(subject, timepoint, "faces", ext)
    elif ("-DAP" in tag):
        return type_folder["fmap"] + "{}_{}_dir-{}_{}_epi{}".format(subject, timepoint, "AP", run_num, ext)
    elif ("-DPA" in tag):
        return type_folder["fmap"] + "{}_{}_dir-{}_{}_epi{}".format(subject, timepoint, "PA", run_num, ext)
    elif ("DTI" in tag):
        return type_folder["dwi"] + "{}_{}_dwi{}".format(subject, timepoint, ext)

def validify_file(path, file_list):

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
        # general validation
        if not tags_pattern.match(tag):
            logger.error("File does not match tag pattern to convert to BIDS format: {}".format(
                scanid.make_filename(ident, tag, series, description, ext=ext)))
            blacklist_files.add(series)
            continue
        # anat validation
        if (tag == "T1" or tag == "T2") and (ext == ".json"):
            json_data = json.load(open(path + filename))
            if "NORM" in json_data["ImageType"]:
                logger.info("File has ImageType NORM and will be excluded from conversion: {}".format(
                    scanid.make_filename(ident, tag, series, description)))
                blacklist_files.add(series)
        elif ((tag == "FACES" or tag == "RST") and ext == ".gz"):
            if (tag == "FACES"):
                num_faces+= 1
            dap_queue.put(series)
            dpa_queue.put(series)
        elif (tag == "FMRI-DAP" and ext == ".json"):
            fmap_dict[filename] = list()
            while not dap_queue.empty():
                func_file = sorted(valid_files[dap_queue.get()])[1]
                logger.info("{} has been mapped to {}".format(filename, func_file))
                fmap_dict[filename].append(func_file)
        elif (tag == "FMRI-DPA" and ext == ".json"):
            fmap_dict[filename] = list()
            while not dpa_queue.empty():
                func_file = sorted(valid_files[dpa_queue.get()])[1]
                logger.info("{} has been mapped to {}".format(filename, func_file))
                fmap_dict[filename].append(func_file)

    if num_faces > 1:
        log.error("More than one session of FACES in {}".format(path))

    for key in blacklist_files:
        valid_files.pop(key, None)

    file_list = list()
    for f in valid_files.values():
        file_list += f

    return file_list, fmap_dict

def create_task_json(file_path, tags_list):
    task_names = dict()
    if "RST" in tags_list:
        task_names["RST"] = ["RestingState", "task-rest_bold.json"]
    if "FACES" in tags_list:
        task_names["FACES"] = ["Faces", "task-faces_bold.json"]
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

def setup_logger(filepath, debug, config):

    logger.setLevel(logging.DEBUG)

    date = str(datetime.date.today())

    fhandler = logging.FileHandler(filepath +  date + "-opt_to_bids.log", "w")
    fhandler.setLevel(logging.DEBUG)

    shandler = logging.StreamHandler()
    if debug:
        shandler.setLevel(logging.DEBUG)
    else:
        shandler.setLevel(logging.WARN)

    server_ip = config.get_key('LOGSERVER')
    server_handler = logging.handlers.SocketHandler(server_ip,
            logging.handlers.DEFAULT_TCP_LOGGING_PORT)
    server_handler.setLevel(logging.CRITICAL)


    formatter = logging.Formatter("[%(name)s] %(levelname)s: %(message)s")

    fhandler.setFormatter(formatter)
    shandler.setFormatter(formatter)
    logger.addHandler(fhandler)
    logger.addHandler(shandler)
    logger.addHandler(server_handler)

def init_setup(study, debug):
    cfg = config.config(study=study)
    logger.info("Study to convert to BIDS Format: {}".format(study))

    bids_folder =  cfg.get_path('data') + "bids/"
    create_dir(bids_folder)

    setup_logger(bids_folder, debug, cfg)
    logger.info("BIDS folder will be {}".format(bids_folder))

    data = dict()
    data["Name"] = "Optimum Neuro"
    data["BIDSVersion"] = "1.0.2"

    create_json(bids_folder + "dataset_description.json", data )
    logger.info("Location of Dataset Description: {}".format(bids_folder + "dataset_description.json"))

    all_tags = cfg.get_tags().keys()
    create_task_json(bids_folder, all_tags)

    nii_path = cfg.get_path('nii')
    logger.info("Nii files to be converted to BIDS format will be from: {}".format(nii_path))
    to_delete = set()
    return cfg, bids_folder,all_tags, nii_path, to_delete


def main():
    cfg, bids_folder,all_tags, nii_path, to_delete = init_setup("OPT", "--debug" in sys.argv)

    logger.info("Beginning to iteratre through folders/files in {}".format(nii_path))
    for item in os.listdir(nii_path):
        if scanid.is_phantom(item):
            logger.info("File is phantom and will be ignored: {}".format(item))
        if not scanid.is_phantom(item):
            parsed = scanid.parse(item)

            type_folders = create_bids_dirs(bids_folder, parsed)
            item_list_path = nii_path + item + "/"
            item_list = os.listdir(item_list_path)
            logger.info("Will now begin creating files in BIDS format for: {}".format(item_list_path))
            valid_files, fmap_dict = validify_file(item_list_path, item_list)
            cnt = {k : 0 for k in all_tags}
            for initem in sorted(valid_files, key=lambda x: scanid.parse_filename(x)[2]):
                ident, tag, series, description =scanid.parse_filename(initem)
                ext = os.path.splitext(item_list_path + initem)[1]
                bids_name = to_bids_name(ident, tag, cnt[tag], type_folders, ext)
                copyfile(item_list_path + initem,bids_name)
                logger.info("{:<80} {:<80}".format(initem, to_bids_name(ident, tag, cnt[tag], type_folders, ext)))
                if initem in fmap_dict.keys():
                    try:
                        with open(bids_name, "r+") as jsonFile:
                            data = json.load(jsonFile)

                            data["Intended For"] = fmap_dict[initem]

                            jsonFile.seek(0)  # rewind
                            json.dump(data, jsonFile, sort_keys=True, indent=4, separators=(',', ': '))
                            jsonFile.truncate()
                    except IOError:
                        logger.error('Failed to open: {}'.format(file_path), exc_info=True)
                cnt[tag] +=1

            for key in type_folders.keys():
                if os.listdir(type_folders[key]) == []:
                    to_delete.add(type_folders[key])

    logger.info("Deleting unecessary BIDS folders")
    for folder in to_delete:
        logger.info("Deleting: {}".format(folder))
        os.rmdir(folder)


if __name__ == '__main__':
    main()
