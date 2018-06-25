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
    dm_proc_dti.py [options] [dtifit|enigma] <study>
    dm_proc_dti.py [options] [dtifit|enigma] <study> group
    dm_proc_dti.py [options] [dtifit|enigma] <study> individual [<subject_id>...]


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
    --reg-vol N                         Registration volume index. For dtifit. [default: 0]
    --fa-thresh N                       FA threshold for bet. For dtifit. [default: 0.5]
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
    Requires FSL/5.0.10, and imagemagick

TODO:
    - Implement --mb=3 mb_off=1 in eddy_openmp
        Available only in FSL/5.0.10
'''
import datman as dm
import datman.utils
import datman.config
import datman.scanid
import os, sys, pdb
import datetime
import tempfile, shutil
import glob
import json
import nibabel as nib
import logging, logging.handlers
import subprocess
from docopt import docopt
import pdb
from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")

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

        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=merged_env)
        out, err = p.communicate()
        logging.debug('Executed command:{}\n{}'.format(cmd, out))
        if p.returncode:
            logging.error('run({}) failed with returncode {}. SDTERR: {}'.format(cmd, p.returncode, err))
        print err
        self.error_msg = err

def create_qc_page(page_title, html_path, sub_ids, gif_structure):
    with open(html_path, 'w') as qc_page:
        qc_page.write('<HTML>')
        qc_page.write('<TITLE>{0}</TITLE>'.format(page_title))
        qc_page.write('<BODY BGCOLOR=#333333>')
        qc_page.write('<h1><font color="white">{0}</font></h1>'.format(page_title))
        qc_page.write("<dl id='gif_list'>")
        for sub in sorted(sub_ids):
            sub_id = os.path.basename(sub)
            sub_id = sub_id[0:sub_id.index('.')]
            gif = gif_structure.format(sub_id)
            qc_page.write('\t<dt style="color:#99CCFF">{0}</a></dt>'.format(gif))
            qc_page.write('\t<dd><a href="{0}"><img src="{0}"></a></dd>'.format(gif))
        qc_page.write('</dl>')
        qc_page.write('</BODY>')
        qc_page.write('</HTML>')

def create_error_gif(error_msg, output_gifs):
    basic_gif = Image.new('RGBA', (1800, 600), (0, 0, 0, 0))
    font = ImageFont.truetype(font='arial', size=30)
    draw = ImageDraw.Draw(basic_gif)
    (width, height) = draw.textsize(error_msg, font)
    error_gif = basic_gif.resize((1800, height + 10))
    draw = ImageDraw.Draw(error_gif)
    draw.text((5, 5), error_msg, font=font, fill=(255, 255, 255, 255))
    for gif in output_gifs:
        with open(gif, 'w+') as fp:
            error_gif.save(gif)

def gif_gridtoline(input_gif, output_gif, tmp_dir, tmp_base,  size):
    sag = os.path.join(tmp_dir, tmp_base + '_sag.gif')
    cor = os.path.join(tmp_dir, tmp_base + '_cor.gif')
    ax = os.path.join(tmp_dir, tmp_base + '_ax.gif')
    # im = Image.open(input_gif)
    dm.utils.run(['convert',input_gif, '-resize', '{0}x{0}'.format(size),input_gif])
    # im = im.convert('RGBA').resize((size, size), resample=Image.BICUBIC)
    # im.save(input_gif)
    dm.utils.run(['convert', input_gif, '-crop', '100x33%+0+0', sag])
    # im.crop((0,0,size,size//3)).save(sag)
    dm.utils.run(['convert', input_gif, '-crop', '100x33%+0+{}'.format(size//3), cor])
    # im.crop((0,size//3, size, size*2//3)).save(cor)
    dm.utils.run(['convert', input_gif, '-crop', '100x33%+0+{}'.format(size*2//3), ax])
    # im.crop((0,size*2//3, size, size)).save(ax)
    dm.utils.run(['montage', '-mode', 'concatenate', '-tile', '3x1', sag, cor, ax, output_gif])

def mask_overlay(background_nii, mask_nii, output_gif, tmp_dir, tmp_base, size):
    B0_masked = os.path.join(tmp_dir, tmp_base + 'B0masked.gif')
    dm.utils.run(['slices', background_nii, mask_nii, '-o', B0_masked])
    gif_gridtoline(B0_masked, output_gif, tmp_dir, tmp_base, size)

def V1_overlay(background_nii, V1_nii, output_gif, tmp_dir, tmp_base, size):
    background = os.path.join(tmp_dir, tmp_base + 'background.gif')
    FA_mask = os.path.join(tmp_dir, tmp_base + 'FAmask.nii.gz')
    V1 = os.path.join(tmp_dir, tmp_base + 'V1{}')
    dirmap = os.path.join(tmp_dir, tmp_base + 'dirmap.gif')
    dm.utils.run(['slices', background_nii, '-o', background])
    dm.utils.run(['fslmaths', background_nii, '-thr', '0.15', '-bin', FA_mask])
    dm.utils.run(['fslsplit', V1_nii, V1.format('')])
    for axis in ['0000', '0001', '0002']:
        dm.utils.run('fslmaths {0}.nii.gz -abs -mul {1} {0}abs.nii.gz'.format(V1.format(axis), FA_mask))
        dm.utils.run('slices {0}abs.nii.gz -o {0}abs.gif'.format(V1.format(axis)))
    dm.utils.run('convert {0}0000abs.gif {0}0001abs.gif {0}0002abs.gif -set colorspace RGB -combine -set colorspace sRGB {1}'.format(V1.format(''), dirmap))
    # im0 = Image.open(V1.format('0000abs.gif'))
    # im1 = Image.open(V1.format('0001abs.gif'))
    # im2 = Image.open(V1.format('0002abs.gif'))
    # Image.merge('RGB', (im0.convert('L'), im1.convert('L'), im2.convert('L'))).save(dirmap)
    gif_gridtoline(dirmap, output_gif, tmp_dir, tmp_base, size)

def skel_overlay(background_nii, skel_nii, output_gif, tmp_dir, tmp_base, size):
    to_target = os.path.join(tmp_dir, tmp_base + 'to_target.gif')
    skel = os.path.join(tmp_dir, tmp_base + 'skel.gif')
    skel_mag = os.path.join(tmp_dir, tmp_base + 'skel_mag.gif')
    cskel = os.path.join(tmp_dir, tmp_base + 'cskel.gif')
    dm.utils.run(['slices', background_nii, '-o', to_target])
    dm.utils.run(['slices', skel_nii, '-o', skel])
    dm.utils.run(['convert', '-fuzz', '10%', '-fill', 'magenta', '-negate', skel, '-transparent', 'white', '-colorize', '100,0,100', skel_mag])
    # to = Image.open(to_target).convert('RGBA')
    # sk = Image.open(skel)
    # mag = ImageOps.colorize(sk.convert('L'), (255,255,255),(255,0,255)).convert('RGBA')
    # mag_data = mag.getdata()
    # transparent_data = []
    # for item in mag_data:
    #     if item[0] == 255 and item[1] == 255 and item[2] == 255:
    #         transparent_data.append((255, 255, 255, 0))
    #     else:
    #         transparent_data.append(item)
    # mag.putdata(transparent_data)
    # mag.save(skel_mag)
    dm.utils.run(['composite', skel_mag, to_target, cskel])
    # Image.alpha_composite(to, mag).save(cskel)
    gif_gridtoline(cskel, output_gif, tmp_dir, tmp_base, size)

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
                     '--DAP-tag', '--DPA-tag', '--FMAP-65-tag', 'FMAP-85-tag',
                     '--fa-thresh', '--reg-vol', '--walltime']:
        flags += [arg_flag, arguments[arg_flag]] if arguments[arg_flag] else []
    for flag in ['--debug', '--dry-run', '--log-to-server', '--output-nVox']:
        flags += [flag] if arguments[flag] else []

    flags += [arguments['<study>']]
    # if arguments['group']:
    #     flags += ['group']
    # elif arguments['individual']:
    #     flags += ['individual']
    #     flags += [" ".join(arguments['<subject_id>'])]
    flags += ['individual', subject]
    return " ".join(flags)

def submit_proc_dti(cd_path, subject, arguments, cfg):
    with dm.utils.cd(cd_path):
        cmd = create_command(subject, arguments)
        logging.debug('Queueing command: {}'.format(cmd))
        job_name = 'dm_proc_dti_{}_{}'.format(subject, time.strftime("%Y%m%d-%H%M%S"))
        dm.utils.submit_job(cmd, job_name, log_dir=LOG_DIR,
                                cpu_cores=1, walltime=arguments['--walltime'],
                                dryrun=False)

def create_dir(dir_path):
    if not os.path.isdir(dir_path):
        logging.info('Creating: {}'.format(dir_path))
        try:
            os.mkdir(dir_path)
        except OSError:
            logging.critical('Failed creating: {}. Exiting.'.format(dir_path), exc_info=True)
            sys.exit(1)

def check_dirs(dtifit, enigma, study, nii_dir, fit_dir, enig_dir, cfg):
    both_pipe = True if not (dtifit or enigma) else False
    # Check nii_dir
    if nii_dir:
        if not os.path.isdir(nii_dir):
            logging.critical('Given nii dir does not exist. Exiting.')
            sys.exit(1)
    elif cfg:
        nii_dir = cfg.get_path('nii')
        if not os.path.isdir(nii_dir):
            logging.critical('Nii dir found through config does not exist.Exiting.')
            sys.exit(1)
    else:
        logging.critical('Nii dir or valid datman configuration required to continue. Exiting.')
        sys.exit(1)
    logging.info('nii_dir will be: {}'.format(nii_dir))

    #Check dtifit dir depending on pipeline
    if (fit_dir and enigma):
        if os.listdir(fit_dir) == []:
            logging.critical("Given dtifit dir is empty. Exiting.")
            sys.exit(1)
    elif (fit_dir and (dtifit or both_pipe)):
        create_dir(fit_dir)
    elif (cfg and enigma):
        fit_dir = cfg.get_path('dtifit')
        if os.listdir(fit_dir) == []:
            logging.critical('Dtifit dir found through config does not exist.Exiting.')
            sys.exit(1)
    elif (cfg and (dtifit or both_pipe)):
        fit_dir = cfg.get_path('dtifit')
        create_dir(fit_dir)
    elif enigma:
        logging.critical('Dtifit dir or valid datman configuration containing data is required to continue. If not available, run without enigma command to create. Exiting.')
        sys.exit(1)
    elif (dtifit or both_pipe):
        logging.critical('Dtifit dir or valid datman configuration required to continue. Exiting.')
        sys.exit(1)
    logging.info('dtifit dir will be: {}'.format(fit_dir))

    #Check enigmaDTI dir
    if (enigma or both_pipe):
        if enig_dir:
            create_dir(enig_dir)
        elif cfg:
            enig_dir = cfg.get_path('enigmaDTI')
            create_dir(enig_dir)
        else:
            logging.critical('EnigmaDTI dir or valid datman configuration required to continue. Exiting.')
            sys.exit(1)
    logging.info('enigma dir will be: {}'.format(enig_dir))

    return nii_dir, fit_dir, enig_dir

def add_file_handler(dir_path, pipeline):
    date = str(datetime.date.today())
    log_path = os.path.join(dir_path, "{}-{}.log".format(date, pipeline))
    fhandler = logging.FileHandler(log_path, "w")
    fhandler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("[%(name)s] %(levelname)s: %(message)s")
    fhandler.setFormatter(formatter)
    logging.getLogger('').addHandler(fhandler)

def setup_log_to_server(cfg):
    server_ip = cfg.get_key('LOGSERVER')
    server_handler = logging.handlers.SocketHandler(server_ip,
            logging.handlers.DEFAULT_TCP_LOGGING_PORT)
    server_handler.setLevel(logging.CRITICAL)
    logging.getLogger('').addHandler(server_handler)

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
    debug = arguments['--debug']
    dry_run = arguments['--dry-run']

    is_dtifit = lambda : dtifit or not (dtifit or enigma)
    is_enigma = lambda : enigma or not (dtifit or enigma)
    is_indiv = lambda : indiv or not (indiv or group)
    is_group = lambda : group or not (indiv or group)

    if debug:
        logging.getLogger('').setLevel(logging.DEBUG)

    if study:
        try:
            cfg = dm.config.config(study=study)
        except:
            cfg = None
            logging.info('Data in not in datman format. Will not be using datman configuarations')

    if (log_to_server and cfg):
        setup_log_to_server(cfg)
    logging.debug(arguments)

    if not os.getenv('FSLDIR'):
        logging.critical('FSLDIR environment variable is undefined. Exiting.')
        sys.exit(1)
    fsldir = os.getenv('FSLDIR')

    if is_enigma():
        if not os.getenv('ENIGMAHOME'):
            logging.critical('ENIGMAHOME environment variable is undefined. Exiting.')
            sys.exit(1)
        enigmahome = os.getenv('ENIGMAHOME')

    nii_dir, fit_dir, enig_dir = check_dirs(dtifit, enigma, study, nii_dir, fit_dir, enig_dir, cfg)

    tmp_dir = tempfile.mkdtemp(dir=enig_dir)

    if is_dtifit():
        fit_qc_dir = os.path.join(fit_dir, 'QC')
        create_dir(fit_qc_dir)
        for qc_type in ['BET', 'directions']:
            qc_type_dir = os.path.join(fit_qc_dir, qc_type)
            create_dir(qc_type_dir)
        bet_gif_form = os.path.join('BET', '{}_b0_bet_mask.gif')
        dir_gif_form = os.path.join('directions', '{}_eddy_dtifit_V1.gif')

        if not sub_ids:
            sub_ids = dm.utils.get_subjects(nii_dir)
        qced_subjects = cfg.get_subject_metadata()
        checked_subs = get_qced_dtis(nii_dir, sub_ids, qced_subjects)

        if is_group():
            all_dti_files = list()
            for dti_list in checked_subs.values():
                all_dti_files += dti_list
            all_dti_files = sorted(all_dti_files)
            bet_html = os.path.join(fit_qc_dir, 'BET.html')
            create_qc_page('DTIFIT BET QC PAGE', bet_html, all_dti_files, bet_gif_form)
            dir_html = os.path.join(fit_qc_dir, 'directions.html')
            create_qc_page('DTIFIT directions QC PAGE', dir_html, all_dti_files, dir_gif_form)

        if is_indiv():
            for sub in sorted(checked_subs.keys()):
                # if indiv and len(sub_ids) > 1:
                #     cd_path = fit_dir if dtifit else enig_dir
                #     submit_proc_dti(cd_path, sub, arguments, cfg)
                #     continue

                fit_sub_dir = os.path.join(fit_dir, sub)
                create_dir(fit_sub_dir)
                sub_tmp_dir = os.path.join(tmp_dir, sub)
                create_dir(sub_tmp_dir)

                nii_sub_dir = os.path.join(nii_dir, sub)
                dti_files = dm.utils.get_files_with_tag(nii_sub_dir, 'DTI', fuzzy=True)
                dti_files = filter(lambda x: x.endswith('.nii.gz'), dti_files)

                for dti in checked_subs[sub]:
                    fit_cmd = Command(5)

                    ident, tag, series, description = dm.scanid.parse_filename(dti)
                    dti_name = dm.scanid.make_filename(ident, tag, str(series), description)
                    dtifit_basename = os.path.join(fit_sub_dir, dti_name)
                    fit_file = '{}_eddy_dtifit_{{}}.nii.gz'.format(dtifit_basename)
                    sub_bet_gif = os.path.join(fit_qc_dir, bet_gif_form.format(dti_name))
                    sub_dir_gif = os.path.join(fit_qc_dir, dir_gif_form.format(dti_name))


                    dti_tmp_dir = os.path.join(sub_tmp_dir, series)
                    create_dir(dti_tmp_dir)
                    os.chdir(dti_tmp_dir)

                    dti_unix = '{}*'.format(dti.split('.')[0])
                    for related_file in glob.glob(dti_unix):
                        if os.path.islink(related_file):
                            linkedto = os.path.realpath(related_file)
                            print linkedto
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

                    with open(bvec, 'r') as bvec_file:
                        bvec_lines = bvec_file.readlines()
                        num_rows = len(bvec_lines)
                        for line in bvec_lines:
                            num_cols = len(line.split())
                        if not (num_rows == 3 and num_cols == num_vols) or (num_rows == num_vols and num_cols == 3):
                            fit_cmd.set_error('bvecs should contain a 3xN or Nx3 matrix where N is the number of volumes in {}'.format(dti_name))
                            logging.error(fit_cmd.get_error())
                            create_error_gif(fit_cmd.get_error(), [sub_bet_gif, sub_dir_gif])
                            continue

                    series = int(series)
                    session = ident.session
                    config = os.path.join(os.getenv('FSLDIR'), 'etc/flirtsch/b02b0.cnf')

                    if dpa_tag or dap_tag:
                        pas = glob.glob(os.path.join(nii_sub_dir, '*{}*.nii.gz'.format(dpa_tag)))
                        pas = sorted(filter(lambda x: get_series(x, session) < series, pas), reverse=True)

                    if dpa_tag and not(dap_tag):
                        with open(dti.replace('nii.gz', 'json'), 'r') as dti_json:
                            dti_data = json.load(dti_json)
                            dti_rep_time = dti_data['RepetitionTime']
                        dpa = match_rep_time(dti_rep_time, pas)

                        if not dpa:
                            fit_cmd.set_error("DPA repetition times does not match with {}. Skipping.\n".format(os.path.basename(dti)))
                            logging.error(fit_cmd.get_error())
                            create_error_gif(fit_cmd.get_error(), [sub_bet_gif, sub_dir_gif])
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
                        fit_cmd.run('dtifit --data=eddy_openmp.nii.gz --mask={} --bvecs=eddy_openmp.eddy_rotated_bvecs --bvals={} --save_tensor --out={}_eddy_dtifit'.format(mask_name, bval, dtifit_basename))
                    elif dpa_tag and dap_tag:
                        aps = glob.glob(os.path.join(nii_sub_dir, '*{}*.nii.gz'.format(dap_tag)))
                        dap = min(aps, key=lambda x: abs(get_series(x, session) - series) if get_series(x, session) < series else sys.maxsize)
                        with open(dap.replace('nii.gz', 'json'), 'r') as dap_json:
                            dap_data = json.load(dap_json)
                            dap_rep_time = dap_data['RepetitionTime']
                        dpa = match_rep_time(dap_rep_time, pas)

                        if not dpa:
                            fit_cmd.set_error("DPA repetition times does not match with {}. Skipping.".format(os.path.basename(dap)))
                            logging.error(fit_cmd.get_error())
                            create_error_gif(fit_cmd.get_error(), [sub_bet_gif, sub_dir_gif])
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
                        fit_cmd.run('dtifit --data=eddy_openmp.nii.gz --mask={} --bvecs=eddy_openmp.eddy_rotated_bvecs --bvals={} --save_tensor --out={}_eddy_dtifit'.format(mask_name, bval, dtifit_basename))
                    elif fmap_65_tag and fmap_85_tag and ident.site == 'CMH':
                        sixes = glob.glob(os.path.join(nii_sub_dir, '*{}*.nii.gz'.format(fmap_65_tag)))
                        eights = glob.glob(os.path.join(nii_sub_dir, '*{}*.nii.gz'.format(fmap_85_tag)))
                        if len(sixes) == 0 or len(eights) == 0:
                            fit_cmd.set_error("No fmaps found for {}. Skipping".format(dti_name))
                            logging.error(fit_cmd.get_error())
                            create_error_gif(fit_cmd.get_error(), [sub_bet_gif, sub_dir_gif])
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
                        fit_cmd.run('fslmaths fieldmap_rads -div 6.28 fieldmap')

                        fit_cmd.run('flirt -dof 6 -in magvolume.nii.gz -ref {} -omat xformMagVol_to_diff.mat'.format(bet_name))
                        fit_cmd.run('flirt -in fieldmap.nii.gz -ref {} -applyxfm -init xformMagVol_to_diff.mat -out fieldmap_diff'.format(bet_name))

                        #0.000342 = echo spacing in sec; 39 = number of phase encode direction-1; same for all dMRI scans from GE scanner at CAMH
                        fit_cmd.run('printf "0 -1 0 {}" > {}'.format('0.013338', acqp_path))

                        fit_cmd.run('eddy_openmp --imain={} --mask={} --acqp={} --index={} --bvecs={} --bvals={} --field=fieldmap_diff --out=eddy_openmp --repol --verbose'.format(dti, mask_name, acqp_path, index_path, bvec, bval))
                        fit_cmd.run('dtifit --data=eddy_openmp.nii.gz --mask={} --bvecs=eddy_openmp.eddy_rotated_bvecs --bvals={} --save_tensor --out={}_eddy_dtifit'.format(mask_name, bval, dtifit_basename))
                    elif not (dpa_tag or dap_tag or fmap_65_tag or fmap_85_tag):
                        fit_cmd.run('eddy_correct {} eddy_correct {}'.format(dti, reg_vol))
                        fit_cmd.run('fslroi eddy_correct {} {} 1'.format(b0_name, reg_vol))
                        #0.5 fa_thresh
                        fit_cmd.run('bet {} {} -m -f {} -R'.format(b0_name, bet_name, fa_thresh))
                        fit_cmd.run('dtifit -k eddy_correct -m {} -r {} -b {} --save_tensor -o {}_eddy_dtifit'.format(mask_name, bvec, bval, dtifit_basename))
                    else:

                        logging.critical("Can't run pipeline.Exiting.")
                        sys.exit(1)

                    #QC
                    if fit_cmd.get_error():
                        create_error_gif(fit_cmd.get_error(), [sub_bet_gif, sub_dir_gif])
                    else:
                        mask_overlay(b0_name, mask_name, sub_bet_gif, dti_tmp_dir, dti_name + '_mask', 600)
                        V1_overlay(fit_file.format('FA'), fit_file.format('V1'), sub_dir_gif, dti_tmp_dir, dti_name + '_V1', 600)

    if is_enigma():
        enig_tmp_dir = os.path.join(tmp_dir, 'enig')
        create_dir(enig_tmp_dir)
        enig_qc_dir = os.path.join(enig_dir, 'QC')
        create_dir(enig_qc_dir)
        for skel_type in [ 'FA', 'AD', 'MD', 'RD']:
            skel_dir = os.path.join(enig_qc_dir, '{}skel'.format(skel_type))
            create_dir(skel_dir)
        skel_gif_form = os.path.join('{type}skel', '{base}_eddy_dtifit_{type}skel.gif')

        if is_group():
            all_dti_files = glob.glob(os.path.join(fit_dir, '*', '*FA.nii.gz'))
            all_dti_files = [x.replace('_eddy_dtifit_FA', '') for x in all_dti_files]
            skel_html = os.path.join(enig_qc_dir, '{}skelqc.html')
            for typ in ['FA', 'AD', 'MD', 'RD']:
                create_qc_page('{} SKELETON QC PAGE'.format(typ), skel_html.format(typ), all_dti_files, skel_gif_form.format(type=typ, base='{}'))

        if is_indiv():
            search_rule_mask =      os.path.join(fsldir, 'data/standard/LowerCingulum_1mm.nii.gz')
            distance_map =          os.path.join(enigmahome, 'ENIGMA_DTI_FA_skeleton_mask_dst.nii.gz')
            tbss_skeleton_alt =     os.path.join(enigmahome, 'ENIGMA_DTI_FA_skeleton_mask.nii.gz')
            tbss_skeleton =         os.path.join(enigmahome, 'ENIGMA_DTI_FA_skeleton.nii.gz')
            tbss_skeleton_input =   os.path.join(enigmahome, 'ENIGMA_DTI_FA.nii.gz')
            look_up_table =         os.path.join(enigmahome, 'ENIGMA_look_up_table.txt')
            jhu_white_matter =      os.path.join(enigmahome, 'JHU-WhiteMatter-labels-1mm.nii')
            single_sub_ROI =        os.path.join(enigmahome, 'singleSubjROI_exe')
            avg_sub_tracts =        os.path.join(enigmahome, 'averageSubjectTracts_exe')
            skel_thresh =           '0.049'

            for sub in sorted(os.listdir(fit_dir)):
                try:
                    ident = dm.scanid.parse(sub)
                except dm.scanid.ParseException:
                    continue

                FA_files = glob.glob(os.path.join(fit_dir, sub, '*_eddy_dtifit_FA.nii.gz'))

                if FA_files:
                    fit_sub_dir = os.path.join(fit_dir, sub)
                    enig_sub_dir = os.path.join(enig_dir, sub)
                    create_dir(enig_sub_dir)
                    ROI_dir = os.path.join(enig_sub_dir, 'ROI')
                    create_dir(ROI_dir)
                    FA_dir = os.path.join(enig_sub_dir, 'FA')

                for FA_file in FA_files:
                    enig_cmd = Command(5)
                    fit_file = FA_file.replace('FA', '{}')
                    fit_file_base = os.path.basename(fit_file)
                    dti_name = fit_file_base.replace('_eddy_dtifit_{}.nii.gz', '')
                    dti_tmp_dir = os.path.join(enig_tmp_dir, dti_name)
                    create_dir(dti_tmp_dir)

                    skel_ROI_csv = os.path.join(ROI_dir, '{}skel_ROIout'.format(fit_file_base.replace('.nii.gz', '')))
                    skel_ROI_csv_avg = os.path.join(ROI_dir, '{}skel_ROIout_avg'.format(fit_file_base.replace('.nii.gz', '')))
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
                        dm.utils.run([single_sub_ROI, look_up_table, tbss_skeleton, jhu_white_matter, skel_ROI_csv.format(typ), skel])
                        dm.utils.run([avg_sub_tracts, skel_ROI_csv.format(typ), skel_ROI_csv_avg.format(typ)])
                        dti_skel_gif = os.path.join(enig_qc_dir, skel_gif_form.format(type=typ, base=dti_name))
                        if enig_cmd.get_error():
                            create_error_gif(enig_cmd.get_error(), [dti_skel_gif])
                        else:
                            skel_overlay(to_target, skel, dti_skel_gif, dti_tmp_dir, '{}_{}'.format(dti_name, typ), 600)


    # shutil.rmtree(tmp_dir)

if __name__ == "__main__":
    main()
