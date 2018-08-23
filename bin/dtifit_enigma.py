#!/usr/bin/env python
'''
Will complete both dtifit and enigmaDTI pipelines unless otherwise specified.

There are two levels of tasks:
    Individual - Tasks that need to be completed for each subject individually.
    Group - Tasks that involve the subjects as a whole.
        Ex. Creating summary csv files and html pages

Will complete tasks for both levels unless otherwise specified.

Any given directories will overwrite datman study configuaration.
Datman folder structure will be ignored if nifti, dtifit, and enigma directories are given.

Usage:
    dtifit_enigma.py [options] [dtifit|enigma] <study>
    dtifit_enigma.py [options] [dtifit|enigma] <study> group
    dtifit_enigma.py [options] [dtifit|enigma] <study> individual [<subject_id>...]

Arguments:
    dtifit                              Will only complete dtifit pipeline tasks
    enigma                              Will only complete enigmaDTI pipeline tasks
    <study>                             Study to process
    group                               Will only complete group tasks such as summarizing csv files and creating html pages
    individual [<subject_id>...]        Will only complete individual subject tasks. If no subject ids are given, all will be run

Options:
    -n DIR, --nii-dir DIR               Input folder holding nii data within subject subfolders
    -d DIR, --dtifit-dir DIR            Output folder for dtifit data
    -e DIR, --enigma-dir DIR            Output folder for enigmaDTI data
    -l DIR, --log-dir DIR               Directory to send log files to
    --reg-vol N                         Registration volume index. For dtifit. [default: 0]
    --fa-thresh N                       FA threshold for bet. For dtifit. [default: 0.3]
    --output-nVox                       Change output value from "Average" to "nVoxels". For
                                        enigma
    --DPA-tag DPA                       Tags for diffusion maps
    --DAP-tag DAP                       Tags for diffusion maps
    --FMAP-65-tag FMAP-tag              Tag for fmap 6.5
    --FMAP-85-tag FMAP-tag              Tag for fmap 8.5
    --walltime TIME                     A walltime for the dtifit/engima/post-engima stage
                                        depending on which stages will be run [default: 4:00:00]

    --log-to-server                     Log to server
    --debug                             Debug logging mode
    --dry-run                           Dry-run

DETAILS:
    Requires FSL/5.0.10

TODO:
    - Implement --mb=3 mb_off=1 in eddy_openmp
        Available only in FSL/5.0.10
'''
import datman as dm
import datman.utils
import datman.config
import datman.scanid
import os, sys, pdb, errno
import datetime, time
import tempfile, shutil
import glob
import json
import nibabel as nib
import pandas as pd
import logging, logging.handlers
import subprocess
from docopt import docopt
from PIL import Image, ImageDraw, ImageFont, ImageOps

logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")

default_font = ''
base_tmp_dir = ''

class Command(object):

    def __init__(self, num_cpus=None):
        self.error_msg = None
        self.num_cpus = num_cpus

    def get_error(self):
        return self.error_msg

    def set_error(self, error):
        if not self.error_msg:
            self.error_msg = error

    def run(self, cmd):
        if self.error_msg:
            return
        if isinstance(cmd, list):
            cmd = " ".join(cmd)

        merged_env = os.environ
        merged_env.pop('DEBUG', None)

        if self.num_cpus:
            merged_env.update({'OMP_NUM_THREADS': str(self.num_cpus)})

        logging.debug('Command:{}\n'.format(cmd))
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=merged_env)
        out, err = p.communicate()
        if not (cmd == out or out == ''):
            logging.debug('Output:{}\n'.format(out))
        if p.returncode:
            logging.error('run({}) failed with returncode {}. SDTERR: {}'.format(cmd, p.returncode, err))
            self.error_msg = err

def clean_and_exit(exit_int):
    shutil.rmtree(base_tmp_dir)
    sys.exit(exit_int)

def create_qc_page(page_title, html_path, sub_ids, gif_structure):
    logging.debug('Creating QC page for {} at {} with {} subjects'.format(page_title, html_path, len(sub_ids)))
    with open(html_path, 'w') as qc_page:
        qc_page.write('<!DOCTYPE html>\n')
        qc_page.write('<HTML>\n')
        qc_page.write('<TITLE>{0}</TITLE>\n'.format(page_title))
        qc_page.write('<BODY BGCOLOR=#333333>\n')
        qc_page.write('<h1><font color="white">{0}</font></h1>\n'.format(page_title))
        qc_page.write("<dl id='gif_list'>\n")
        for sub in sorted(sub_ids):
            sub_id = os.path.basename(sub)
            sub_id = sub_id[0:sub_id.index('.')]
            gif = gif_structure.format(sub_id)
            qc_page.write('\t<dt style="color:#99CCFF">{0}</dt>\n'.format(gif))
            qc_page.write('\t<dd>\n\t\t<a href="{0}">\n\t\t\t<img src="{0}">\n\t\t</a>\n\t</dd>\n'.format(gif))
        qc_page.write('</dl>\n')
        qc_page.write('</BODY>\n')
        qc_page.write('</HTML>')
    logging.debug('Done create {}'.format(page_title))

def create_error_gif(error_msg, output_gifs):
    logging.debug('Creating error gif for message: {}'.format(error_msg))
    logging.debug('Output Gifs: {}'.format(str(output_gifs)))
    basic_gif = Image.new('RGBA', (1800, 600), (0, 0, 0, 0))
    logging.debug('PILLOW may have trouble finding font for ImageFont.')
    font = ImageFont.truetype(font=default_font, size=30)
    draw = ImageDraw.Draw(basic_gif)
    (width, height) = draw.textsize(error_msg, font)
    error_gif = basic_gif.resize((1800, height + 10))
    draw = ImageDraw.Draw(error_gif)
    draw.text((5, 5), error_msg, font=font, fill=(255, 255, 255, 255))
    for gif in output_gifs:
        error_gif.save(gif)
        logging.debug('Saved error_gif for {} at {}'.format(error_msg, gif))

def gif_gridtoline(input_gif, output_gif, tmp_dir, tmp_base,  size, cmd):
    sag = os.path.join(tmp_dir, tmp_base + '_sag.gif')
    cor = os.path.join(tmp_dir, tmp_base + '_cor.gif')
    ax = os.path.join(tmp_dir, tmp_base + '_ax.gif')
    try:
        im = Image.open(input_gif)
        # dm.utils.run(['convert',input_gif, '-resize', '{0}x{0}'.format(size),input_gif])
        im = im.convert('RGBA').resize((size, size), resample=Image.BICUBIC)
        im.save(input_gif)
        # dm.utils.run(['convert', input_gif, '-crop', '100x33%+0+0', sag])
        im.crop((0,0,size,size//3)).save(sag)
        # dm.utils.run(['convert', input_gif, '-crop', '100x33%+0+{}'.format(size//3), cor])
        im.crop((0,size//3, size, size*2//3)).save(cor)
        # dm.utils.run(['convert', input_gif, '-crop', '100x33%+0+{}'.format(size*2//3), ax])
        im.crop((0,size*2//3, size, size)).save(ax)
        # dm.utils.run(['montage', '-mode', 'concatenate', '-tile', '3x1', sag, cor, ax, output_gif])
        concat = Image.new('RGBA', (size*3, size//3))
        x_offset = 0
        for im_name in (sag, cor, ax):
            concat.paste(Image.open(im_name), (x_offset, 0))
            x_offset += size
        concat.save(output_gif)
    except Exception as exp:
        logging.error('Error creating QC image: {}'.format(exp))
        cmd.set_error(exp)

def mask_overlay(background_nii, mask_nii, output_gif, tmp_dir, tmp_base, size, cmd):
    B0_masked = os.path.join(tmp_dir, tmp_base + 'B0masked.gif')
    cmd.run(['slices', background_nii, mask_nii, '-o', B0_masked])
    if not cmd.get_error():
        gif_gridtoline(B0_masked, output_gif, tmp_dir, tmp_base, size, cmd)

def V1_overlay(background_nii, V1_nii, output_gif, tmp_dir, tmp_base, size, cmd):
    background = os.path.join(tmp_dir, tmp_base + 'background.gif')
    FA_mask = os.path.join(tmp_dir, tmp_base + 'FAmask.nii.gz')
    V1 = os.path.join(tmp_dir, tmp_base + 'V1{}')
    dirmap = os.path.join(tmp_dir, tmp_base + 'dirmap.gif')
    cmd.run(['slices', background_nii, '-o', background])
    cmd.run(['fslmaths', background_nii, '-thr', '0.15', '-bin', FA_mask])
    cmd.run(['fslsplit', V1_nii, V1.format('')])
    for axis in ['0000', '0001', '0002']:
        cmd.run('fslmaths {0}.nii.gz -abs -mul {1} {0}abs.nii.gz'.format(V1.format(axis), FA_mask))
        cmd.run('slices {0}abs.nii.gz -o {0}abs.gif'.format(V1.format(axis)))
    # dm.utils.run('convert {0}0000abs.gif {0}0001abs.gif {0}0002abs.gif -set colorspace RGB -combine -set colorspace sRGB {1}'.format(V1.format(''), dirmap))
    try:
        im0 = Image.open(V1.format('0000abs.gif'))
        im1 = Image.open(V1.format('0001abs.gif'))
        im2 = Image.open(V1.format('0002abs.gif'))
        Image.merge('RGB', (im0.convert('L'), im1.convert('L'), im2.convert('L'))).save(dirmap)
    except Exception as exp:
        logging.error('Error creating V1 grid gif: {}'.format(exp))
        cmd.set_error(exp)

    if not cmd.get_error():
        gif_gridtoline(dirmap, output_gif, tmp_dir, tmp_base, size, cmd)

def skel_overlay(background_nii, skel_nii, output_gif, tmp_dir, tmp_base, size, cmd):
    to_target = os.path.join(tmp_dir, tmp_base + 'to_target.gif')
    skel = os.path.join(tmp_dir, tmp_base + 'skel.gif')
    skel_mag = os.path.join(tmp_dir, tmp_base + 'skel_mag.gif')
    cskel = os.path.join(tmp_dir, tmp_base + 'cskel.gif')
    cmd.run(['slices', background_nii, '-o', to_target])
    cmd.run(['slices', skel_nii, '-o', skel])
    # dm.utils.run(['convert', '-fuzz', '10%', '-fill', 'magenta', '-negate', skel, '-transparent', 'white', '-colorize', '100,0,100', skel_mag])
    try:
        to = Image.open(to_target).convert('RGBA')
        sk = Image.open(skel)
        mag = ImageOps.colorize(sk.convert('L'), (255,255,255),(255,0,255)).convert('RGBA')
        mag_data = mag.getdata()
        transparent_data = []
        for item in mag_data:
            if item[0] == 255 and item[1] == 255 and item[2] == 255:
                transparent_data.append((255, 255, 255, 0))
            else:
                transparent_data.append(item)
        mag.putdata(transparent_data)
        mag.save(skel_mag)
        # dm.utils.run(['composite', skel_mag, to_target, cskel])
        Image.alpha_composite(to, mag).save(cskel)
    except Exception as exp:
        logging.error('Error creating skeleton grid gif: {}'.format(exp))
        cmd.set_error(exp)
        return

    if not cmd.get_error():
        gif_gridtoline(cskel, output_gif, tmp_dir, tmp_base, size, cmd)

#change int behaviour to python 3 compatible
def get_rounded_dims(nii_to_round):
    nii_header = nib.load(nii_to_round).header
    get_dim = lambda x: int(nii_header['dim'][x])
    rounded_dims = [get_dim(i) if (get_dim(i) % 2 == 0) else (get_dim(i) - 1) for i in range(1, 5)]
    return rounded_dims

def create_index_file(dti, index_path):
    dti_dim = nib.load(dti).header
    indx = '1'
    for i in range(1, dti_dim['dim'][4]):
        indx = indx + " 1"

    logging.debug('Number of values in {}: {}'.format(dti, dti_dim['dim'][4]))
    with open(index_path, 'w') as indx_file:
        indx_file.write(indx)
    return dti_dim['dim'][4]

def match_rep_time(time, nii_list):
    matched = None
    for nii in nii_list:
        with open(nii.replace('nii.gz', 'json'), 'r') as nii_json:
            nii_data = json.load(nii_json)
            if time == nii_data['RepetitionTime']:
                matched = nii
                logging.debug('Got match.')
                break
    return matched

def get_series(path, session_to_match):
    ident, tag, series, description = dm.scanid.parse_filename(path)
    if ident.session == session_to_match:
        return int(series)
    else:
        return sys.maxsize

def get_qced_dtis(nii_dir, sub_ids, qced_subjects):
    checked_subs = dict()
    for sub in sub_ids:
        try:
            dm.scanid.parse(sub)
        except dm.scanid.ParseException:
            logging.info('{} is not subject. Skipping.'.format(sub))
            continue

        if dm.scanid.is_phantom(sub):
            logging.info('Subject is phantom. Skipping: {}'.format(sub))
            continue

        # try:
        #     blacklisted_series = qced_subjects[sub]
        # except KeyError:
        #     logging.info('Subject has not been QCed. Skipping: {}'.format(sub))
        #     continue

        checked_subs[sub] = list()

        dti_files = dm.utils.get_files_with_tag(os.path.join(nii_dir, sub), 'DTI', fuzzy=True)
        dti_files = sorted(filter(lambda x: x.endswith('.nii.gz'), dti_files))
        for dti in dti_files:
            series = dm.scanid.parse_filename(dti)[2]
            # try:
            #     blacklisted_series.index(series)
            #     logging.info("DTI series number in blacklist. Skipping: {}".format(os.path.basename(dti)))
            #     continue
            # except ValueError:
            #     checked_subs[sub].append(dti)
            checked_subs[sub].append(dti)
    return checked_subs

def create_command(subject, arguments):
    flags = ['dtifit_enigma.py']
    if arguments['dtifit']:
        flags += ['dtifit']
    elif arguments['enigma']:
        flags += ['enigma']
    for arg_flag in ['--nii-dir', '--dtifit-dir', '--enigma-dir',
                     '--DAP-tag', '--DPA-tag', '--FMAP-65-tag', '--FMAP-85-tag',
                     '--fa-thresh', '--reg-vol', '--log-dir', '--walltime']:
        flags += [arg_flag, arguments[arg_flag]] if arguments[arg_flag] else []
    for flag in ['--debug', '--dry-run', '--log-to-server', '--output-nVox']:
        flags += [flag] if arguments[flag] else []

    flags += [arguments['<study>']]
    flags += ['individual', subject]
    return " ".join(flags)

def submit_proc_dti(log_dir, subject, arguments):
    with dm.utils.cd(log_dir):
        cmd = create_command(subject, arguments)
        # logging.debug('Queueing command: {}'.format(cmd))
        job_name = '{}_dm_proc_dti_{}'.format(subject, time.strftime("%Y%m%d-%H%M%S"))
        dm.utils.submit_job(cmd, job_name, log_dir=log_dir,
                                cpu_cores=1, walltime=arguments['--walltime'],
                                dryrun=False)

def check_dirs(dtifit, enigma, study, nii_dir, fit_dir, enig_dir, cfg):
    both_pipe = True if not (dtifit or enigma) else False
    # Check nii_dir
    if not nii_dir:
        nii_dir = cfg.get_path('nii')

    if dtifit or both_pipe:
        if not os.path.isdir(nii_dir):
            logging.critical('NII dir does not exist: {}. Exiting.'.format(nii_dir))
            clean_and_exit(1)
        if os.listdir(nii_dir) == []:
            logging.critical("NII dir is empty: {}. Exiting.".format(nii_dir))
            clean_and_exit(1)
        logging.info('NII dir will be: {}'.format(nii_dir))

    #Check dtifit dir depending on pipeline
    if not fit_dir:
        fit_dir = cfg.get_path('dtifit')

    if enigma:
        if not os.path.isdir(fit_dir):
            logging.critical('DTIFIT dir does not exist: {}. Exiting.'.format(fit_dir))
            clean_and_exit(1)
        if os.listdir(fit_dir) == []:
            logging.critical("DTIFIT dir is empty: {}. Exiting.".format(fit_dir))
            clean_and_exit(1)
    elif dtifit or both_pipe:
        create_dir(fit_dir)
    logging.info('DTIFIT dir will be: {}'.format(fit_dir))

    #Check enigmaDTI dir
    if enigma or both_pipe:
        if not enig_dir:
            enig_dir = cfg.get_path('enigmaDTI')
        create_dir(enig_dir)
        logging.info('ENIGMA dir will be: {}'.format(enig_dir))

    return nii_dir, fit_dir, enig_dir

def setup_log_to_server(cfg):
    server_ip = cfg.get_key('LOGSERVER')
    server_handler = logging.handlers.SocketHandler(server_ip,
            logging.handlers.DEFAULT_TCP_LOGGING_PORT)
    server_handler.setLevel(logging.CRITICAL)
    logging.getLogger('').addHandler(server_handler)

def add_file_handler(dir_path, log_name):
    date = str(datetime.date.today())
    log_path = os.path.join(dir_path, "{}-{}.log".format(date, log_name))
    fhandler = logging.FileHandler(log_path, "w")
    fhandler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("[%(name)s] %(levelname)s: %(message)s")
    fhandler.setFormatter(formatter)
    logging.getLogger('').addHandler(fhandler)
    return fhandler

def create_dir(dir_path):
    if not os.path.isdir(dir_path):
        logging.info('Creating: {}'.format(dir_path))
        try:
            os.mkdir(dir_path)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                logging.debug('Dir already exists:\t{}. Mostly likely a no-locking problem. Continuing.'.format(dir_path))
            else:
                logging.critical('Failed creating:\t{}. Exiting.'.format(dir_path), exc_info=True)
                clean_and_exit(1)
    else:
        logging.info('Dir already exists:\t{}. Continuing.'.format(dir_path))

def main():
    arguments = docopt(__doc__)
    dtifit = arguments['dtifit']
    enigma = arguments['enigma']
    study = arguments['<study>']
    group = arguments['group']
    indiv = arguments['individual']
    sub_ids = arguments ['<subject_id>']
    nii_dir = arguments['--nii-dir']
    fit_dir = arguments['--dtifit-dir']
    enig_dir = arguments['--enigma-dir']
    reg_vol = arguments['--reg-vol']
    fa_thresh = arguments['--fa-thresh']
    output_nVox = arguments['--output-nVox']
    dap_tag = arguments['--DAP-tag']
    dpa_tag = arguments['--DPA-tag']
    fmap_65_tag = arguments['--FMAP-65-tag']
    fmap_85_tag = arguments['--FMAP-85-tag']
    walltime = arguments['--walltime']
    log_to_server = arguments['--log-to-server']
    log_dir = arguments['--log-dir']
    debug = arguments['--debug']
    dry_run = arguments['--dry-run']

    is_dtifit = lambda : dtifit or not (dtifit or enigma)
    is_enigma = lambda : enigma or not (dtifit or enigma)
    is_indiv = lambda : indiv or not (indiv or group)
    is_group = lambda : group or not (indiv or group)

    if debug:
        logging.getLogger('').setLevel(logging.DEBUG)

    # Get log dir / log file name
    if log_dir:
        create_dir(log_dir)
        log_name = '{}DTI{}{}'
        en = 'enigma' if is_enigma() else ''
        fit = 'fit' if is_dtifit() else ''
        if group:
            log_id = '_group'
        elif len(sub_ids) == 1:
            log_id = '_' + sub_ids[0]
        else:
            log_id = ''
        add_file_handler(log_dir, log_name.format(en, fit, log_id))


    global base_tmp_dir
    suf = sub_ids[0] if len(sub_ids) == 1 else ''
    base_tmp_dir = tempfile.mkdtemp(suffix=suf, dir=log_dir)

    # Get DATMAN study config
    try:
        cfg = dm.config.config(study=study)
    except Exception as exc:
        logging.critical('Data in not in datman format. Exiting', exc_info=True)
        clean_and_exit(1)

    if (log_to_server):
        setup_log_to_server(cfg)
    logging.debug(arguments)

    global default_font
    default_font = os.path.join(cfg.system_config['DATMAN_ASSETSDIR'], 'fonts', 'Roboto-Regular.ttf')

    logging.debug('Getting all necessary environment variables.')
    fsldir = os.getenv('FSLDIR')
    if not fsldir:
        logging.critical('FSLDIR environment variable is undefined. Exiting.')
        clean_and_exit(1)

    if is_enigma():
        enigmahome = os.getenv('ENIGMAHOME')
        if not enigmahome:
            logging.critical('ENIGMAHOME environment variable is undefined. Exiting.')
            clean_and_exit(1)

    logging.debug('Getting/ creating all necessary major directories.')
    nii_dir, fit_dir, enig_dir = check_dirs(dtifit, enigma, study, nii_dir, fit_dir, enig_dir, cfg)


    if len(sub_ids) == 0:
        logging.debug('Getting all subject ids.')
        if is_dtifit():
            sub_ids = dm.utils.get_subjects(nii_dir)
        else:
            sub_ids = dm.utils.get_subjects(fit_dir)

    qced_subjects = cfg.get_subject_metadata()
    checked_subs = get_qced_dtis(nii_dir, sub_ids, qced_subjects)

    if is_dtifit():
        fit_tmp_dir = os.path.join(base_tmp_dir, 'fit')
        create_dir(fit_tmp_dir)
        logging.debug('Getting all valid subjects for dtifit')
        is_qced_sub = list()
        for sub in sub_ids:
            if sub in checked_subs:
                is_qced_sub.append(sub)
            else:
                logging.error('Subject is phantom or has not been QCed. Will not be run through pipeline. {}'.format(sub))
        sub_ids = is_qced_sub
        if len(sub_ids) == 0:
            logging.error('No subjects left to run through pipeline. Exiting.')
            clean_and_exit(1)

        logging.debug('Creating DTIFIT QC directories.')
        fit_qc_dir = os.path.join(fit_dir, 'QC')
        create_dir(fit_qc_dir)
        for qc_type in ['BET', 'directions', 'fieldmaps']:
            qc_type_dir = os.path.join(fit_qc_dir, qc_type)
            create_dir(qc_type_dir)
        bet_gif_form = os.path.join('BET', '{}_b0_bet_mask.gif')
        dir_gif_form = os.path.join('directions', '{}_eddy_dtifit_V1.gif')
        fm_gif_form  = os.path.join('fieldmaps', '{}_fieldmap_diff.gif')

    if is_enigma():
        enig_tmp_dir = os.path.join(base_tmp_dir, 'enig')
        create_dir(enig_tmp_dir)
        logging.debug('Creating ENIGMA QC directories.')
        enig_qc_dir = os.path.join(enig_dir, 'QC')
        create_dir(enig_qc_dir)
        for skel_type in [ 'FA', 'AD', 'MD', 'RD']:
            skel_dir = os.path.join(enig_qc_dir, '{}skel'.format(skel_type))
            create_dir(skel_dir)
        skel_gif_form = os.path.join('{type}skel', '{base}_eddy_dtifit_{type}skel.gif')

    # if only one subject, no need to do anything
    if is_indiv() and len(sub_ids) > 1:
        if log_dir:
            q_log_dir = log_dir
        else:
            q_log_dir = fit_dir
        logging.debug('.qcbatch logs will go to: {}'.format(q_log_dir))

        logging.debug('Putting each subject on queue for individual mode.')
        for sub in sub_ids:
            try:
                dm.scanid.parse(sub)
            except dm.scanid.ParseException:
                logging.info('{} is not subject. Skipping.'.format(sub))
                continue
            # logging.info('Submitting subject to queue: {}'.format(sub))
            submit_proc_dti(q_log_dir, sub, arguments)

        if not is_group():
            logging.info('Every subject is now on the queue. Exiting.')
            ###tmp_Fir cleanup
            clean_and_exit(0)
        # if indiv mode and group mode needed, turn off indiv and
        # continue in just group mode
        else:
            logging.debug('Continuing in just group mode.')
            indiv = False
            group = True

    if len(sub_ids) == 1:
        sub = sub_ids[0]

    dti_errors = { dti: '' for dti in checked_subs[sub]}
    if is_dtifit():
        logging.debug('Entering DTIFIT mode.')
        if is_group():
            logging.debug('Entering DTIFIT group mode.')
            logging.debug('Getting all QCed DTIs.')
            all_dti_files = list()
            for dti_list in checked_subs.values():
                all_dti_files += dti_list
            all_dti_files = sorted(all_dti_files)
            logging.debug('Creating all DTIFIT QC pages.')
            bet_html = os.path.join(fit_qc_dir, 'BET.html')
            create_qc_page('DTIFIT BET QC PAGE', bet_html, all_dti_files, bet_gif_form)
            dir_html = os.path.join(fit_qc_dir, 'directions.html')
            create_qc_page('DTIFIT directions QC PAGE', dir_html, all_dti_files, dir_gif_form)
            if fmap_65_tag and fmap_85_tag:
                fm_html = os.path.join(fit_qc_dir, 'fieldmaps.html')
                create_qc_page('FIELDMAPS QC PAGE', fm_html, all_dti_files, fm_gif_form)

        if is_indiv():
            logging.debug('Entering DTIFIT individual mode.')
            fit_sub_dir = os.path.join(fit_dir, sub)
            create_dir(fit_sub_dir)
            sub_tmp_dir = os.path.join(fit_tmp_dir, sub)
            create_dir(sub_tmp_dir)

            nii_sub_dir = os.path.join(nii_dir, sub)
            for dti in checked_subs[sub]:
                logging.debug('Starting to process: {}'.format(dti))
                fit_cmd = Command(5)
                if not os.path.isdir(nii_sub_dir):
                    fit_cmd.set_error('Nii subject dir does not exist. Skipping. {}'.format(sub))
                    create_error_gif(fit_cmd.get_error(), gifs)
                    logging.error(fit_cmd.get_error())
                    dti_errors[dti] = fit_cmd.get_error()
                    continue

                ident, tag, series, description = dm.scanid.parse_filename(dti)
                dti_name = dm.scanid.make_filename(ident, tag, str(series), description)
                dtifit_basename = os.path.join(fit_sub_dir, dti_name)
                fit_file = '{}_eddy_dtifit_{{}}.nii.gz'.format(dtifit_basename)
                sub_bet_gif = os.path.join(fit_qc_dir, bet_gif_form.format(dti_name))
                sub_dir_gif = os.path.join(fit_qc_dir, dir_gif_form.format(dti_name))
                gifs = [sub_bet_gif, sub_dir_gif]
                if fmap_65_tag and fmap_85_tag:
                    sub_fm_gif = os.path.join(fit_qc_dir, fm_gif_form.format(dti_name))
                    gifs.append(sub_fm_gif)

                dti_tmp_dir = os.path.join(sub_tmp_dir, series)
                create_dir(dti_tmp_dir)
                os.chdir(dti_tmp_dir)

                dti_unix = '{}*'.format(dti.split('.')[0])
                logging.debug('Going through all related files for dti and copying file to tmp directory.')
                for related_file in glob.glob(dti_unix):
                    if os.path.islink(related_file):
                        linkedto = os.path.realpath(related_file)
                        shutil.copyfile(linkedto, os.path.basename(related_file))
                    else:
                        shutil.copyfile(related_file, os.path.basename(related_file))
                dti = os.path.basename(dti)
                bvec = dti.replace('nii.gz', 'bvec')
                bval = dti.replace('nii.gz', 'bval')

                b0_name = os.path.join(fit_sub_dir, '{}_b0'.format(dti_name))
                bet_name = os.path.join(fit_sub_dir, '{}_b0_bet'.format(dti_name))
                mask_name = os.path.join(fit_sub_dir, '{}_b0_bet_mask'.format(dti_name))
                acqp_path = os.path.join(fit_sub_dir, 'acqparams.txt')
                index_path = os.path.join(fit_sub_dir, 'index.txt')
                num_vols = create_index_file(dti, index_path)

                logging.debug('Checking bvec file for proper format.')
                with open(bvec, 'r') as bvec_file:
                    bvec_lines = bvec_file.readlines()
                    num_rows = len(bvec_lines)
                    for line in bvec_lines:
                        num_cols = len(line.split())
                    if not (num_rows == 3 and num_cols == num_vols) or (num_rows == num_vols and num_cols == 3):
                        fit_cmd.set_error('bvecs should contain a 3xN or Nx3 matrix where N is the number of volumes in {}'.format(dti_name))
                        create_error_gif(fit_cmd.get_error(), gifs)
                        logging.error(fit_cmd.get_error())
                        dti_errors[dti] = fit_cmd.get_error()
                        continue

                series = int(series)
                session = ident.session
                config = os.path.join(os.getenv('FSLDIR'), 'etc/flirtsch/b02b0.cnf') #BEGINNINED

                if dpa_tag or dap_tag:
                    logging.debug('Getting all {} that match session {}.'.format(dpa_tag, session))
                    pas = glob.glob(os.path.join(nii_sub_dir, '*{}*.nii.gz'.format(dpa_tag)))
                    pas = sorted(filter(lambda x: get_series(x, session) < series, pas), reverse=True)

                if dpa_tag and not(dap_tag):
                    logging.debug('Completing DTIFIT with only DPAs.')
                    with open(dti.replace('nii.gz', 'json'), 'r') as dti_json:
                        dti_data = json.load(dti_json)
                        dti_rep_time = dti_data['RepetitionTime']
                    logging.debug('{} RepetitionTime is {}'.format(dti, dti_rep_time))
                    dpa = match_rep_time(dti_rep_time, pas)

                    if dpa:
                        logging.debug('{} matches with {}'.format(os.path.basename(dpa), os.path.basename(dti)))
                    else:
                        fit_cmd.set_error("DPA repetition times does not match with {}. Skipping.\n".format(os.path.basename(dti)))
                        create_error_gif(fit_cmd.get_error(), gifs)
                        logging.error(fit_cmd.get_error())
                        dti_errors[dti] = fit_cmd.get_error()
                        continue

                    with open(bval, 'r') as bval_file:
                        bvals = bval_file.readline()
                    bvals = [ float(i) for i in bvals.split()]
                    b0s = [ i for i in range(0, len(bvals)) if bvals[i] == 0]
                    for val in b0s:
                        fit_cmd.run('fslroi {0} tmp_{1}.nii.gz {1} 1'.format(dti, val))
                    fit_cmd.run('fslmerge -t merged_dti_b0.nii.gz tmp_*.nii.gz')
                    fit_cmd.run('fslmerge -t merged_b0.nii.gz merged_dti_b0.nii.gz {}'.format(dpa))
                    acqparams = '0 1 0 0.096\n'
                    for i in range(1, int(nib.load('merged_dti_b0.nii.gz').header['dim'][4])):
                        acqparams += '0 1 0 0.096\n'
                    for i in range(0, int(nib.load(dpa).header['dim'][4])):
                        acqparams += '0 -1 0 0.096\n'
                    with open(acqp_path, 'w') as acq_file:
                        acq_file.write(acqparams)

                    rounded_b0_dims = get_rounded_dims('merged_b0.nii.gz')
                    fit_cmd.run('fslroi merged_b0.nii.gz merged_b0.nii.gz 0 {d[0]} 0 {d[1]} 1 {d[2]} 0 {d[3]}'.format(d=rounded_b0_dims))
                    fit_cmd.run('topup --imain=merged_b0.nii.gz --datain={} --config={} --out=topup_b0 --iout={} -v'.format(acqp_path, config, b0_name))
                    fit_cmd.run('fslmaths {0}.nii.gz -Tmean {0}'.format(b0_name))
                    ## 0.5
                    fit_cmd.run('bet {} {} -m -f {}'.format(b0_name, bet_name, fa_thresh))
                    rounded_dti_dims = get_rounded_dims(dti)
                    fit_cmd.run('fslroi {0} {0} 0 {d[0]} 0 {d[1]} 0 {d[2]} 0 {1}'.format(dti, num_vols, d=rounded_dti_dims))
                    fit_cmd.run('eddy_openmp --imain={} --mask={}.nii.gz --acqp={} --index={} --bvecs={} --bvals={} --topup=topup_b0 --repol --out=eddy_openmp --data_is_shelled --verbose'.format(dti, mask_name, acqp_path, index_path, bvec, bval))
                    for to_copy in ('eddy_openmp.eddy_rotated_bvecs', 'eddy_openmp.nii.gz'):
                        shutil.copyfile(to_copy, os.path.join(fit_sub_dir, '{}_{}'.format(dti_name, to_copy)))
                    fit_cmd.run('dtifit --data=eddy_openmp.nii.gz --mask={} --bvecs=eddy_openmp.eddy_rotated_bvecs --bvals={} --save_tensor --out={}_eddy_dtifit'.format(mask_name, bval, dtifit_basename))
                elif dpa_tag and dap_tag:
                    aps = glob.glob(os.path.join(nii_sub_dir, '*{}*.nii.gz'.format(dap_tag)))
                    dap = min(aps, key=lambda x: abs(get_series(x, session) - series) if get_series(x, session) < series else sys.maxsize)
                    with open(dap.replace('nii.gz', 'json'), 'r') as dap_json:
                        dap_data = json.load(dap_json)
                        dap_rep_time = dap_data['RepetitionTime']
                    logging.debug('{} RepetitionTime is {}'.format(dap, dap_rep_time))
                    dpa = match_rep_time(dap_rep_time, pas)

                    if dpa:
                        logging.debug('{} matches with DAP {}'.format(os.path.basename(dpa), os.path.basename(dap)))
                    else:
                        fit_cmd.set_error("DPA repetition times does not match with {}. Skipping.".format(os.path.basename(dap)))
                        create_error_gif(fit_cmd.get_error(), gifs)
                        logging.error(fit_cmd.get_error())
                        dti_errors[dti] = fit_cmd.get_error()
                        continue

                    fit_cmd.run('fslroi {} DAP_b0 0 1'.format(dap))
                    fit_cmd.run('fslroi {} DPA_b0 0 1'.format(dpa))
                    fit_cmd.run('fslmerge -t merged_b0 DAP_b0 DPA_b0')
                    fit_cmd.run('printf "0 -1 0 0.05\n0 1 0 0.05" > {}'.format(acqp_path))
                    rounded_b0_dims = get_rounded_dims('merged_b0.nii.gz')
                    fit_cmd.run('fslroi {0} {0} 0 {d[0]} 0 {d[1]} 0 {d[2]} 0 {d[3]}'.format('merged_b0.nii.gz', d=rounded_b0_dims))
                    fit_cmd.run('topup --imain=merged_b0 --datain={} --config={} --out=topup_b0 --iout={} -v'.format(acqp_path, config, b0_name))
                    fit_cmd.run('fslmaths {0} -Tmean {0}'.format(b0_name))
                    #fa_thesh ??? 0.5
                    fit_cmd.run('bet {} {} -m -f {}'.format(b0_name, bet_name, fa_thresh))
                    rounded_dti_dims = get_rounded_dims(dti)
                    fit_cmd.run('fslroi {0} {0} 0 {d[0]} 0 {d[1]} 0 {d[2]} 0 {1}'.format(dti, num_vols, d=rounded_dti_dims))
                    fit_cmd.run('eddy_openmp --imain={} --mask={} --acqp={} --index={} --bvecs={} --bvals={} --topup=topup_b0 --repol --out=eddy_openmp --data_is_shelled --verbose'.format(dti, mask_name, acqp_path, index_path, bvec, bval))
                    for to_copy in ('eddy_openmp.eddy_rotated_bvecs', 'eddy_openmp.nii.gz'):
                        shutil.copyfile(to_copy, os.path.join(fit_sub_dir, '{}_{}'.format(dti_name, to_copy)))
                    fit_cmd.run('dtifit --data=eddy_openmp.nii.gz --mask={} --bvecs=eddy_openmp.eddy_rotated_bvecs --bvals={} --save_tensor --out={}_eddy_dtifit'.format(mask_name, bval, dtifit_basename))
                elif fmap_65_tag and fmap_85_tag and ident.site == 'CMH':
                    ### from Natalie who got it from downstairs
                    sixes = glob.glob(os.path.join(nii_sub_dir, '*{}*.nii.gz'.format(fmap_65_tag)))
                    eights = glob.glob(os.path.join(nii_sub_dir, '*{}*.nii.gz'.format(fmap_85_tag)))
                    if len(sixes) == 0 or len(eights) == 0:
                        fit_cmd.set_error("No fmaps found for {}. Skipping".format(dti_name))
                        create_error_gif(fit_cmd.get_error(), gifs)
                        logging.error(fit_cmd.get_error())
                        dti_errors[dti] = fit_cmd.get_error()
                        continue
                    six = min(sixes, key=lambda x: abs(get_series(x, session) - series) if get_series(x, session) < series else sys.maxsize)
                    eight = min(eights, key=lambda x: abs(get_series(x, session) - series) if get_series(x, session) < series else sys.maxsize)

                    fit_cmd.run('fslroi {} {} 0 1'.format(dti, b0_name))
                    ##fa-thresh 0/.5
                    fit_cmd.run('bet {} {} -m -f {}'.format(b0_name, bet_name, fa_thresh))

                    for f, num in ((six, '65'), (eight, '85')):
                         fit_cmd.run('fslsplit {} split{} -t'.format(f, num))
                         fit_cmd.run('bet split{0}0000 {0}mag -R -f 0.7 -m'.format(num))
                         fit_cmd.run('fslmaths split{0}0002 -mas {0}mag_mask {0}realm'.format(num))
                         fit_cmd.run('fslmaths split{0}0003 -mas {0}mag_mask {0}imagm'.format(num))

                    fit_cmd.run('fslmaths 65realm -mul 85realm realeq1')
                    fit_cmd.run('fslmaths 65imagm -mul 85imagm realeq2')
                    fit_cmd.run('fslmaths 65realm -mul 85imagm imageq1')
                    fit_cmd.run('fslmaths 85realm -mul 65imagm imageq2')
                    fit_cmd.run('fslmaths realeq1 -add realeq2 realvol')
                    fit_cmd.run('fslmaths imageq1 -sub imageq2 imagvol')

                    fit_cmd.run('fslcomplex -complex realvol imagvol calcomplex')
                    fit_cmd.run('fslcomplex -realphase calcomplex phasevolume 0 1')
                    fit_cmd.run('fslcomplex -realabs calcomplex magvolume 0 1')

                    fit_cmd.run('prelude -a 65mag -p phasevolume -m 65mag_mask -o phasevolume_maskUW')

                    fit_cmd.run('fslmaths phasevolume_maskUW -div 0.002 fieldmap_rads')
                    fit_cmd.run('fslmaths fieldmap_rads -div 6.28 fieldmap_Hz')

                    fit_cmd.run('flirt -dof 12 -in magvolume.nii.gz -ref {} -omat xformMagVol_to_diff.mat'.format(bet_name))
                    fit_cmd.run('flirt -in fieldmap_Hz.nii.gz -ref {} -applyxfm -init xformMagVol_to_diff.mat -out fieldmap_Hz_diff'.format(bet_name))


                    #0.000342 = echo spacing in sec; 39 = number of phase encode direction-1; same for all dMRI scans from GE scanner at CAMH
                    fit_cmd.run('printf "0 -1 0 {}" > {}'.format('0.013338', acqp_path))
                    fit_cmd.run('eddy_openmp --imain={} --mask={} --acqp={} --index={} --bvecs={} --bvals={} --field=fieldmap_Hz_diff --out=eddy_openmp --repol --verbose'.format(dti, mask_name, acqp_path, index_path, bvec, bval))
                    for to_copy in ('eddy_openmp.eddy_rotated_bvecs', 'eddy_openmp.nii.gz', 'fieldmap_Hz_diff.nii.gz', 'fieldmap_Hz.nii.gz'):
                        shutil.copyfile(to_copy, os.path.join(fit_sub_dir, '{}_{}'.format(dti_name, to_copy)))
                    fit_cmd.run('dtifit --data=eddy_openmp.nii.gz --mask={} --bvecs=eddy_openmp.eddy_rotated_bvecs --bvals={} --save_tensor --out={}_eddy_dtifit'.format(mask_name, bval, dtifit_basename))
                    fit_cmd.run('fslmaths fieldmap_Hz_diff -abs -bin fieldmap_Hz_diff_bin')
                elif not (dpa_tag or dap_tag or fmap_65_tag or fmap_85_tag):
                    fit_cmd.run('eddy_correct {} eddy_correct {}'.format(dti, reg_vol))
                    fit_cmd.run('fslroi eddy_correct {} {} 1'.format(b0_name, reg_vol))
                    #0.5 fa_thresh
                    fit_cmd.run('bet {} {} -m -f {} -R'.format(b0_name, bet_name, fa_thresh))
                    fit_cmd.run('dtifit -k eddy_correct -m {} -r {} -b {} --save_tensor -o {}_eddy_dtifit'.format(mask_name, bvec, bval, dtifit_basename))
                else:
                    fit_cmd.set_error("Can't run pipeline on {}. Skipping.".format(os.path.basename(dti)))
                    create_error_gif(fit_cmd.get_error(), gifs)
                    logging.critical(fit_cmd.get_error())
                    dti_errors[dti] = fit_cmd.get_error()
                    continue

                #QC
                logging.debug('Creating final DTIFIT QC gifs.')
                if fit_cmd.get_error():
                    create_error_gif(fit_cmd.get_error(), gifs)
                    dti_errors[dti] = fit_cmd.get_error()
                else:
                    mask_overlay(b0_name, mask_name, sub_bet_gif, dti_tmp_dir, dti_name + '_mask', 600, fit_cmd)
                    V1_overlay(fit_file.format('FA'), fit_file.format('V1'), sub_dir_gif, dti_tmp_dir, dti_name + '_V1', 600, fit_cmd)
                    if fmap_65_tag and fmap_85_tag:
                        mask_overlay(b0_name, 'fieldmap_Hz_diff_bin.nii.gz', sub_fm_gif, dti_tmp_dir, dti_name + '_fm', 600, fit_cmd)
                    if fit_cmd.get_error():
                        create_error_gif(fit_cmd.get_error(), gifs)
                        dti_errors[dti] = fit_cmd.get_error()


    if is_enigma():
        logging.debug('Entering ENIGMA mode.')

        if is_group():
            logging.debug('Entering ENIGMA group mode.')
            all_fa_files = glob.glob(os.path.join(fit_dir, '*', '*FA.nii.gz'))
            if len(all_fa_files) == 0 and is_dtifit():
                logging.debug('Using same QC subjects as DTIFIT.')
            else:
                all_dti_files = [x.replace('_eddy_dtifit_FA', '') for x in all_fa_files]

            if len(all_dti_files) != 0:
                logging.debug('Creating ENIGMA QC pages')
                skel_html = os.path.join(enig_qc_dir, '{}skelqc.html')
                for typ in ['FA', 'AD', 'MD', 'RD']:
                    create_qc_page('{} SKELETON QC PAGE'.format(typ), skel_html.format(typ), all_dti_files, skel_gif_form.format(type=typ, base='{}'))

            for typ in ['FA', 'AD', 'MD', 'RD']:
                concat_file = os.path.join(enig_dir, 'enigmaDTI-{}-results.csv'.format(typ))
                typ_rois = glob.glob(os.path.join(enig_dir, '*/ROI/*{}skel_ROIout.csv'.format(typ)))
                if len(typ_rois) == 0:
                    continue
                firstROItxt = pd.read_csv(typ_rois[0], sep=',', dtype=str, comment='#')
                tractnames = firstROItxt['Tract'].tolist() # reads the tract names from the 'Tract' column for template
                tractcolnames = [tract + '_' + typ for tract in tractnames]

                cols = ['id'] + tractcolnames
                results = pd.DataFrame(columns = cols)

                for csv in typ_rois:
                    csvdata = pd.read_csv(csv, sep=',', dtype=str, comment='#')
                    sub = os.path.basename(os.path.dirname(os.path.dirname(csv)))
                    idx = len(results)
                    results = results.append(pd.DataFrame(columns=cols, index=[idx]))
                    results.id[idx] = sub
                    for i in range(len(tractnames)):
                        tractname = tractnames[i]
                        tractcolname = tractcolnames[i]
                        val = float(csvdata.loc[csvdata['Tract']==tractname]['Average'])
                        results[tractcolname][idx] = val
                results.to_csv(concat_file, sep=',', columns = cols, index = False)


        if is_indiv():
            logging.debug('Entering ENIGMA individual mode.')
            if not os.path.isdir(os.path.join(fit_dir, sub)):
                logging.error('Dtifit subject dir does not exist. Exiting. {}'.format(sub))
                clean_and_exit(1)

            search_rule_mask =      os.path.join(fsldir, 'data/standard/LowerCingulum_1mm.nii.gz')
            distance_map =          os.path.join(enigmahome, 'ENIGMA_DTI_FA_skeleton_mask_dst.nii.gz')
            tbss_skeleton_alt =     os.path.join(enigmahome, 'ENIGMA_DTI_FA_skeleton_mask.nii.gz')
            tbss_skeleton =         os.path.join(enigmahome, 'ENIGMA_DTI_FA_skeleton.nii.gz')
            tbss_skeleton_input =   os.path.join(enigmahome, 'ENIGMA_DTI_FA.nii.gz')
            look_up_table =         os.path.join(enigmahome, 'ENIGMA_look_up_table.txt')
            jhu_white_matter =      os.path.join(enigmahome, 'JHU-WhiteMatter-labels-1mm.nii')
            single_sub_ROI =        os.path.join(enigmahome, 'singleSubjROI_exe')
            avg_sub_tracts =        os.path.join(enigmahome, 'averageSubjectTracts_exe')
            skel_thresh =           '0.049' ## don't where the value came from

            try:
                ident = dm.scanid.parse(sub)
            except dm.scanid.ParseException:
                logging.error('{} is not a subject. Exiting.'.format(sub))
                clean_and_exit(1)

            if is_dtifit():
                for dti in checked_subs[sub]:
                    if dti_errors[os.path.basename(dti)] != '':
                        ident, tag, series, description = dm.scanid.parse_filename(dti)
                        dti_name = dm.scanid.make_filename(ident, tag, str(series), description)
                        dti_tmp_dir = os.path.join(enig_tmp_dir, dti_name)
                        create_dir(dti_tmp_dir)
                        for typ in ['FA', 'MD', 'AD', 'RD']:
                            dti_skel_gif = os.path.join(enig_qc_dir, skel_gif_form.format(type=typ, base=dti_name))
                            create_error_gif('DTIFIT: ' + dti_errors[os.path.basename(dti)], [dti_skel_gif])
                clean_and_exit(1)

            FA_files = glob.glob(os.path.join(fit_dir, sub, '*_eddy_dtifit_FA.nii.gz'))

            if FA_files:
                logging.debug('Creating ENIGMA directories for {}'.format(sub))
                fit_sub_dir = os.path.join(fit_dir, sub)
                enig_sub_dir = os.path.join(enig_dir, sub)
                create_dir(enig_sub_dir)
                ROI_dir = os.path.join(enig_sub_dir, 'ROI')
                create_dir(ROI_dir)
                FA_dir = os.path.join(enig_sub_dir, 'FA')

            for FA_file in FA_files:
                logging.debug('Starting ENIGMA process for {}'.format(FA_file))
                enig_cmd = Command(5)
                if is_dtifit():
                    enig_cmd.set_error(fit_cmd.get_error())

                fit_file = FA_file.replace('FA', '{}')
                fit_file_base = os.path.basename(fit_file)
                dti_name = fit_file_base.replace('_eddy_dtifit_{}.nii.gz', '')
                dti_tmp_dir = os.path.join(enig_tmp_dir, dti_name)
                create_dir(dti_tmp_dir)

                skel_ROI_csv = os.path.join(ROI_dir, '{}skel_ROIout'.format(fit_file_base.replace('.nii.gz', '')))
                skel_ROI_csv_avg = os.path.join(ROI_dir, '{}skel_ROIout_avg.csv'.format(fit_file_base.replace('.nii.gz', '')))
                os.chdir(enig_sub_dir)
                FA_mask = os.path.join(enig_sub_dir, 'FA', fit_file_base.format('FA_mask'))
                FA_to_target = os.path.join(enig_sub_dir, 'FA', fit_file_base.format('FA_to_target'))
                FA_to_target_warp = os.path.join(enig_sub_dir, 'FA', fit_file_base.format('FA_to_target_warp'))
                for typ in ['FA', 'MD', 'AD', 'RD']:
                    type_dir = os.path.join(enig_sub_dir, typ)
                    create_dir(type_dir)
                    create_dir(os.path.join(type_dir, 'origdata'))
                    orig_file = os.path.join(type_dir, 'origdata', fit_file_base.format(typ))
                    masked = os.path.join(type_dir, fit_file_base.format(typ))
                    skel = os.path.join(type_dir, fit_file_base.format(typ + 'skel'))
                    to_target = os.path.join(type_dir, fit_file_base.format(typ + '_to_target'))
                    if typ == 'FA':
                        shutil.copyfile(FA_file, os.path.basename(FA_file.replace('_FA', '')))
                        enig_cmd.run(['tbss_1_preproc', os.path.basename(FA_file.replace('_FA', ''))])
                        enig_cmd.run(['tbss_2_reg', '-t', tbss_skeleton_input])
                        enig_cmd.run(['tbss_3_postreg', '-S'])
                    else:
                        if typ == 'MD':
                            shutil.copyfile(fit_file.format(typ), orig_file)
                        elif typ == 'AD':
                            shutil.copyfile(fit_file.format('L1'), orig_file)
                        elif typ == 'RD':
                            enig_cmd.run(['fslmaths', fit_file.format('L2'), '-add', fit_file.format('L3'), '-div', '2', orig_file])
                        enig_cmd.run(['fslmaths', orig_file, '-mas', FA_mask, masked])
                        enig_cmd.run(['applywarp', '-i', masked, '-o', to_target, '-r', FA_to_target, '-w', FA_to_target_warp])
                    enig_cmd.run(['tbss_skeleton', '-i', tbss_skeleton_input, '-s', tbss_skeleton_alt, '-p', skel_thresh, distance_map, search_rule_mask, to_target, skel])
                    if typ == 'FA':
                        enig_cmd.run(['fslmaths', skel, '-mul', '1', skel, '-odt', 'float'])
                    enig_cmd.run([single_sub_ROI, look_up_table, tbss_skeleton, jhu_white_matter, skel_ROI_csv.format(typ), skel])
                    enig_cmd.run([avg_sub_tracts, skel_ROI_csv.format(typ), skel_ROI_csv_avg.format(typ)])
                    dti_skel_gif = os.path.join(enig_qc_dir, skel_gif_form.format(type=typ, base=dti_name))

                    skel_overlay(to_target, skel, dti_skel_gif, dti_tmp_dir, '{}_{}'.format(dti_name, typ), 600, enig_cmd)
                    if enig_cmd.get_error():
                        create_error_gif(enig_cmd.get_error(), [dti_skel_gif])

    logging.info('DONE')
    shutil.rmtree(base_tmp_dir)

if __name__ == "__main__":
    main()
