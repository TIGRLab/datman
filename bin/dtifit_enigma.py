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
from docopt import docopt
import pdb

logging.basicConfig(level=logging.WARN,
                    format="[%(name)s] %(levelname)s: %(message)s")

def create_qc_page(page_title, html_path, sub_ids, gif_structure):
    with open(html_path, 'w') as qc_page:
        qc_page.write('<HTML>')
        qc_page.write('<TITLE>{0}</TITLE>'.format(page_title))
        qc_page.write('<BODY BGCOLOR=#333333>')
        qc_page.write('<h1><font color="white">{0}</font></h1>'.format(page_title))
        qc_page.write("<dl id='gif_list'>")
        for sub in sorted(sub_ids):
            gif = gif_structure.format(sub)
            qc_page.write('\t<dt style="color:#99CCFF">{0}</a></dt>'.format(gif))
            qc_page.write('\t<dd><a href="{0}"><img src="{0}"></a></dd>'.format(gif))
        qc_page.write('</dl>')
        qc_page.write('</BODY>')
        qc_page.write('</HTML>')

def gif_gridtoline(input_gif, output_gif, size):
    dm.utils.run(['convert',input_gif, '-resize', '{0}x{0}'.format(size),input_gif])
    sag = '_sag.gif'
    cor = '_cor.gif'
    ax = '_ax.gif'
    dm.utils.run(['convert', input_gif, '-crop', '100x33%+0+0', sag])
    dm.utils.run(['convert', input_gif, '-crop', '100x33%+0+{}'.format(size//3), cor])
    dm.utils.run(['convert', input_gif, '-crop', '100x33%+0+{}'.format(size*2//3), ax])
    dm.utils.run(['montage', '-mode', 'concatenate', '-tile', '3x1', sag, cor, ax, output_gif])


def mask_overlay(background_nii, mask_nii, output_gif, size):
    B0_masked = 'B0masked.gif'
    dm.utils.run(['slices', background_nii, mask_nii, '-o', B0_masked])
    gif_gridtoline(B0_masked, output_gif, size)

def V1_overlay(background_nii, V1_nii, output_gif, size):
    background = 'background.gif'
    FA_mask = 'FAmask.nii.gz'
    dm.utils.run(['slices', background_nii, '-o', background])
    dm.utils.run(['fslmaths', background_nii, '-thr', '0.15', '-bin', FA_mask])
    dm.utils.run(['fslsplit', V1_nii, 'V1'])
    for axis in ['0000', '0001', '0002']:
        dm.utils.run('fslmaths V1{0}.nii.gz -abs -mul {1} V1{0}abs.nii.gz'.format(axis, FA_mask))
        dm.utils.run('slices V1{0}abs.nii.gz -o V1{0}abs.gif'.format(axis))
    dm.utils.run('convert V10000abs.gif V10001abs.gif V10002abs.gif -set colorspace RGB -combine -set colorspace sRGB dirmap.gif')
    gif_gridtoline('dirmap.gif', output_gif, size)

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

    logging.debug('Index content: {}'.format(indx))
    with open(index_path, 'w') as indx_file:
        indx_file.write(indx)
    return dti_dim['dim'][4]

def match_rep_time(time, nii_list):
    matched = None
    for nii in nii_list:
        with open(nii.replace('nii.gz', 'json'), 'r+') as nii_json:
            nii_data = json.load(nii_json)
            if time == nii_data['RepetitionTime']:
                matched = nii
                break
    return matched

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
        logger.debug('Queueing command: {}'.format(cmd))
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
    if (dtifit or both_pipe):
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
    logger.getLogger('').addHandler(fhandler)

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

    print(arguments)

    if debug:
        logging.getLogger('').setLevel(logging.DEBUG)

    if study:
        try:
            cfg = dm.config.config(study=study)
        except:
            cfg = None
            logger.info('Data in not in datman format. Will not be using datman configuarations')


    if (log_to_server and cfg):
        setup_log_to_server(cfg)

    nii_dir, fit_dir, enig_dir = check_dirs(dtifit, enigma, study, nii_dir, fit_dir, enig_dir, cfg)
    both_pipe = True if not (dtifit or enigma) else False
    both_task = True if not (indiv or group) else False

    if not sub_ids:
        sub_ids = dm.utils.get_subjects(nii_dir)

    qced_subjects = cfg.get_subject_metadata()

    tmp_dir = tempfile.mkdtemp(dir=fit_dir)

    if dtifit or both_pipe:
        fit_qc_dir = os.path.join(fit_dir, "QC")
        create_dir(fit_qc_dir)
        bet_dir = os.path.join(fit_qc_dir, "BET")
        create_dir(bet_dir)
        dir_dir = os.path.join(fit_qc_dir, "directions")
        create_dir(dir_dir)
        bet_gif_form = os.path.join('BET', '{}_b0_bet_mask.gif')
        dir_gif_form = os.path.join('directions', '{}_dtifit_V1.gif')

        if group or both_task:

            all_dti_files = []
            for sub_dir in glob.glob(os.path.join(nii_dir, '*')):
                sub_dti_files = dm.utils.get_files_with_tag(sub_dir, 'DTI', fuzzy=True)
                sub_dti_files = filter(lambda x: x.endswith('.nii.gz'), sub_dti_files)
                sub_dti_files = [os.path.basename(x.replace('.nii.gz', '')) for x in sub_dti_files]
                all_dti_files += sub_dti_files

            bet_html = os.path.join(fit_qc_dir, 'BET.html')
            create_qc_page('DTIFIT BET QC PAGE', bet_html, all_dti_files, bet_gif_form)

            dir_html = os.path.join(fit_qc_dir, 'directions.html')
            create_qc_page('DTIFIT directions QC PAGE', dir_html, all_dti_files, dir_gif_form)


    for sub in sub_ids:
        if dm.scanid.is_phantom(sub):
            logging.info('Subject is phantom. Skipping: {}'.format(sub))
            continue

        # try:
        #     blacklisted_series = qced_subjects[sub]
        # except KeyError:
        #     logging.info('Subject has not been QCed. Skipping: {}'.format(sub))
        #     continue



        # if indiv and len(sub_ids) > 1:
        #     cd_path = fit_dir if dtifit else enig_dir
        #     submit_proc_dti(cd_path, sub, arguments, cfg)
        #     continue

        if dtifit or both_pipe:
            fit_sub_dir = os.path.join(fit_dir, sub)
            create_dir(fit_sub_dir)
            sub_tmp_dir = os.path.join(tmp_dir, sub)
            create_dir(sub_tmp_dir)

            if indiv or both_task:
                sub_dir = os.path.join(nii_dir, sub)

                dti_files = dm.utils.get_files_with_tag(sub_dir, 'DTI', fuzzy=True)
                dti_files = filter(lambda x: x.endswith('.nii.gz'), dti_files)
                if not os.getenv('FSLDIR'):
                    logger.critical('FSLDIR environment variable is undefined. Exiting.')
                    sys.exit(1)

                for dti in dti_files:
                    ident, tag, series, description = dm.scanid.parse_filename(dti)

                    dti_name = dm.scanid.make_filename(ident, tag, str(series), description)
                    b0_name = os.path.join(fit_sub_dir, '{}_b0'.format(dti_name))
                    bet_name = os.path.join(fit_sub_dir, '{}_b0_bet'.format(dti_name))
                    mask_name = os.path.join(fit_sub_dir, '{}_b0_bet_mask'.format(dti_name))
                    dtifit_basename = os.path.join(fit_sub_dir, dti_name)

                    index_path = os.path.join(fit_sub_dir, 'index.txt')
                    num_vols = create_index_file(dti, index_path)
                    acqp_path = os.path.join(fit_sub_dir, 'acqparams.txt')


                    dti_tmp_dir = os.path.join(sub_tmp_dir, series)
                    create_dir(dti_tmp_dir)

                    print('\n{}\n'.format(dti))

                    series = int(series)

                    # try:
                    #     blacklisted_series.index(series)
                    #     logger.info("DTI series number in blacklist. Skipping: {}".format(os.path.basename(dti)))
                    #     continue
                    # except ValueError:
                    #     pass

                    get_series = lambda x: int(dm.scanid.parse_filename(x)[2])

                    os.chdir(dti_tmp_dir)
                    dti_unix = '{}*'.format(dti.split('.')[0])
                    for related_file in glob.glob(dti_unix):
                        shutil.copyfile(related_file, os.path.basename(related_file))
                    dti = os.path.basename(dti)
                    bvec = dti.replace('nii.gz', 'bvec')
                    bval = dti.replace('nii.gz', 'bval')

                    config = os.path.join(os.getenv('FSLDIR'), 'etc/flirtsch/b02b0.cnf')

                    if dpa_tag or dap_tag:
                        pas = glob.glob(os.path.join(sub_dir, '*{}*.nii.gz'.format(dpa_tag)))
                        pas = sorted(filter(lambda x: get_series(x) < series, pas), reverse=True)

                    # if dpa_tag and not(dap_tag):
                    #     with open(dti.replace('nii.gz', 'json'), 'r+') as dti_json:
                    #         dti_data = json.load(dti_json)
                    #         dti_rep_time = dti_data['RepetitionTime']
                    #     dpa = match_rep_time(dti_rep_time, pas)
                    #
                    #     if not dpa:
                    #         logging.error("DPA repetition times does not match with {}. Skipping.\n".format(os.path.basename(dti)))
                    #         shutil.rmtree(dti_tmp_dir)
                    #         continue
                    #
                    #     with open(bval, 'r+') as bval_file:
                    #         bvals = bval_file.readline()
                    #     bvals = [ float(i) for i in bvals.split()]
                    #     b0s = [ i for i in range(0, len(bvals)) if bvals[i] == 0]
                    #     print(b0s)
                    #     for val in b0s:
                    #         dm.utils.run('fslroi {0} tmp_{1}.nii.gz {1} 1'.format(dti, val))
                    #     dm.utils.run('fslmerge -t merged_dti_b0.nii.gz tmp_*.nii.gz')
                    #     dm.utils.run('fslmerge -t merged_b0.nii.gz merged_dti_b0.nii.gz {}'.format(dpa))
                    #     acqparams = '0 1 0 0.05\n'
                    #     for i in range(1, int(nib.load('merged_dti_b0.nii.gz').header['dim'][4])):
                    #         acqparams += '0 1 0 0.05\n'
                    #     for i in range(0, int(nib.load(dpa).header['dim'][4])):
                    #         acqparams += '0 -1 0 0.05\n'
                    #     with open(acqp_path, 'w') as acq_file:
                    #         acq_file.write(acqparams)
                    #
                    #     rounded_b0_dims = get_rounded_dims('merged_b0.nii.gz')
                    #     dm.utils.run('fslroi merged_b0.nii.gz merged_b0.nii.gz 0 {d[0]} 0 {d[1]} 1 {d[2]} 0 {d[3]}'.format(d=rounded_b0_dims))
                    #     dm.utils.run('topup --imain=merged_b0.nii.gz --datain={} --config={} --out=topup_b0 --iout={} -v'.format(acqp_path, config, b0_name))
                    #     dm.utils.run('fslmaths {0}.nii.gz -Tmean {0}'.format(b0_name))
                    #     ## 0.5
                    #     dm.utils.run('bet {} {} -m -f {}'.format(b0_name, bet_name, fa_thresh))
                    #     rounded_dti_dims = get_rounded_dims(dti)
                    #     dm.utils.run('fslroi {0} {0} 0 {d[0]} 0 {d[1]} 0 {d[2]} 0 {1}'.format(dti, num_vols, d=rounded_dti_dims))
                    #     dm.utils.run('eddy_openmp --imain={} --mask={}.nii.gz --acqp={} --index={} --bvecs={} --bvals={} --topup=topup_b0 --repol --out=eddy_openmp --data_is_shelled --verbose'.format(dti, mask_name, acqp_path, index_path, bvec, bval))
                    #     dm.utils.run('dtifit --data=eddy_openmp.nii.gz --mask={} --bvecs=eddy_openmp.eddy_rotated_bvecs --bvals={} --save_tensor --out={}_dtifit_eddy'.format(mask_name, bval, dtifit_basename))
                    #
                    # elif dpa_tag and dap_tag:
                    #     aps = glob.glob(os.path.join(sub_dir, '*{}*.nii.gz'.format(dap_tag)))
                    #     dap = min(aps, key=lambda x: abs(get_series(x) - series) if get_series(x) < series else sys.maxsize)
                    #     with open(dap.replace('nii.gz', 'json'), 'r+') as dap_json:
                    #         dap_data = json.load(dap_json)
                    #         dap_rep_time = dap_data['RepetitionTime']
                    #     dpa = match_rep_time(dap_rep_time, pas)
                    #
                    #     if not dpa:
                    #         logging.error("DPA repetition times does not match with {}. Exiting.".format(os.path.basename(dap)))
                    #         sys.exit(1)
                    #
                    #     dm.utils.run('fslroi {} DAP_b0 0 1'.format(dap))
                    #     dm.utils.run('fslroi {} DPA_b0 0 1'.format(dpa))
                    #     dm.utils.run('fslmerge -t merged_b0 DAP_b0 DPA_b0')
                    #     dm.utils.run('printf "0 -1 0 0.05\n0 1 0 0.05" > {}'.format(acqp_path))
                    #     rounded_b0_dims = get_rounded_dims('merged_b0.nii.gz')
                    #     dm.utils.run('fslroi {0} {0} 0 {d[0]} 0 {d[1]} 0 {d[2]} 0 {d[3]}'.format('merged_b0.nii.gz', d=rounded_b0_dims))
                    #     dm.utils.run('topup --imain=merged_b0 --datain={} --config={} --out=topup --iout={} -v'.format(acqp_path, config, b0_name))
                    #     dm.utils.run('fslmaths {0} -Tmean {0}'.format(b0_name))
                    #     #fa_thesh ??? 0.5
                    #     dm.utils.run('bet {} {} -m -f {}'.format(b0_name, bet_name, fa_thresh))
                    #     rounded_dti_dims = get_rounded_dims(dti)
                    #     dm.utils.run('fslroi {0} {0} 0 {d[0]} 0 {d[1]} 0 {d[2]} 0 {1}'.format(dti, num_vols, d=rounded_dti_dims))
                    #     dm.utils.run('eddy_openmp --imain={} --mask={} --acqp={} --index={} --bvecs={} --bvals={} --topup=topup_b0 --repol --out=eddy_openmp --data_is_shelled --verbose'.format(dti, mask_name, acqp_path, index_path, bvec, bval))
                    #     dm.utils.run('dtifit --data=eddy_openmp.nii.gz --mask={} --bvecs=eddy_openmp.eddy_rotated_bvecs --bvals={} --save_tensor --out={}_dtifit_eddy'.format(mask_name, bval, dtifit_basename))
                    # elif fmap_65_tag and fmap_85_tag and ident.site == 'CMH':
                    #     sixes = glob.glob(os.path.join(sub_dir, '*{}*.nii.gz'.format(fmap_65_tag)))
                    #     eights = glob.glob(os.path.join(sub_dir, '*{}*.nii.gz'.format(fmap_85_tag)))
                    #     six = min(sixes, key=lambda x: abs(get_series(x) - series) if get_series(x) < series else sys.maxsize)
                    #     eight = min(eights, key=lambda x: abs(get_series(x) - series) if get_series(x) < series else sys.maxsize)
                    #
                    #     dm.utils.run('fslroi {} {} 0 1'.format(dti, b0_name))
                    #     ##fa-thresh 0/.5
                    #     dm.utils.run('bet {} {} -m -f {}'.format(b0_name, bet_name, fa_thresh))
                    #
                    #     for f, num in ((six, '65'), (eight, '85')):
                    #          dm.utils.run('fslsplit {} split{} -t'.format(f, num))
                    #          dm.utils.run('bet split{0}0000 {0}mag -R -f 0.7 -m'.format(num))
                    #          dm.utils.run('fslmaths split{0}0002 -mas {0}mag_mask {0}realm'.format(num))
                    #          dm.utils.run('fslmaths split{0}0003 -mas {0}mag_mask {0}imagm'.format(num))
                    #
                    #     dm.utils.run('fslmaths 65realm -mul 85realm realeq1')
                    #     dm.utils.run('fslmaths 65imagm -mul 85imagm realeq2')
                    #     dm.utils.run('fslmaths 65realm -mul 85imagm imageq1')
                    #     dm.utils.run('fslmaths 85realm -mul 65imagm imageq2')
                    #     dm.utils.run('fslmaths realeq1 -add realeq2 realvol')
                    #     dm.utils.run('fslmaths imageq1 -sub imageq2 imagvol')
                    #
                    #     dm.utils.run('fslcomplex -complex realvol imagvol calcomplex')
                    #     dm.utils.run('fslcomplex -realphase calcomplex phasevolume 0 1')
                    #     dm.utils.run('fslcomplex -realabs calcomplex magvolume 0 1')
                    #
                    #     dm.utils.run('prelude -a 65mag -p phasevolume -m 65mag_mask -o phasevolume_maskUW')
                    #
                    #     dm.utils.run('fslmaths phasevolume_maskUW -div 0.002 fieldmap_rads')
                    #     dm.utils.run('fslmaths fieldmap_rads -div 6.28 fieldmap')
                    #
                    #     dm.utils.run('flirt -dof 6 -in magvolume.nii.gz -ref {} -omat xformMagVol_to_diff.mat'.format(bet_name))
                    #     dm.utils.run('flirt -in fieldmap.nii.gz -ref {} -applyxfm -init xformMagVol_to_diff.mat -out fieldmap_diff'.format(bet_name))
                    #
                    #     #0.000342 = echo spacing in sec; 39 = number of phase encode direction-1; same for all dMRI scans from GE scanner at CAMH
                    #     dm.utils.run('printf "0 -1 0 {}" > {}'.format('0.013338', acqp_path))
                    #
                    #     dm.utils.run('eddy_openmp --imain={} --mask={} --acqp={} --index={} --bvecs={} --bvals={} --field=fieldmap_diff --out=eddy_openmp --repol --verbose'.format(dti, mask_name, acqp_path, index_path, bvec, bval))
                    #     dm.utils.run('dtifit --data=eddy_openmp.nii.gz --mask={} --bvecs=eddy_openmp.eddy_rotated_bvecs --bvals={} --save_tensor --out={}_dtifit_eddy'.format(mask_name, bval, dtifit_basename))
                    # elif not (dpa_tag or dap_tag or fmap_65_tag or fmap_85_tag):
                    #     dm.utils.run('eddy_correct {} eddy_correct {}'.format(dti, reg_vol))
                    #     dm.utils.run('fslroi eddy_correct {} {} 1'.format(b0_name, reg_vol))
                    #     #0.5 fa_thresh
                    #     dm.utils.run('bet {} {} -m -f {} -R'.format(b0_name, bet_name, fa_thresh))
                    #     dm.utils.run('dtifit -k eddy_correct -m {} -r {} -b {} --save_tensor -o {}_dtifit_eddy'.format(mask_name, bvec, bval, dtifit_basename))
                    # else:
                    #     logging.critical("Can't run pipeline.Exiting.")
                    #     sys.exit(1)

                    #QC
                    FA_file = '{}_dtifit_eddy_FA.nii.gz'.format(dtifit_basename)
                    V1_file = '{}_dtifit_eddy_V1.nii.gz'.format(dtifit_basename)

                    sub_bet_gif = os.path.join(fit_qc_dir, bet_gif_form.format(dti_name))
                    sub_dir_gif = os.path.join(fit_qc_dir, dir_gif_form.format(dti_name))
                    mask_overlay(b0_name, mask_name, sub_bet_gif, 600)
                    V1_overlay(FA_file, V1_file, sub_dir_gif, 600)

    # shutil.rmtree(tmp_dir)

if __name__ == "__main__":
    main()
