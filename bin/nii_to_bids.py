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
import datman.utils
import logging, logging.handlers
import os, sys, path
import json, csv
import re
import datetime
import traceback
import nibabel, numpy
import glob
from docopt import docopt
from shutil import copyfile, copytree
from distutils import dir_util
from queue import *
from collections import Counter

logger = logging.getLogger(__name__)
dmlogger = logging.getLogger('datman.utils')

tag_map = dict()

def validify_fmap(fmap):
    img = nibabel.load(fmap)
    hdr = img.header
    if (hdr['srow_z'][2] == 0):
        value = hdr['pixdim'][3]
        hdr['srow_z'][2] = value
        img.affine[2][2] = value
        nibabel.save(img, fmap)

def get_missing_data(data, nii_file, site):
    try:
        img = nibabel.load(nii_file)
    except:
        logger.error("Could not open {}".format(nii_file))
        return
    if ('EffectiveEchoSpacing' not in data.keys()) and site == 'CMH':
        data['EffectiveEchoSpacing'] = 0.000342
    if "RepetitionTime" not in data.keys():
        data['RepetitionTime'] = int(img.header['pixdim'][4])
    if ("task" in nii_file):
        slices = float(img.shape[2])
        tr = float(data['RepetitionTime'])
        spacing = tr/slices
        timing_list = [round(x,4) for x in numpy.arange(0, tr, spacing)]
        half = len(timing_list)//2
        first = timing_list[:half]
        second = timing_list[half:]
        to_return = list()
        while (len(first) > 0 and len(second) > 0):
            to_return.append(first.pop(0))
            to_return.append(second.pop(0))
        to_return += first + second
        data['SliceTiming'] = to_return
    if "TotalReadoutTime" not in data.keys():
        try:
            axis = {'i':0, 'j':1, 'k':2}[data['PhaseEncodingDirection'][0]]
            npe = img.shape[axis]
            acc = 1.0
            if 'ParallelReductionFactorInPlane' in data.keys():
                acc = dat['ParallelReductionFactorInPlane']
            data["TotalReadoutTime"] = str(float(data["EffectiveEchoSpacing"])*(npe/acc-1))
        except KeyError, key:
            logger.info(
            "Total readout time cannot be calculated due to missing information {} in JSON for: {}".format(key, nii_file))

def to_sub(ident):
    try:
        int(ident.subject[0])
        return "sub-" + ident.site + ident.subject
    except ValueError:
        return "sub-" + ident.subject

def to_ses(timepoint):
    return "ses-{:02}".format(int(timepoint))

def to_run(run):
    run_num = "run-{:02}".format(run + 1)
    return run_num

def to_bids_name(ident, tag, cnt_run, type_folder, ex):
    subject = to_sub(ident)
    session = to_ses(ident.timepoint)
    acq = "acq-{}".format(ident.site)
    run_num = to_run(cnt_run[tag])

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
        return type_folder["anat"], name.format(subject, session, acq,run_num, mod, ext)
    elif (tag in tag_map["fmri"]):
        name = "{}_{}_task-{}_{}_{}_bold{}"
        if (tag == "RST" or tag == "VN-SPRL"):
            run_num = to_run(cnt_run["RST"] + cnt_run["VN-SPRL"])
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
        return type_folder["func"] , name.format(subject, session, task, acq, run_num, ext)
    elif (tag in tag_map["dmap_fmri"]):
        if ("-DAP" in tag):
            return type_folder["fmap"] , "{}_{}_{}_dir-{}_{}_epi{}".format(subject, session, acq, "AP", run_num, ext)
        elif ("-DPA" in tag):
            return type_folder["fmap"] , "{}_{}_{}_dir-{}_{}_epi{}".format(subject, session, acq, "PA", run_num, ext)
    elif (tag in tag_map["dti"]):
        dtiacq = "{}{}".format(acq, tag.translate(None, "DTI-"))
        return type_folder["dwi"] , "{}_{}_{}_{}_dwi{}".format(subject, session, dtiacq, run_num, ext)
    elif ("FMAP" in tag and not (ext == ".json")):
        return type_folder["fmap"] , "{}_{}_{}_{}_{}{}".format(subject, session, acq, run_num, tag, ext)
    else:
        raise ValueError("File could not be changed to bids format:{} {}".format(str(ident), tag))

def validify_file(subject_nii_path):
    file_list = os.listdir(subject_nii_path)
    series_list = [scanid.parse_filename(x)[2] for x in file_list]
    valid_files = { k : list() for k in series_list }
    blacklist_files = set()
    num_faces = 0

    dap_queue = Queue()
    dpa_queue = Queue()
    six_queue = Queue()
    eight_queue = Queue()

    dmap_dict = dict()
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
            dap_queue.put(series)
            dpa_queue.put(series)
            six_queue.put(series)
            eight_queue.put(series)
        elif (tag in tag_map["dmap_fmri"] and ext == ".json"):
            dmap_dict[filename] = list()
            if ("-DAP" in tag):
                while not dap_queue.empty():
                    func_file = sorted(valid_files[dap_queue.get()], reverse=True)[0]
                    logger.info("{} has been mapped to {}".format(filename, func_file))
                    dmap_dict[filename].append(func_file)
            elif ("-DPA" in tag):
                while not dpa_queue.empty():
                    func_file = sorted(valid_files[dpa_queue.get()], reverse=True)[0]
                    logger.info("{} has been mapped to {}".format(filename, func_file))
                    dmap_dict[filename].append(func_file)
            six_queue.queue.clear()
            eight_queue.queue.clear()
        elif ('FMAP' in tag and ext == '.gz'):
            if ('-6.5' in tag):
                fmap_dict[filename] = list()
                while not six_queue.empty():
                    func_file = sorted(valid_files[six_queue.get()], reverse=True)[0]
                    logger.info("{} has been mapped to {}".format(filename, func_file))
                    fmap_dict[filename].insert(0, func_file)
            dap_queue.queue.clear()
            dpa_queue.queue.clear()

    for key in blacklist_files:
        valid_files.pop(key, None)

    file_list = list()
    for f in valid_files.values():
        file_list += f

    return file_list, dmap_dict, fmap_dict

def modify_map_json(orig, bids, dmap_dict, fmap_dict, csv_dict, site):

    is_map = False
    if orig in fmap_dict.keys():
        pattern = re.compile(r'FMAP-\d\.5\.nii\.gz')
        bids = pattern.sub("fieldmap.json", bids )
        nii_file = str.replace(bids, 'json', 'nii.gz')
        intended_fors = fmap_dict
        is_map = True

    elif orig in dmap_dict.keys():
        nii_file = str.replace(bids, 'json', 'nii.gz')
        intended_fors = dmap_dict
        is_map = True
    elif ('.nii.gz' in orig and "FMAP" not in orig):
        nii_file = bids
        bids = str.replace(nii_file, 'nii.gz', 'json')
    else:
        return
    try:
        jsonFile = open(bids, "r+")
        data = json.load(jsonFile)
    except:
        try:
            jsonFile = open(bids, "w")
            data = dict()
        except IOError:
            logger.error('Failed to open: {}'.format(bids), exc_info=True)
            return

    if is_map and len(intended_fors) > 0:
        data['IntendedFor'] = list()
        for nii in intended_fors[orig]:
            bids_path = csv_dict[nii][1]
            split = bids_path.split('/')
            s = len(split)
            bids_name = os.path.join(split[s-3], split[s-2], split[s-1])
            data["IntendedFor"].append(bids_name)

    if orig in fmap_dict.keys():
        data['Units'] = 'rad/s'

    get_missing_data(data, nii_file, site)
    jsonFile.seek(0)  # rewind
    json.dump(data, jsonFile, sort_keys=True, indent=4, separators=(',', ': '))
    jsonFile.truncate()


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
    dmlogger.setLevel(logging.DEBUG)
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
    dmlogger.addHandler(shandler)

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
    else:
        fmriprep_fs_dir = None

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

    logger.info("Creating match.csv to hold original name, bids location and freesurfer location.")
    csvfile = open(bids_dir + 'match.csv', 'w+')
    csvwriter = csv.writer(csvfile)
    csvwriter.writerow(['CAMH','BIDS', 'FREESURFER'])
    csv_dict = dict()

    logger.info("Beginning to iterate through folders/files in {}".format(nii_dir))
    study_tags = set()
    fmap_dict = dict()
    dmap_dict = dict()

    for subject_dir in sorted(os.listdir(nii_dir)):
        if scanid.is_phantom(subject_dir):
            logger.info("File is phantom and will be ignored: {}".format(subject_dir))
            continue
        parsed = scanid.parse(subject_dir)

        type_folders = create_bids_dirs(bids_dir, parsed)
        subject_nii_path = nii_dir + subject_dir + "/"
        logger.info("Will now begin creating files in BIDS format for: {}".format(subject_nii_path))
        valid_files, dmap_d, fmap_d = validify_file(subject_nii_path)
        series_set = set(scanid.parse_filename(x)[2] for x in valid_files)

        fmap_dict.update(fmap_d)
        dmap_dict.update(dmap_d)

        if fmriprep_dir:
            fs_src = os.path.join(fs_dir, subject_dir)
            sub_ses = "{}_{}".format(to_sub(parsed), to_ses(parsed.timepoint))
            fs_dst = os.path.join(fmriprep_fs_dir, sub_ses)
            if os.path.isdir(fs_src):
                dir_util.copy_tree(fs_src, fs_dst)
                logger.warning("Copied {} to {}".format(fs_src, fs_dst))


        cnt = {k : 0 for k in all_tags}
        for series in sorted(series_set):
            timepoint = 1
            filename_base = "{}0{}_*_{}_*".format(str(parsed), timepoint, series)
            series_files = glob.glob(os.path.join(subject_nii_path,filename_base))
            series_tag = None
            for item in series_files:
                ident, tag, series, description =scanid.parse_filename(item)
                ext = os.path.splitext(subject_nii_path + item)[1]
                try:
                    type_dir, bids_name = to_bids_name(ident, tag, cnt, type_folders, ext)
                except ValueError, err:
                    logger.info(err)
                    continue
                if tag in tag_map["fmri"]:
                    study_tags.add(tag)
                copyfile(item, type_dir + bids_name, )
                #if "nii.gz" in bids_name and ("dwi" in bids_name or "task" in bids_name):
                    # os.system('fslroi {} {} 4 -1'.format(type_dir + bids_name, type_dir + bids_name))
                    #logger.warning("Finished fslroi on {}".format(bids_name))
                logger.warning("{:<70} {:<80}".format(os.path.basename(item), bids_name))
                csv_dict[os.path.basename(item)] = [type_dir + bids_name]
                if fmriprep_dir and os.path.isdir(fs_src):
                    csv_dict[os.path.basename(item)].append(fs_dst)
                series_tag = tag
            if series_tag:
                cnt[series_tag] += 1

        run_num = 1
        fmaps = sorted(glob.glob("{}*run-0{}*_FMAP-*".format(type_folders['fmap'],run_num)))
        while len(fmaps) > 1:
            for fmap in fmaps:
                validify_fmap(fmap)
            pattern = re.compile(r'_FMAP-\d\.5\.nii\.gz')
            without_tag = pattern.sub("", fmaps[0])
            base = os.path.basename(without_tag)

            cmd = ['bash', '/projects/mmanogaran/scripts/to_fmap.sh', fmaps[0], fmaps[1], without_tag, base]
            datman.utils.run(cmd)
            logger.warning("Running: {}".format(cmd))
            run_num+=1
            fmaps = sorted(glob.glob("{}*run-0{}*_FMAP-*".format(type_folders['fmap'],run_num)))

        for key in type_folders.keys():
            if os.listdir(type_folders[key]) == []:
                to_delete.add(type_folders[key])


    [ v.insert(0,k) for k,v in csv_dict.items()]
    for k, v in sorted(csv_dict.items()):
        ident, tag, series, description = scanid.parse_filename(k)
        site = ident.site
        sub = ident.get_full_subjectid_with_timepoint()
        logger.warning("Modifying JSON for: {}".format(k))
        modify_map_json(k, v[1], dmap_dict, fmap_dict, csv_dict, site)
        csvwriter.writerow(v)

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
