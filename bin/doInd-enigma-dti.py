#!/usr/bin/env python
"""
This run ENIGMA DTI pipeline on one FA map.
This was made to be called from dm-proc-engimadti.py.

Usage:
  doInd-enigma-dti.py [options] <output_dir> <input_fa>

Arguments:
    <output_dir>        Top directory for the output file structure
    <input_fa>         Full path to input FA map to process

Options:
  --calc-MD                Option to process MD image as well
  --calc-all               Option to process MD, AD and RD
  -v,--verbose             Verbose logging
  --debug                  Debug logging in Erin's very verbose style
  -n,--dry-run             Dry run
  -h,--help                Print this help

DETAILS
This run ENIGMA DTI pipeline on one FA map.
This was made to be called from dm-proc-engimadti.py - which runs enigma-dti protocol
for a group of subjects (or study) - then creates a group csv output and QC.

We recommend specifying an outputdir that doesn't yet exist (ex. enigmaDTI/<subjectID/).
This script will create the ouputdir and copy over the relevant inputs.
Why? Because this meant to work in directory with only ONE FA image!! (ex. enigmaDTI/<subjectID/).
Having more than one FA image in the outputdir would lead to crazyness during the TBSS steps.
So, the script will not run if more than one FA image (or the wrong FAimage) is present in the outputdir.

By default, this extracts FA values for each ROI in the atlas.
To extract MD as well, call with the "--calc-MD" option.
To extract FA, MD, RD and AD, call with the "--calc-all" option.

Requires ENIGMA dti enviroment to be set (for example):
module load FSL/5.0.7 R/3.1.1 ENIGMA-DTI/2015.01

also requires datman python enviroment.

Written by Erin W Dickie, July 30 2015
Adapted from ENIGMA_MASTER.sh - Generalized October 2nd David Rotenberg Updated Feb 2015 by JP+TB
Runs pipeline outlined by enigma-dti:
http://enigma.ini.usc.edu/protocols/dti-protocols/
"""
from docopt import docopt
import pandas as pd
import datman as dm
import datman.utils
import datman.scanid
import glob
import os
import sys

def main():
    arguments = docopt(__doc__)
    output_di = arguments['<outputdir>']
    FAmap     = arguments['<FAmap>']
    CALC_MD   = arguments['--calc-MD']
    CALC_ALL  = arguments['--calc-all']
    VERBOSE   = arguments['--verbose']
    DEBUG     = arguments['--debug']
    DRYRUN    = arguments['--dry-run']

    if DEBUG:
        print arguments

    if os.path.isfile(FAmap) == False:
        sys.exit("Input file {} doesn't exist.".format(FAmap))

    if CALC_MD | CALC_ALL:
        MDmap = FAmap.replace('FA.nii.gz','MD.nii.gz')
        if os.path.isfile(MDmap) == False:
          sys.exit("Input file {} doesn't exist.".format(MDmap))

    if CALC_ALL:
        for L in ['L1.nii.gz','L2.nii.gz','L3.nii.gz']:
            Lmap = FAmap.replace('FA.nii.gz', L)
            if os.path.isfile(MDmap) == False:
              sys.exit("Input file {} doesn't exist.".format(Lmap))

    output_dir = os.path.abspath(output_dir)
    skel_thresh = 0.049

    # if the output directory exists, delete it
    if os.path.isdir(output_dir):
        shutil.rmtree(output_dir)

    # find enigma and freesurfer
    enigma_home = os.path.dirname(utils.run('which ENIGMA_MASTER_MD.sh')[1].strip())
    fsl_dir = os.path.dirname(os.path.dirname(utils.run('which fsl')[1].strip()))

    if len(enigma_home) == 0:
        logger.error('enigma is not on your path')
        sys.exit(1)
    elif len(fsl_dir) == 0:
        logger.error('fsl is not on your path')
        sys.exit(1)

    # find atlas nifti files
    distance_map = os.path.join(enigma_home,'ENIGMA_DTI_FA_skeleton_mask_dst.nii.gz')
    search_rule_mask = os.path.join(fsl_dir,'data','standard','LowerCingulum_1mm.nii.gz')
    tbss_skeleton_input = os.path.join(enigma_home,'ENIGMA_DTI_FA.nii.gz')
    tbss_skeleton_alt = os.path.join(enigma_home, 'ENIGMA_DTI_FA_skeleton_mask.nii.gz')

    # output file names
    roi_dir = utils.define_folder(os.path.join(output_dir, 'ROI'))
    img_basename = os.path.basename(input_fa.replace('_FA.nii.gz',''))
    img_fa = img_basename + '.nii.gz'
    img_skel = os.path.join(outputdir,'FA', img_basename + '_FAskel.nii.gz')

    csv_out = os.path.join(roi_dir, img_basename + '_FAskel_ROIout.csv')
    csv_out_avg = os.path.join(roi_dir, img_basename + '_FAskel_ROIout_avg.csv')

    # copy input fa file to working directory
    utils.run('cp {} {} '.format(input_fa, os.path.join(output_dir, img_fa))

    os.chdir(output_dir)

    logger.debug("TBSS step 1: preproc")
    utils.run('tbss_1_preproc {}'.format(img_fa))

    logger.debug("TBSS step 2: reg")
    utils.run('tbss_2_reg -t {}'.format(os.path.join(ENIGMAHOME,'ENIGMA_DTI_FA.nii.gz')))

    logger.debug("TBSS step 3: postreg")
    utils.run('tbss_3_postreg -S')

    logger.debug("TBSS step 4: skeletonize")
    utils.run('tbss_skeleton -i {} -s {} -p {} {} {} {} {}'.format(
        tbss_skeleton_input, tbss_skeleton_alt, skel_thresh, distancemap, search_rule_mask, 'FA/{}_FA_to_target.nii.gz'.format(img_basename), img_skel))

    logger.debug("Convert skeleton datatype to 'float'...")
    utils.run('fslmaths {} -mul 1 {} -odt float'.format(img_skel, img_skel))

    logger.debug('roi extraction step 1')
    utils.run('{} {} {} {} {} {}'.format(
        os.path.join(enigma_home, 'singleSubjROI_exe'),
        os.path.join(enigma_home, 'ENIGMA_look_up_table.txt'),
        os.path.join(enigma_home, 'ENIGMA_DTI_FA_skeleton.nii.gz'),
        os.path.join(enigma_home, 'JHU-WhiteMatter-labels-1mm.nii'),
        csv_out, img_skel))

    logger.debug('roi extraction step 2')
    utils.run('{} {} {}'.format(os.path.join(ENIGMAHOME, 'averageSubjectTracts_exe'), csv_out, csv_out_avg))

    ## jdv: ok -- what is going on here?
    # extract medial, axial, radial diffusivity
    O_dir = os.path.join(outputdir,DTItag)
    O_dir_orig = os.path.join(O_dir, 'origdata')
    dm.utils.makedirs(O_dir_orig)

    if DTItag == 'MD':
        image_i = input_fa.replace('FA.nii.gz','MD.nii.gz')
        image_o = os.path.join(O_dir_orig,image_noext + '_' + DTItag + '.nii.gz')
        # copy over the MD image if not done already
        if os.path.isfile(image_o) == False:
            dm.utils.run(['cp',image_i,image_o])

    if DTItag == 'AD':
        image_i = input_fa.replace('FA.nii.gz','L1.nii.gz')
        image_o = os.path.join(O_dir_orig,image_noext + '_' + DTItag + '.nii.gz')
        # copy over the AD image - this is _L1 in dti-fit
        if os.path.isfile(image_o) == False:
            dm.utils.run(['cp',image_i,image_o])

    if DTItag == 'RD':
        imageL2 = input_fa.replace('FA.nii.gz','L2.nii.gz')
        imageL3 = input_fa.replace('FA.nii.gz','L3.nii.gz')
        image_o = os.path.join(O_dir_orig,image_noext + '_' + DTItag + '.nii.gz')

        # create the RD image as an average of '_L2' and '_L3' images from dti-fit
        if os.path.isfile(image_o) == False:
            utils.run(['fslmaths', imageL2, '-add', imageL3, '-div', "2", image_o])

    masked =    os.path.join(O_dir, img_basename + '_' + DTItag + '.nii.gz')
    to_target = os.path.join(O_dir, img_basename + '_' + DTItag + '_to_target.nii.gz')
    skel =      os.path.join(O_dir, img_basename + '_' + DTItag +'skel.nii.gz')
    csvout1 =   os.path.join(ROIoutdir, img_basename + '_' + DTItag + 'skel_ROIout')
    csvout2 =   os.path.join(ROIoutdir, img_basename + '_' + DTItag + 'skel_ROIout_avg')

    ## mask with subjects FA mask
    utils.run('fslmaths {} -mas {} {}'.format(image_o, os.path.join(outputdir,'FA', image_noext + '_FA_mask.nii.gz'), masked))

    # applywarp calculated for FA map
    utils.run('applywarp -i {} -o {} -r {} -w {}'.format(
        masked, to_target, os.path.join(outputdir,'FA', 'target'), os.path.join(outputdir,'FA', image_noext + '_FA_to_target_warp.nii.gz')))

    ## tbss_skeleton step
    dm.utils.run(['tbss_skeleton', \
          '-i', tbss_skeleton_input, \
          '-s', tbss_skeleton_alt, \
          '-p', str(skel_thresh), distancemap, search_rule_mask,
           to_target, skel])

    ## ROI extract
    dm.utils.run([os.path.join(ENIGMAHOME,'singleSubjROI_exe'),
              os.path.join(ENIGMAHOME,'ENIGMA_look_up_table.txt'), \
              os.path.join(ENIGMAHOME, 'ENIGMA_DTI_FA_skeleton.nii.gz'), \
              os.path.join(ENIGMAHOME, 'JHU-WhiteMatter-labels-1mm.nii.gz'), \
              csvout1, skel])

    ## ROI average
    dm.utils.run([os.path.join(ENIGMAHOME, 'averageSubjectTracts_exe'),
                  csvout1 + '.csv', csvout2 + '.csv'])

    ## run the pipeline for MD - if asked
    if CALC_MD | CALC_ALL:
        run_non_FA('MD')

    ## run the pipeline for AD and RD - if asked
    if CALC_ALL:
        run_non_FA('AD')
        run_non_FA('RD')

    ###############################################################################
    os.putenv('SGE_ON','true')
    print("Done !!")

if __name__ == '__main__':
    main()
