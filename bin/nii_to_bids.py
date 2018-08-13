#!/usr/bin/env python
"""
This copies and converts files in nii folder to a bids folder in BIDS format

Usage:
  nii_to_bids.py [options] <study> [<sub-id>...]

Arguments:
    <study>                     Study name defined in master configuration .yml file
                                to convert to BIDS format
    <sub-id>                    One or more names of subject directories in nii
                                directory to convert to bids

Options:
    --nii-dir PATH              Path to directory to copy nifti data from
    --bids-dir PATH             Path to directory to store data in BIDS format
    --fmriprep-out-dir PATH     Path to fmriprep output. Will copy subject
                                freesurfer data in fmriprep format. Will let fmriprep
                                skip this part of its process
    --freesurfer-dir PATH       Path to freesurfer data to copy into fmriprep-out-dir
    --rewrite                   Overwrite existing BIDS directories
    --log-to-server             If set, all log messages are sent to the configured
                                logging server.
    --debug                     Debug logging
"""
import datman.config as config
import datman.scanid as scanid
import datman.utils
import logging, logging.handlers
import os, sys
import json, csv
import re
import datetime, time
import traceback
import nibabel, numpy
import glob, fnmatch
from docopt import docopt
from shutil import copyfile, copytree
from distutils import dir_util
from queue import *
from collections import Counter

logger = logging.getLogger(__name__)
dmlogger = logging.getLogger('datman.utils')

tag_map = dict()
get_session_series = lambda x: (scanid.parse_filename(x)[0].session, scanid.parse_filename(x)[2])
get_series = lambda x: scanid.parse_filename(x)[2]
get_tag = lambda x: scanid.parse_filename(x)[1]

def validify_fmap(fmap):
    img = nibabel.load(fmap)
    hdr = img.header
    if (hdr['srow_z'][2] == 0):
        value = hdr['pixdim'][3]
        hdr['srow_z'][2] = value
        img.affine[2][2] = value
        nibabel.save(img, fmap)

def get_missing_data(data, nii_file):
    ident, _, _, _ = scanid.parse_filename(nii_file)
    try:
        img = nibabel.load(nii_file)
    except:
        logger.error("Could not open {}".format(nii_file))
        return
    if ('EffectiveEchoSpacing' not in data.keys()) and ident.site == 'CMH':
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
                acc = data['ParallelReductionFactorInPlane']
            data["TotalReadoutTime"] = str(float(data["EffectiveEchoSpacing"])*(npe/acc-1))
        except KeyError, key:
            logger.info(
            "Total readout time cannot be calculated due to missing information {} in JSON for: {}".format(key, nii_file))

def to_sub(ident):
    try:
        int(ident.subject[0])
        return "sub-" + ident.site + ident.subject
    except ValueError:
        if (ident.subject[0] == 'P'):
           return "sub-" + ident.site + ident.subject
        else:
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
        return os.path.join(type_folder["anat"], name.format(subject, session, acq,run_num, mod, ext))
    elif (tag in tag_map["fmri"]):
        name = "{}_{}_task-{}_{}_{}_bold{}"
        if (tag == "RST" or tag == "VN-SPRL"):
            run_num = to_run(cnt_run["RST"] + cnt_run["VN-SPRL"])
            task = "rest"
        else:
            task = tag.lower().replace('-','')
        return os.path.join(type_folder["func"] , name.format(subject, session, task, acq, run_num, ext))
    elif (tag in tag_map["dti"]):
        dtiacq = "{}{}".format(acq, tag.translate(None, "DTI-"))
        return os.path.join(type_folder["dwi"] , "{}_{}_{}_{}_dwi{}".format(subject, session, dtiacq, run_num, ext))
    elif "FMAP" in tag and ext != ".json" and ident.site == 'CMH':
        return os.path.join(type_folder["fmap"] , "{}_{}_{}_{}_{}{}".format(subject, session, acq, run_num, tag, ext))
    else:
        raise ValueError("File could not be changed to bids format:{} {} {}".format(str(ident), tag, ext))

def get_intended_fors(ses_ser_file_map, matched_fmaps):
    intended_fors = dict()
    for ses in sorted(ses_ser_file_map.keys()):
        ses_fmaps = sorted(matched_fmaps[ses])
        for ser in sorted(ses_ser_file_map[ses].keys()):
            series = int(ser)
            for i in range(0, len(ses_fmaps)):
                (six, eight) = ses_fmaps[i]
                matched = False
                if ser == six or ser == eight:
                    break
                if i == 0 and series < float(six):
                    matched = True
                elif i == len(ses_fmaps) - 1 and series > float(eight):
                    matched = True
                elif series != float(six) and series != float(eight):
                    nex = int(ses_fmaps[i+1][0]) if i != len(ses_fmaps) -1 else (sys.maxsize * -1) -1
                    prev = int(ses_fmaps[i-1][1]) if i != 0 else sys.maxsize
                    if (( series > float(six) - (float(six) - prev)/2) or (series <= float(eight) + (nex - float(eight))/2)):
                        matched = True
                if matched:

                    six_fmap = filter(lambda x: x.endswith('nii.gz'), ses_ser_file_map[ses][six])[0]
                    eight_fmap = filter(lambda x: x.endswith('nii.gz'), ses_ser_file_map[ses][eight])[0]
                    if six_fmap not in intended_fors and eight_fmap not in intended_fors:
                        intended_fors[six_fmap] = list()
                        intended_fors[eight_fmap] = list()
                    for nii in ses_ser_file_map[ses][ser]:
                        tag = scanid.parse_filename(nii)[1]
                        if (tag in tag_map['fmri'] or tag in tag_map['dti']) and nii.endswith('.nii.gz'):
                            intended_fors[six_fmap].append(nii)
                            intended_fors[eight_fmap].append(nii)
                    break
    return intended_fors

def validify_file(sub_nii_dir):
    nii_list = os.listdir(sub_nii_dir)
    # nii_list = [x for x in nii_list if x.endswith('nii.gz')]
    invalid_filenames = list()
    ses_ser_file_map = dict()
    for nii in nii_list:
        try:
            nii_ident, _, nii_ser, _ = scanid.parse_filename(nii)
        except:
            invalid_filenames.append(nii)
            continue
        nii_ses = nii_ident.session
        if nii_ses not in ses_ser_file_map.keys():
            ses_ser_file_map[nii_ses] = dict()
        ses_ser_file_map[nii_ses][nii_ser] = list()
    [nii_list.remove(x) for x in invalid_filenames]
    blacklist_files = set()
    match_six = {ses : LifoQueue() for ses in ses_ser_file_map.keys()}
    match_eight = {ses : LifoQueue() for ses in ses_ser_file_map.keys()}
    for filename in sorted(nii_list, key=lambda x: (scanid.parse_filename(x)[0].session, scanid.parse_filename(x)[2])):
        ident, tag, series, description = scanid.parse_filename(filename)
        ext = os.path.splitext(filename)[1]
        session = ident.session
        ses_ser_file_map[session][series].append(filename)
        ses_ser = (session, series)
        # fmap validation
        if tag == 'FMAP-6.5' and ext == '.gz':
            if 'flipangle' in filename:
                blacklist_files.add(ses_ser)
            else:
                match_six[session].put(series)
        elif tag == 'FMAP-8.5' and ext == '.gz':
            if 'flipangle' in filename:
                blacklist_files.add(ses_ser)
            else:
                match_eight[session].put(series)
        # anat validation
        if tag in tag_map['anat'] and ext == '.json_file':
            json_file = os.path.join(sub_nii_dir, filename)
            try:
                json_data = json.load(open(json_file))
            except IOError:
                continue
            if "NORM" in json_data["ImageType"]:
                logger.info("File has ImageType NORM. Skipping: {}".format(filename))
                blacklist_files.add(ses_ser)
    matched_fmaps = { ses : list() for ses in ses_ser_file_map.keys()}
    for ses in ses_ser_file_map.keys():
        while not (match_six[ses].empty() or match_eight[ses].empty()):
            six = match_six[ses].get()
            eight = match_eight[ses].get()
            matched_fmaps[ses].append((six, eight))
            logger.info("Matched FMAP series for session {0}: {1} {2}".format(ses, six, eight))
    for ses in ses_ser_file_map.keys():
        for match in [match_six, match_six]:
            while not match[ses].empty():
                not_matched = match[ses].get()
                blacklist_files.add((ses, not_matched))
                logger.info("FMAP series not matched: Session {}. Series {} ".format(ses, not_matched))
    for (ses, ser) in blacklist_files:
        ses_ser_file_map[ses].pop(ser)
    return ses_ser_file_map, matched_fmaps

def modify_json(nii_to_bids_match, intended_fors, sub_nii_dir):
    fmap_pattern = re.compile(r'FMAP-\d\.5')
    for nii, bids in nii_to_bids_match.items():
        intendeds = list()
        nii_file = os.path.join(sub_nii_dir, nii)
        if nii in intended_fors:
            bids = fmap_pattern.sub("fieldmap", bids)
            intendeds = intended_fors[nii]
        bids_json = bids.replace('nii.gz', 'json')

        try:
            json_file = open(bids_json, 'r+')
            data = json.load(json_file)
        except:
            try:
                json_file = open(bids_json, 'w')
                data = dict()
            except IOError:
                logger.error('Failed to open: {}'.format(bids_json), exc_info=True)
                continue

        if len(intendeds) > 0:
            data['Units'] = 'rad/s'
            data['IntendedFor'] = list()
            for nii in intendeds:
                bids_path = nii_to_bids_match[nii]
                split = bids_path.split('/')
                s = len(split)
                bids_name = os.path.join(split[s-3], split[s-2], split[s-1])
                data['IntendedFor'].append(bids_name)

        get_missing_data(data, nii_file)
        json_file.seek(0)
        json.dump(data, json_file, sort_keys=True, indent=4, separators=(',', ': '))
        json_file.truncate()
        json_file.close()

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
        create_json(os.path.join(file_path, task_names[task][1]), data)
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
    sub_dir = os.path.join(bids_dir,to_sub(ident)) + "/"
    create_dir(sub_dir)
    ses_dir = os.path.join(sub_dir,to_ses(ident.timepoint)) + "/"
    create_dir(ses_dir)
    for bid_type in ["anat", "func", "fmap", "dwi"]:
        type_dir[bid_type] = os.path.join(ses_dir,bid_type) + "/"
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

def create_command(subject, arguments):
    flags = ['python', '/scratch/mmanogaran/circleci_testing/datman/bin/nii_to_bids.py']
    for arg_flag in ['--nii-dir', '--bids-dir', '--fmriprep-out-dir', '--freesurfer-dir']:
        flags += [arg_flag, arguments[arg_flag]] if arguments[arg_flag] else []
    for flag in ['--rewrite', '--log-to-server', '--debug']:
        flags += [flag] if arguments[flag] else []
    flags += [arguments['<study>']]
    flags += [subject]
    return " ".join(flags)

def submit_nii_to_bids(log_dir, subject, arguments, cfg):
    with datman.utils.cd(log_dir):
        cmd = create_command(subject, arguments)
        logging.debug('Queueing command: {}'.format(cmd))
        job_name = 'nii_to_bids_{}_{}'.format(subject, time.strftime("%Y%m%d-%H%M%S"))
        datman.utils.submit_job(cmd, job_name, log_dir=log_dir, cpu_cores=1, dryrun=False)

def setup_logger(filepath, to_server, debug, config, sub_ids):

    logger.setLevel(logging.DEBUG)
    dmlogger.setLevel(logging.DEBUG)
    date = str(datetime.date.today())

    sub = '_{}'.format(sub_ids[0]) if len(sub_ids) == 1 else ''
    log_name = os.path.join(filepath, date + "-nii_to_bids{}.log".format(sub))
    fhandler = logging.FileHandler(log_name, "w")
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

def init_setup(study, cfg, bids_dir):

    bidsignore_path = os.path.join(bids_dir,".bidsignore")
    bidsignore = 'echo "*-nii_to_bids.log\nmatch.csv\nlogs/*" > {}'.format(bidsignore_path)
    os.system(bidsignore)

    data = dict()
    try:
        data["Name"] = cfg.get_key('FullName')
    except KeyError:
        data["Name"] = study
    data["BIDSVersion"] = "1.0.2"

    create_json(os.path.join(bids_dir, "dataset_description.json"), data )
    logger.info("Location of Dataset Description: {}".format(os.path.join(bids_dir + "dataset_description.json")))

    all_tags = cfg.get_tags()
    global tag_map
    tag_map = {all_tags.get(x, "qc_type") : [] for x in all_tags.keys()}
    for tag in all_tags.keys():
        tag_map[all_tags.get(tag, "qc_type")].append(tag)

    return all_tags.keys()

def main():
    arguments = docopt(__doc__)

    study  = arguments['<study>']
    sub_ids = arguments['<sub-id>']
    nii_dir = arguments['--nii-dir']
    bids_dir = arguments['--bids-dir']
    fmriprep_dir = arguments['--fmriprep-out-dir']
    fs_dir = arguments['--freesurfer-dir']
    rewrite = arguments['--rewrite']
    to_server = arguments['--log-to-server']
    debug  = arguments['--debug']

    cfg = config.config(study=study)
    logger.info("Study to convert to BIDS Format: {}".format(study))

    if not bids_dir:
        bids_dir =  os.path.join(cfg.get_path('data'),"bids/")
    create_dir(bids_dir)

    log_dir = os.path.join(bids_dir, 'logs')
    create_dir(log_dir)

    setup_logger(log_dir, to_server, debug, cfg, sub_ids)
    logger.info("BIDS folder will be {}".format(bids_dir))

    if not nii_dir:
        nii_dir = cfg.get_path('nii')
        logger.info("Nii files to be converted to BIDS format will be from: {}".format(nii_dir))

    if fmriprep_dir:
        fmriprep_fs_dir = os.path.join(fmriprep_dir, 'freesurfer')
        create_dir(fmriprep_fs_dir)
        logger.info('Fmriprep freesurfer dir will be:{}'.format(fmriprep_fs_dir))
    else:
        fmriprep_fs_dir = None

    if not fs_dir:
        fs_dir = cfg.get_path('freesurfer')
        logger.info('Freesurfer dir is: {}'.format(fs_dir))

    all_tags = init_setup(study,cfg, bids_dir)
    create_task_json(bids_dir, tag_map['fmri'])


    to_delete = set()

    try:
        sites = cfg.get_sites()
    except KeyError,err:
        logger.error(err)
        sys.exit(1)

    logger.info("Beginning to iterate through folders/files in {}".format(nii_dir))
    fmap_dict = dict()

    if not sub_ids:
        sub_ids = os.listdir(nii_dir)
    sub_ids = sorted(sub_ids)

    if len(sub_ids) > 1:
        for sub_id in sub_ids:
            logger.info('Submitting subject to queue: {}'.format(sub_id))
            submit_nii_to_bids(log_dir, sub_id, arguments, cfg)
    else:
        subject_dir = sub_ids[0]
        if scanid.is_phantom(subject_dir):
            logger.info("File is phantom and will be ignored: {}".format(subject_dir))
            sys.exit(1)

        parsed = scanid.parse(subject_dir)
        if os.path.isdir(os.path.join(bids_dir, to_sub(parsed), to_ses(parsed.timepoint)) and not rewrite:
            logger.warning('BIDS subject directory already exists. Exiting: {}'.format(subject_dir))
            sys.exit(1)
        type_folders = create_bids_dirs(bids_dir, parsed)
        sub_nii_dir = os.path.join(nii_dir,subject_dir) + '/'
        logger.info("Will now begin creating files in BIDS format for: {}".format(sub_nii_dir))
        ses_ser_file_map, matched_fmaps = validify_file(sub_nii_dir)
        intended_fors = get_intended_fors(ses_ser_file_map, matched_fmaps)
        nii_to_bids_match = dict()

        if fmriprep_dir:
            fs_src = os.path.join(fs_dir, subject_dir)
            sub_ses = "{}_{}".format(to_sub(parsed), to_ses(parsed.timepoint))
            fs_dst = os.path.join(fmriprep_fs_dir, sub_ses)
            if os.path.isdir(fs_src):
                dir_util.copy_tree(fs_src, fs_dst)
                logger.warning("Copied {} to {}".format(fs_src, fs_dst))

        cnt = {k : 0 for k in all_tags}
        for ses in sorted(ses_ser_file_map.keys()):
            logger.info('Session: {}'.format(ses))
            for ser in sorted(ses_ser_file_map[ses].keys()):
                logger.info('Series: {}'.format(ser))
                series_tags = set()
                for item in sorted(ses_ser_file_map[ses][ser]):
                    logger.info('File: {}'.format(item))
                    item_path = os.path.join(sub_nii_dir, item)
                    ident, tag, series, description =scanid.parse_filename(item)
                    ext = os.path.splitext(item)[1]
                    logger.info('to_bids_name')
                    try:
                        bids_path = to_bids_name(ident, tag, cnt, type_folders, ext)
                    except ValueError, err:
                        logger.info(err)
                        continue
                    logger.info('Copying file')
                    copyfile(item_path, bids_path)
                    logger.info('fslroi')
                    if bids_path.endswith('nii.gz') and "task" in os.path.basename(bids_path):
                        os.system('fslroi {0} {0} 4 -1'.format(bids_path))
                        logger.warning("Finished fslroi on {}".format(os.path.basename(bids_path)))
                    logger.info("{:<80} {:<80}".format(os.path.basename(item), os.path.basename(bids_path)))
                    if item_path.endswith('nii.gz'):
                        nii_to_bids_match[item] = bids_path
                    series_tags.add(tag)
                while len(series_tags) > 0:
                    cnt[series_tags.pop()] += 1

        run_num = 1
        fmaps = sorted(glob.glob("{}*run-0{}_FMAP-*".format(type_folders['fmap'],run_num)))
        while len(fmaps) > 1:
            for fmap in fmaps:
                validify_fmap(fmap)
            pattern = re.compile(r'_FMAP-\d\.5\.nii\.gz')
            without_tag = pattern.sub("", fmaps[0])
            base = os.path.basename(without_tag)

            cmd = ['bash', 'CMH_generate_fmap.sh', fmaps[0], fmaps[1], without_tag, base]
            datman.utils.run(cmd)
            logger.warning("Running: {}".format(cmd))
            run_num+=1
            fmaps = sorted(glob.glob("{}*run-0{}*_FMAP-*".format(type_folders['fmap'],run_num)))

        modify_json(nii_to_bids_match, intended_fors, sub_nii_dir)

        logger.info("Deleting unecessary BIDS folders")
        for key in type_folders.keys():
            folder = type_folders[key]
            if os.listdir(folder) == []:
                try:
                    logger.info("Deleting: {}".format(folder))
                    os.rmdir(folder)
                except Exception, e:
                    logger.info("Folder {} contains multiple acquistions. Should not be deleted.")

if __name__ == '__main__':
    main()
