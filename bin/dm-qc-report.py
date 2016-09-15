#!/usr/bin/env python
"""
Runs quality control on defined MRI data types.

Usage:
    dm-qc <datadir> <qcdir>

Options:
    --project-settings YML  File with project settings (to read expected file list from)
    --subject SCANID        Scan ID to QC for. E.g. DTI_CMH_H001_01_01
    --rewrite               Rewrite the html of an existing qc page
    --verbose               Be chatty
    --debug                 Be extra chatty
    --dry-run               Don't actually do any work

DETAILS

    This program requires the AFNI toolkit to be available, as well as NIFTI
    scans for each acquisition to be QC'd. That is, it searches for exported
    nifti acquistions in:

        <datadir>/nii/<timepoint>

    The database stores some of the numbers plotted here, and is used by web-
    build to generate interactive charts detailing the acquisitions over time.

"""

import os, sys
import glob
import logging
import datetime
import datman as dm
import subprocess as proc
from copy import copy
from datman.docopt import docopt
import re
import tempfile
import textwrap
import yaml
import pandas as pd

logging.basicConfig(level=logging.WARN,
    format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

DEBUG = False
VERBOSE = False
DRYRUN = False
FIGDPI = 144
REWRITE = False

SUBJECT_HANDLERS = {   # map from tag to QC function
    "T1"            : anat_qc,
    "T2"            : anat_qc,
    "PD"            : anat_qc,
    "PDT2"          : anat_qc,
    "FLAIR"         : anat_qc,
    "FMAP"          : ignore,
    "FMAP-6.5"      : ignore,
    "FMAP-8.5"      : ignore,
    "RST"           : fmri_qc,
    "EPI"           : fmri_qc,
    "SPRL"          : fmri_qc,
    "OBS"           : fmri_qc,
    "IMI"           : fmri_qc,
    "NBK"           : fmri_qc,
    "EMP"           : fmri_qc,
    "VN-SPRL"       : fmri_qc,
    "SID"           : fmri_qc,
    "MID"           : fmri_qc,
    "DTI"           : dti_qc,
    "DTI21"         : dti_qc,
    "DTI22"         : dti_qc,
    "DTI23"         : dti_qc,
    "DTI60-29-1000" : dti_qc,
    "DTI60-20-1000" : dti_qc,
    "DTI60-1000"    : dti_qc,
    "DTI60-b1000"   : dti_qc,
    "DTI33-1000"    : dti_qc,
    "DTI33-b1000"   : dti_qc,
    "DTI33-3000"    : dti_qc,
    "DTI33-b3000"   : dti_qc,
    "DTI33-4500"    : dti_qc,
    "DTI33-b4500"   : dti_qc,

}

PHANTOM_HANDLERS = { # map from tag to QC function
    "T1"            : phanton_anat_qc,
    "RST"           : phantom_fmri_qc,
    "DTI60-1000"    : phantom_dti_qc,
}

# adds qascripts to the environment
ASSETS = '{}/assets'.format(os.path.dirname(dm.utils.script_path()))
os.environ['PATH'] += os.pathsep + ASSETS + '/qascripts_version2'

class Document:
    pass

###############################################################################
# HELPERS

def makedirs(path):
    logger.debug("makedirs: {}".format(path))
    if not DRYRUN: os.makedirs(path)

def run(cmd):
    logger.debug("exec: {}".format(cmd))
    if not DRYRUN:
        p = proc.Popen(cmd, shell=True, stdout=proc.PIPE, stderr=proc.PIPE)
        out, err = p.communicate()
        if p.returncode != 0:
            logger.error("Error {} while executing: {}".format(p.returncode, cmd))
            out and logger.error("stdout: \n>\t{}".format(out.replace('\n','\n>\t')))
            err and logger.error("stderr: \n>\t{}".format(err.replace('\n','\n>\t')))
        else:
            logger.debug("rtnval: {}".format(p.returncode))
            out and logger.debug("stdout: \n>\t{}".format(out.replace('\n','\n>\t')))
            err and logger.debug("stderr: \n>\t{}".format(err.replace('\n','\n>\t')))

def slicer(fpath, pic, slicergap, picwidth):
    """
    Uses FSL's slicer function to generate a montage png from a nifti file
        fpath       -- submitted image file name
        slicergap   -- int of "gap" between slices in Montage
        picwidth    -- width (in pixels) of output image
        pic         -- fullpath to for output image
    """
    run("slicer {} -S {} {} {}".format(fpath,slicergap,picwidth,pic))

def get_scan_date(data_path, subject):
    """
    This finds the 'imageactualdate' field and converts it to week number.
    If we don't find this date, we return -1.
    """
    dcm_path = os.path.join(data_path, 'dcm', subject)
    dicoms = os.listdir(dcm_path)
    trys = ['imageactualdate', 'seriesdate']
    for dicom in dicoms:
        # read in the dicom header
        d = dcm.read_file(os.path.join(dcm_path, dicom))

        for t in trys:
            if t == 'imageactualdate':
                try:
                    imgdate = d['0009','1027'].value
                    disc = datetime.datetime.fromtimestamp(float(imgdate)).strftime("%Y %B %d")
                    imgdate = datetime.datetime.fromtimestamp(float(imgdate)).strftime("%U")
                    return int(imgdate), disc
                except:
                    pass

            if t == 'seriesdate':
                try:
                    imgdate = d['0008','0021'].value
                    disc = datetime.datetime.strptime(imgdate, '%Y%m%d').strftime("%Y %B %d")
                    imgdate = datetime.datetime.strptime(imgdate, '%Y%m%d').strftime("%U")
                    return int(imgdate), disc
                except:
                    pass

    # if we don't find a date, return -1. This won't break the code, but
    # will raise the alarm that somthing is wrong.
    print("ERROR: No DICOMs with valid date field found for {} !".format(subject))
    return -1, 'NA'

def found_files_df(config, scanpath, subject):
    '''
    reads in the export info from the config file and
    compares it to the contents of the subjects nii folder (scanpath)
    write the results out info a pandas dataframe
    '''
    allfiles = []
    for filetype in ('*.nii.gz', '*.nii'):
        allfiles.extend(glob.glob(scanpath + '/*' + filetype))

    allbfiles = []
    for file in allfiles:
        allbfiles.append(os.path.basename(file))

    # initialize the DataFrame
    cols = ['tag', 'File', 'bookmark', 'Note']
    exportinfo = pd.DataFrame(columns=cols)
    idx = 0

    # for the subjects site - compare filelist to exportinfo
    for sitedict in config['Sites']:
        site = sitedict.keys()[0]

        if site in subject:
            for row in sitedict[site]['ExportInfo']:
                tag = row.keys()[0]
                expected_count = row[tag]['Count']
                tagstring = "_{}_".format(tag)
                bfiles = [k for k in allbfiles if tagstring in k]
                bfiles.sort()
                filenum = 1

                for bfile in bfiles:
                    bookmark = tag + str(filenum)
                    notes='Repeated Scan' if filenum > expected_count else ''
                    exportinfo.loc[idx] = [tag, bfile, bookmark, notes]
                    idx += 1
                    filenum += 1

                if filenum < (expected_count + 1):
                    notes='missing({})'.format(expected_count-filenum + 1)
                    exportinfo.loc[idx] = [tag, '', '', notes]
                    idx += 1

    # add any extra files to the end
    exportinfoFiles = exportinfo.File.tolist()
    PDT2scans = [k for k in exportinfoFiles if '_PDT2_' in k]
    if len(PDT2scans) > 0:
        for PDT2scan in PDT2scans:
            exportinfoFiles.append(PDT2scan.replace('_PDT2_','_T2_'))
            exportinfoFiles.append(PDT2scan.replace('_PDT2_','_PD_'))

    otherscans = list(set(allbfiles) - set(exportinfoFiles))
    for oscan in otherscans:
        exportinfo.loc[idx] = ['unknown', oscan, '', 'extra scan']
        idx += 1

    return(exportinfo)

def qchtml_writetable(qchtml, exportinfo):
    # header
    qchtml.write('<table>'
                '<tr><th>Tag</th>'
                '<th>File</th>'
                '<th>Notes</th></tr>')

    # write each row
    for row in range(0,len(exportinfo)):
        qchtml.write('<tr><td>{}</td>'.format(exportinfo.loc[row,'tag'])) ## table new row
        qchtml.write('<td><a href="#{}">{}</a></td>'.format(exportinfo.loc[row,'bookmark'],exportinfo.loc[row,'File']))
        qchtml.write('<td><font color="#FF0000">{}</font></td></tr>'.format(exportinfo.loc[row,'Note'])) ## table new row

    qchtml.write('</table>\n')

def nifti_basename(fpath):
    """
    return basename with out .nii.gz extension
    """
    basefpath = os.path.basename(fpath)
    stem = basefpath.replace('.nii.gz','')
    return(stem)

def add_pic_to_html(qchtml, pic):
    '''
    Adds a pic to an html page with this handler "qchtml"
    '''
    relpath = os.path.relpath(pic,os.path.dirname(qchtml.name))
    qchtml.write('<a href="'+ relpath + '" >')
    qchtml.write('<img src="' + relpath + '" > ')
    qchtml.write('</a><br>\n')
    return qchtml

###############################################################################
# PIPELINES

def ignore(fpath, qcpath, qchtml, cur):
    pass

def phantom_fmri_qc:
    datman_config = os.getenv('datman_config')
    if datman_config:
        qc_code = parse_config(datman_config, 'phantom-qc')
    else:
        sys.exit('ERROR: datman_config env variable is not defined.')

    outputfile = os.path.join(base_path, 'qc/phantom/fmri/', subj + '.csv')
    if os.path.isfile(outputfile) == False:
        cmd = (r"addpath(genpath('{}')); analyze_fmri_phantom('{}','{}','{}')".format(qc_code, base_path, subj, phantom))
        os.system('matlab -nodisplay -nosplash -r "' + cmd + '"')

    data = np.genfromtxt(outputfile, delimiter=',',dtype=np.float, skip_header=1)

def phantom_dti_qc:

    datman_config = os.getenv('datman_config')
    if datman_config:
        qc_code = parse_config(datman_config, 'phantom-qc')
    else:
        sys.exit('ERROR: datman_config env variable is not defined.')

    output = os.path.join(base_path, 'qc/phantom/dti/', subj)
    dm.utils.makedirs(output)
    outputfile = os.path.join(output, 'main_stats.csv')

    # NB: generate FA file to run
    if os.path.isfile(outputfile) == False:
        cmd = (r"addpath(genpath('{}')); analyze_dti_phantom('{}','{}','{}', '{}', {})".format(
                                               qc_code, raw, fa, bval, output, 1))
        os.system('matlab -nodisplay -nosplash -r "' + cmd + '"')

    data = np.genfromtxt(outputfile, delimiter=',',dtype=np.float, skip_header=1)

    return data

def phantom_anat_qc:

def fmri_qc(fpath, qcpath, qchtml):

    # if the number of TRs is too little, we skip the pipeline
    ntrs = check_n_trs(fpath)

    # check scan length
    qc-scanlength

    filename = os.path.basename(fpath)
    filestem = nifti_basename(fpath)

    # BOLD-contrast
    add_pic_to_html(qchtml, BOLDpic)

    # sfnr
    add_pic_to_html(qchtml, SNR)

    # spikes
    add_pic_to_html(qchtml, spikespic)

    # run metrics from qascripts toolchain
    run('ln -s {fpath} {t}/fmri.nii.gz'.format(fpath=fpath, t=tmpdir))
    run('qa_bold_v2.sh {t}/fmri.nii.gz {t}/qc_fmri.csv'.format(t=tmpdir))
    run('mv {t}/qc_fmri.csv {qcpath}/{filestem}_qascript_fmri.csv'.format(t=tmpdir, filestem=filestem, qcpath=qcpath))
    run('rm -r {}'.format(tmpdir))

def anat_qc(fpath, qcpath, qchtml):
    pic = os.path.join(qcpath, nifti_basename(fpath) + '.png')
    fslslicer_pic(fpath, pic, 5, 1600)
    add_pic_to_html(qchtml, pic)

def dti_qc(fpath, qcpath, qchtml):
    filestem = nifti_basename(fpath)
    directory = os.path.dirname(fpath)
    bvec = fpath[:-len(datman.utils.get_extension(fpath))] + ".bvec"
    bval = fpath[:-len(datman.utils.get_extension(fpath))] + ".bval"

    # first B0
    b0pic = os.path.join(qcpath, filestem + '_B0.png')
    slicer(fpath, b0pic, 2, 1600)
    add_pic_to_html(qchtml, B0pic)

    # spikes
    add_pic_to_html(qchtml, spikespic)

    # run metrics from qascripts toolchain
    tmpdir = tempfile.mkdtemp(prefix='qc-')
    run('ln -s {fpath} {t}/dti.nii.gz'.format(fpath=fpath, t=tmpdir))
    run('ln -s {bvec} {t}/dti.bvec'.format(bvecfile=bvec, t=tmpdir))
    run('ln -s {bval} {t}/dti.bval'.format(bvalfile=bval, t=tmpdir))
    run('qa_dti_v2.sh {t}/dti.nii.gz {t}/dti.bval {t}/dti.bvec {t}/qc_dti.csv'.format(t=tmpdir))
    run('mv {t}/qc_dti.csv {qcpath}/{filestem}_qascript_dti.csv'.format(t=tmpdir, filestem=filestem, qcpath=qcpath))

    run('rm -r {}'.format(tmpdir))

def header_qc(fpath, qchtml, logdata):
    filestem = os.path.basename(fpath).replace(dm.utils.get_extension(fpath),'')
    lines = [re.sub('^.*?: *','',line) for line in logdata if filestem in line]
    if not lines:
        return

    qchtml.write('<h3> {} header differences </h3>\n<table>'.format(filestem))
    for l in lines:
        qchtml.write('<tr><td>{}</td></tr>'.format(l))
    qchtml.write('</table>\n')

def bvec_qc(fpath, qchtml, logdata):
    filestem = os.path.basename(fpath).replace(dm.utils.get_extension(fpath),'')
    lines = [re.sub('^.*'+filestem,'',line) for line in logdata if filestem in line]
    if not lines:
        return

    #text ='\n'.join(['\n'.join(textwrap.wrap(l,width=120,subsequent_indent=" "*4)) for l in lines])

    qchtml.write('<h3> {} bvec/bval differences </h3>\n<table>'.format(filestem))
    for l in lines:
        qchtml.write('<tr><td>{}</td></tr>'.format(l))
    qchtml.write('</table>\n')

def qc_phantom(scanpath, subject, qcdir, pconfig):

def qc_subject(scanpath, subject, qcdir, pconfig):
    """
    QC all the images in a folder (scanpath) for a human participant. Report
    written to  outputdir. pconfig is loaded from the project_settings.yml file
    """

    qcdir = dm.utils.define_folder(qcdir)
    qcpath = dm.utils.define_folder(os.path.join(qcdir, subject))
    htmlfile = os.path.join(qcpath, 'qc_{}.html'.format(subject))

    if os.path.exists(htmlfile) and not REWRITE:
        logger.debug("MSG: {} exists, skipping.".format(htmlfile))
        return

    if REWRITE:
        try:
            os.remove(htmlfile)
        except:
            pass

    qchtml = open(htmlfile, 'wb')
    qchtml.write('<HTML><TITLE>{} qc</TITLE>\n'.format(subject))
    qchtml.write('<head>\n<style>\n'
                'body { font-family: futura,sans-serif;'
                '        text-align: center;}\n'
                'img {width:90%; \n'
                '   display: block\n;'
                '   margin-left: auto;\n'
                '   margin-right: auto }\n'
                'table { margin: 25px auto; \n'
                '        border-collapse: collapse;\n'
                '        text-align: left;\n'
                '        width: 90%; \n'
                '        border: 1px solid grey;\n'
                '        border-bottom: 2px solid black;} \n'
                'th {background: black;\n'
                '    color: white;\n'
                '    text-transform: uppercase;\n'
                '    padding: 10px;}\n'
                'td {border-top: thin solid;\n'
                '    border-bottom: thin solid;\n'
                '    padding: 10px;}\n'
                '</style></head>\n')

    qchtml.write('<h1> QC report for {} <h1/>'.format(subject))

    # read exportinfo from config_yml
    exportinfo = found_files_df(pconfig, scanpath, subject)
    qchtml_writetable(qchtml, exportinfo)

    # find and link technotes
    if 'CMH' in subject:
        techglob = '{}/../../RESOURCES/{}*/*/*/*.pdf'.format(scanpath, subject)
        technotes = glob.glob(techglob)

        if len(technotes) > 0:
            techrelpath = os.path.relpath(os.path.abspath(technotes[0]), os.path.dirname(qchtml.name))
            qchtml.write('<a href="'+ techrelpath + '" >\n'
                         'Click Here to open Tech Notes'
                         '</a><br>\n')
        else:
            qchtml.write('<p>Tech Notes not found</p>\n')

    # load up any header/bvec check log files for the subjectt
    # !!! RUN HEADER CHECK HERE !!! #
    header_check_logs = glob.glob(os.path.join(qcdir, 'logs', 'dm-check-headers-{}*'.format(subject)))
    header_check_log = []
    for logfile in header_check_logs:
        header_check_log += open(logfile).readlines()
    add_header_checks(fname, qchtml, header_check_log)

    # !!! RUN BVEC/BVAL CHECK HERE !!! #
    # load up any header/bvec check log files for the subjectt
    bvecs_check_logs = glob.glob(os.path.join(qcdir, 'logs', 'dm-check-bvecs-{}*'.format(subject)))
    bvecs_check_log = []
    for logfile in bvecs_check_logs:
        bvecs_check_log += open(logfile).readlines()
    add_bvec_checks(fname, qchtml, bvecs_check_log)

    for idx in range(0,len(exportinfo)):
        bname = exportinfo.loc[idx,'File']
        if bname!='' :
            fname = os.path.join(scanpath, bname)
            logger.info("QC scan {}".format(fname))
            ident, tag, series, description = dm.scanid.parse_filename(fname)
            qchtml.write('<h2 id="{}">{}</h2>\n'.format(exportinfo.loc[idx,'bookmark'], bname))

            if tag not in QC_HANDLERS:
                logger.info("MSG: No QC tag {} for scan {}. Skipping.".format(tag, fname))
                continue

            QC_HANDLERS[tag](fname, qcpath, qchtml, cur)
            qchtml.write('<br>')

    qchtml.close()

def main():
    """
    This spits out our QCed data
    """
    global VERBOSE
    global DEBUG
    global DRYRUN
    global REWRITE

    arguments = docopt(__doc__)

    datadir   = arguments['<datadir>']
    qcdir     = arguments['<qcdir>']

    ymlfile   = arguments['--project-settings']
    scanid    = arguments['--subject']
    REWRITE   = arguments['--rewrite']
    VERBOSE   = arguments['--verbose']
    DEBUG     = arguments['--debug']
    DRYRUN    = arguments['--dry-run']

    if VERBOSE:
        logging.getLogger().setLevel(logging.INFO)
    if DEBUG:
        logging.getLogger().setLevel(logging.DEBUG)

    if scanid:
        timepoint_glob = '{}/nii/{}'.format(datadir, scanid)
    else:
        timepoint_glob = '{}/nii/*'.format(datadir)

    # load the yml of project settings
    with open(ymlfile, 'r') as stream:
        pconfig = yaml.load(stream)

    for path in glob.glob(timepoint_glob):
        subject = os.path.basename(path)

        # skip phantoms
        if 'PHA' in subject:
            logger.info("MSG: qc phantom {}".format(path))
            qc_phantom(path, subject, qcdir, pconfig)
        else:
            logger.info("MSG: qc {}".format(path))
            qc_subject(path, subject, qcdir, pconfig)

if __name__ == "__main__":
    main()

