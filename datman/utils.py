"""
A collection of utilities for generally munging imaging data.
"""
import os
import sys
import re
import io
import glob
import zipfile
import tarfile
import logging
import tempfile
import shutil
import shlex
import pipes
import contextlib
import subprocess as proc

import dicom as dcm
import numpy as np
import nibabel as nib
import pyxnat

import datman.config
import datman.scanid as scanid

logger = logging.getLogger(__name__)

def check_checklist(session_name, study=None):
    """Reads the checklist identified from the session_name
    If there is an entry returns the comment, otherwise
    returns None
    """

    try:
        ident = scanid.parse(session_name)
    except scanid.ParseException:
        logger.warning('Invalid session id:{}'.format(session_name))
        return

    if study:
        cfg = datman.config.config(study=study)
    else:
        cfg = datman.config.config(study=session_name)

    try:
        checklist_path = os.path.join(cfg.get_path('meta'),
                                      'checklist.csv')
    except KeyError:
        logger.warning('Unable to identify meta path for study:{}'
                       .format(cfg.study_name))
        return

    try:
        with open(checklist_path, 'r') as f:
            lines = f.readlines()
    except IOError:
        logger.warning('Unable to open checklist file:{} for reading'
                       .format(checklist_path))
        return

    for line in lines:
        parts = line.split(None, 1)
        if parts:  # fix for empty lines
            if os.path.splitext(parts[0])[0] == 'qc_{}'.format(session_name):
                try:
                    return parts[1].strip()
                except IndexError:
                    return ''

    return None

def check_blacklist(scan_name, study=None):
    """Reads the checklist identified from the session_name
    If there is an entry returns the comment, otherwise
    returns None
    """

    try:
        ident, tag, series_num, _ = scanid.parse_filename(scan_name)
        blacklist_id = "_".join([str(ident), tag, series_num])
    except scanid.ParseException:
        logger.warning('Invalid session id:{}'.format(scan_name))
        return

    if study:
        cfg = datman.config.config(study=study)
    else:
        cfg = datman.config.config(study=ident.get_full_subjectid_with_timepoint())

    try:
        checklist_path = os.path.join(cfg.get_path('meta'),
                                      'blacklist.csv')
    except KeyError:
        logger.warning('Unable to identify meta path for study:{}'
                       .format(study))
        return

    try:
        with open(checklist_path, 'r') as f:
            lines = f.readlines()
    except IOError:
        logger.warning('Unable to open blacklist file:{} for reading'
                       .format(checklist_path))
        return
    for line in lines:
        parts = line.split(None, 1)
        if parts:  # fix for empty lines
            if blacklist_id in parts[0]:
                try:
                    return parts[1].strip()
                except IndexError:
                    return


def get_subject_from_filename(filename):
    filename = os.path.basename(filename)
    filename = filename.split('_')[0:5]
    filename = '_'.join(filename)

    return filename


def script_path():
    """
    Returns the full path to the executing script.
    """
    return os.path.abspath(os.path.dirname(sys.argv[0]))

def guess_tag(description, tagmap):
    """
    Given a series description return a list of series tags this might be.

    By "series tag" we mean a short code like T1, DTI, etc.. that indicates
    more generally what the data is (usually the DICOM header
    SeriesDescription).

    <tagmap> is a dictionary that maps a regex to a series tag, where the regex
    matches the series description dicom header. If not specified this modules
    SERIES_TAGS_MAP is used.
    """
    matches = list(set(
        [tag for p,tag in tagmap.iteritems() if re.search(p,description)]
        ))
    if len(matches) == 0: return None
    if len(matches) == 1: return matches[0]
    return matches

def mangle_basename(base_path):
    """
    strip off final slash to get the appropriate basename if necessary.
    """
    base_path = os.path.normpath(base_path)
    base = os.path.basename(base_path).lower()

    return base

def mangle(string):
    """Mangles a string to conform with the naming scheme.

    Mangling is roughly: convert runs of non-alphanumeric characters to a dash.

    Does not convert '.' to avoid accidentally mangling extensions and does
    not convert '+'
    """
    if not string:
        string = ""
    return re.sub(r"[^a-zA-Z0-9.+]+","-",string)

def get_extension(path):
    """
    Get the filename extension on this path.

    This is a slightly more sophisticated version of os.path.splitext in that
    this will correctly return the extension for '.tar.gz' files, for example.
    :D
    """
    if path.endswith('.tar.gz'):
        return '.tar.gz'
    if path.endswith('.nii.gz'):
        return '.nii.gz'
    else:
        return os.path.splitext(path)[1]

def get_archive_headers(path, stop_after_first = False):
    """
    Get dicom headers from a scan archive.

    Path can be a path to a tarball or zip of dicom folders, or a folder. It is
    assumed that this archive contains the dicoms from a single exam, organized
    into folders for each series.

    The entire archive is scanned and dicom headers from a single file in each
    folder are returned as a dictionary that maps path->headers.

    If stop_after_first == True only a single set of dicom headers are
    returned for the entire archive, which is useful if you only care about the
    exam details.
    """
    if os.path.isdir(path):
        return get_folder_headers(path, stop_after_first)
    elif zipfile.is_zipfile(path):
        return get_zipfile_headers(path, stop_after_first)
    elif os.path.isfile(path) and path.endswith('.tar.gz'):
        return get_tarfile_headers(path, stop_after_first)
    else:
        raise Exception("{} must be a file (zip/tar) or folder.".format(path))

def get_tarfile_headers(path, stop_after_first = False):
    """
    Get headers for dicom files within a tarball
    """
    tar = tarfile.open(path)
    members = tar.getmembers()

    manifest = {}
    # for each dir, we want to inspect files inside of it until we find a dicom
    # file that has header information
    for f in filter(lambda x: x.isfile(), members):
        dirname = os.path.dirname(f.name)
        if dirname in manifest: continue
        try:
            manifest[dirname] = dcm.read_file(tar.extractfile(f))
            if stop_after_first: break
        except dcm.filereader.InvalidDicomError as e:
            continue
    return manifest

def get_zipfile_headers(path, stop_after_first = False):
    """
    Get headers for a dicom file within a zipfile
    """
    zf = zipfile.ZipFile(path)

    manifest = {}
    for f in zf.namelist():
        dirname = os.path.dirname(f)
        if dirname in manifest: continue
        try:
            manifest[dirname] = dcm.read_file(io.BytesIO(zf.read(f)))
            if stop_after_first: break
        except dcm.filereader.InvalidDicomError as e:
            continue
        except zipfile.BadZipfile:
            logger.warning('Error in zipfile:{}'
                           .format(path))
            break
    return manifest

def get_folder_headers(path, stop_after_first = False):
    """
    Generate a dictionary of subfolders and dicom headers.
    """

    manifest = {}

    # for each dir, we want to inspect files inside of it until we find a dicom
    # file that has header information
    subdirs = []
    for filename in os.listdir(path):
        filepath = os.path.join(path,filename)
        try:
            if os.path.isdir(filepath):
                subdirs.append(filepath)
                continue
            manifest[path] = dcm.read_file(filepath)
            break
        except dcm.filereader.InvalidDicomError as e:
            pass

    if stop_after_first: return manifest

    # recurse
    for subdir in subdirs:
        manifest.update(get_folder_headers(subdir, stop_after_first))
    return manifest

def get_all_headers_in_folder(path, recurse = False):
    """
    Get DICOM headers for all files in the given path.

    Returns a dictionary mapping path->headers for *all* files (headers == None
    for files that are not dicoms).
    """

    manifest = {}
    for dirname, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirname,filename)
            headers = None
            try:
                headers = dcm.read_file(filepath)
            except dcm.filereader.InvalidDicomError as e:
                continue
            manifest[filepath] = headers
        if not recurse: break
    return manifest

def col(arr, colname):
    """
    Return the named column of an ndarray.

    Column names are given by the first row in the ndarray
    """
    idx = np.where(arr[0,] == colname)[0]
    return arr[1:,idx][:,0]

def subject_type(subject):
    """
    Uses subject naming to determine what kind of files we are looking at. If
    we find a strangely-named subject, we return None.

    TO DEPRICATE.
    """
    try:
        subject = subject.split('_')

        if subject[2] == 'PHA':
            return 'phantom'
        elif subject[2] != 'PHA' and subject[2][0] == 'P':
            return 'humanphantom'
        elif str.isdigit(subject[2]) == True and len(subject[2]) == 4:
            return 'subject'
        else:
            return None

    except:
        return None

def get_subjects(path):
    """
    Finds all of the subject folders in the supplied directory, and returns
    their basenames.
    """
    subjects = filter(os.path.isdir, glob.glob(os.path.join(path, '*')))
    for i, subj in enumerate(subjects):
        subjects[i] = os.path.basename(subj)
    subjects.sort()

    return subjects

def get_phantoms(path):
    """
    Finds all of the phantom folders in the supplied directory, and returns
    their basenames.
    """
    phantoms = []
    subjects = get_subjects(path)
    for subject in subjects:
        subjtype = subject_type(subject)
        if subjtype == 'phantom':
            phantoms.append(subject)

    return phantoms

def get_xnat_catalog(data_path, subject):
    """
    For a given subject, finds and returns all of the xml files as full
    paths. In almost all cases, this will be a single catalog.


    THIS IS BROKEN.
    """
    dicoms = os.listdir(os.path.join(data_path, 'dicom'))
    subjects = filter(lambda x: subject in x, dicoms)

    catalogs = []

    for subject in subjects:
        folders = os.listdir(os.path.join(data_path, 'dicom', subject))
        folders.sort()
        files = os.listdir(os.path.join(data_path, 'dicom', subject, folders[0]))
        files = filter(lambda x: '.xml' in x, files)
        catalogs.append(os.path.join(data_path, 'dicom', subject, folders[0], files[0]))

    catalogs.sort()

    return catalogs

def define_folder(path):
    """
    Sets a variable to be the path to a folder. Also, if the folder does not
    exist, this makes it so, unless we lack the permissions to do so, which
    leads to a graceful exit.
    """
    if not os.path.isdir(path):
        try:
            os.makedirs(path)
        except OSError as e:
            logger.error('failed to make directory {}'.format(path))
            raise(e)

    if not has_permissions(path):
        raise OSError("User does not have permission to access {}".format(path))

    return path

def has_permissions(path):
    """
    Checks for write access to submitted path.
    """
    if os.access(path, 7) == True:
        flag = True
    else:
        logger.error('You do not have write access to path {}'.format(path))
        flag = False

    return flag

def make_epitome_folders(path, n_runs):
    """
    Makes an epitome-compatible folder structure with functional data FUNC of n
    import pipesruns, and a single T1.

    This works assuming we've run everything through freesurfer.

    If we need multisession, it might make sense to run this multiple times
    (once per session).
    """
    run('mkdir -p ' + path + '/TEMP/SUBJ/T1/SESS01/RUN01')
    for r in np.arange(n_runs)+1:
        num = "{:0>2}".format(str(r))
        run('mkdir -p ' + path + '/TEMP/SUBJ/FUNC/SESS01/RUN' + num)

def run_dummy_q(list_of_names):
    """
    This holds the script until all of the queued items are done.
    """
    logger.info('Holding for remaining processes.')
    opts = 'h_vmem=3G,mem_free=3G,virtual_free=3G'
    holds = ",".join(list_of_names)
    cmd = 'qsub -sync y -hold_jid {} -l {} -b y echo'.format(holds, opts)
    run(cmd)
    logger.info('... Done.')

def run(cmd, dryrun=False, specialquote=True, verbose=True):
    """
    Runs the command in default shell, returning STDOUT and a return code.
    The return code uses the python convention of 0 for success, non-zero for
    failure
    """
    # Popen needs a string command.
    if isinstance(cmd, list):
        cmd = " ".join(cmd)

    # perform shell quoting for special characters in filenames
    if specialquote:
        cmd = _escape_shell_chars(cmd)

    if dryrun:
        logger.info("Performing dry-run. Skipped command: {}".format(cmd))
        return 0, ''

    logger.debug("Executing command: {}".format(cmd))

    p = proc.Popen(cmd, shell=True, stdout=proc.PIPE, stderr=proc.PIPE)
    out, err = p.communicate()

    if p.returncode and verbose:
        logger.error('run({}) failed with returncode {}. STDERR: {}'
                     .format(cmd, p.returncode, err))

    return p.returncode, out


def _escape_shell_chars(arg):
    """
    An attempt to sanitize shell arguments without disabling
    shell expansion.

    >>> _escape_shell_chars('This (; file has funky chars')
    'This \\(\\; file has funky chars'
    """
    arg = arg.replace('(', '\\(')
    arg = arg.replace(';', '\\;')
    arg = arg.replace(')', '\\)')

    return(arg)


def get_files_with_tag(parentdir, tag, fuzzy = False):
    """
    Returns a list of files that have the specified tag.

    Filenames must conform to the datman naming convention (see
    scanid.parse_filename) in order to be considered.

    If fuzzy == True, then filenames are matched if the given tag is found
    within the filename's tag.
    """

    files = []
    for f in os.listdir(parentdir):
        try:
            _, filetag, _, _ = scanid.parse_filename(f)
            if tag == filetag or (fuzzy and tag in filetag):
                files.append(os.path.join(parentdir,f))
        except scanid.ParseException:
            continue

    return files

def makedirs(path):
    """
    Make the directory (including parent directories) if they don't exist
    """
    if not os.path.exists(path):
        os.makedirs(path)

def loadnii(filename):
    """
    Usage:
        nifti, affine, header, dims = loadnii(filename)

    Loads a Nifti file (3 or 4 dimensions).

    Returns:
        a 2D matrix of voxels x timepoints,
        the input file affine transform,
        the input file header,
        and input file dimensions.
    """

    # load everything in
    nifti = nib.load(filename)
    affine = nifti.get_affine()
    header = nifti.get_header()
    dims = nifti.shape

    # if smaller than 3D
    if len(dims) < 3:
        raise Exception('Your data has less than 3 dimensions!')

    # if smaller than 4D
    if len(dims) > 4:
        raise Exception('Your data is at least a penteract (> 4 dimensions!)')

    # load in nifti and reshape to 2D
    nifti = nifti.get_data()
    if len(dims) == 3:
        dims = tuple(list(dims) + [1])
    nifti = nifti.reshape(dims[0]*dims[1]*dims[2], dims[3])

    return nifti, affine, header, dims

def check_returncode(returncode):
    if returncode != 0:
        raise ValueError

def get_loaded_modules():
    """Returns a space separated list of loaded modules

    These are modules loaded by the environment-modules system. This function
    just looks in the LOADEDMODULES environment variable for the list.
    """
    return " ".join(os.environ.get("LOADEDMODULES","").split(":"))

def splitext(path):
    """
    Function that will remove extension, including specially-defined extensions
    that fool os.path.splitext
    """
    for ext in ['.nii.gz', '.mnc.gz']:
        if path.endswith(ext):
            return path[:-len(ext)], path[-len(ext):]
    return os.path.splitext(path)

@contextlib.contextmanager
def make_temp_directory(suffix='', prefix='tmp', path=None):
    temp_dir = tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=path)
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir)

def remove_empty_files(path):
    for root, dirs, files in os.walk(path):
        for f in files:
            filename = os.path.join(root, f)
            if os.path.getsize(filename) == 0:
                os.remove(filename)

def nifti_basename(fpath):
    """
    return basename without extension (either .nii.gz or .nii)
    """
    basefpath = os.path.basename(fpath)
    stem = basefpath.replace('.nii','').replace('.gz', '')

    return(stem)

def filter_niftis(candidates):
    """
    Takes a list and returns all items that contain the extensions '.nii' or '.nii.gz'.
    """
    candidates = filter(lambda x: 'nii.gz' == '.'.join(x.split('.')[1:]) or
                                     'nii' == '.'.join(x.split('.')[1:]), candidates)

    return candidates

def split_path(path):
    """
    Splits a path into all the component parts, returns a list

    >>> split_path('a/b/c/d.txt')
    ['a', 'b', 'c', 'd.txt']
    """
    dirname = path
    path_split = []
    while True:
        dirname, leaf = os.path.split(dirname)
        if (leaf):
            path_split = [leaf] + path_split
        else:
            break
    return(path_split)

class cd(object):
    """
    A context manager for changing directory. Since best practices dictate
    returning to the original directory, saves the original directory and
    returns to it after the block has exited.

    May raise OSError if the given path doesn't exist (or the current directory
    is deleted before switching back)
    """

    def __init__(self, path):
        user_path = os.path.expanduser(path)
        self.new_path = os.path.expandvars(user_path)

    def __enter__(self):
        self.old_path = os.getcwd()
        os.chdir(self.new_path)

    def __exit__(self, e, value, traceback):
        os.chdir(self.old_path)

class XNATConnection(object):
    def __init__(self,  xnat_url, user_name, password):
        self.server = xnat_url
        self.user = user_name
        self.password = password

    def __enter__(self):
        self.connection = pyxnat.Interface(server=self.server, user=self.user,
                password=self.password)
        return self.connection

    def __exit__(self, type, value, traceback):
        self.connection.disconnect()

def get_xnat_credentials(config, xnat_cred):
    if not xnat_cred:
        xnat_cred = os.path.join(config.get_path('meta'), 'xnat-credentials')

    logger.debug("Retrieving xnat credentials from {}".format(xnat_cred))
    try:
        credentials = read_credentials(xnat_cred)
        user_name = credentials[0]
        password = credentials[1]
    except IndexError:
        logger.error("XNAT credential file {} is missing the user name or " \
                "password.".format(xnat_cred))
        sys.exit(1)
    return user_name, password

def read_credentials(cred_file):
    credentials = []
    try:
        with open(cred_file, 'r') as creds:
            for line in creds:
                credentials.append(line.strip('\n'))
    except:
        logger.error("Cannot read credential file or file does not exist: " \
                "{}.".format(cred_file))
        sys.exit(1)
    return credentials

def get_relative_source(source, target):
    if os.path.isfile(source):
        source_file = os.path.basename(source)
        source = os.path.dirname(source)
    else:
        source_file = ''

    rel_source_dir = os.path.relpath(source, os.path.dirname(target))
    rel_source = os.path.join(rel_source_dir, source_file)
    return rel_source

def check_dependency_configured(program_name, shell_cmd=None, env_vars=None):
    """
    <program_name>      Name to add to the exception message if the program is
                        not correctly configured.
    <shell_cmd>         A command line command that will be put into 'which', to
                        check whether the shell can find it.
    <env_vars>          A list of shell variables that are expected to be set.
                        Doesnt verify the value of these vars, only that they are
                        all set.

    Raises EnvironmentError if the command is not findable or if any environment
    variable isnt configured.
    """
    message = ("{} required but not found. Please check that "
            "it is installed and correctly configured.".format(program_name))

    if shell_cmd is not None:
        return_val, found = run('which {}'.format(shell_cmd))
        if return_val or not found:
            raise EnvironmentError(message)

    if env_vars is None:
        return

    if not isinstance(env_vars, list):
        env_vars = [env_vars]

    try:
        for variable in env_vars:
            os.environ[variable]
    except KeyError:
        raise EnvironmentError(message)

def validate_subject_id(subject_id, config):
    """
    Checks that a given subject id
        a) Matches the datman convention
        b) Matches a study tag that is defined in the configuration file for
           the current study
        c) Matches a site that is defined for the given study tag

    If all validation checks pass, will return a datman scanid instance. This
    can be ignored if the validation is all that's wanted.
    """
    try:
        scanid = datman.scanid.parse(subject_id)
    except datman.scanid.ParseException:
        raise RuntimeError("Subject id {} does not match datman"
                " convention".format(subject_id))

    valid_tags = config.get_study_tags()

    try:
        sites = valid_tags[scanid.study]
    except KeyError:
        raise RuntimeError("Subject id {} has undefined study code {}".format(
                subject_id, scanid.study))

    if scanid.site not in sites:
        raise RuntimeError("Subject id {} has undefined site {} for study {}".format(
                subject_id, scanid.site, scanid.study))

    return scanid

def submit_job(cmd, job_name, log_dir, system = 'other',
        cpu_cores=1, walltime="2:00:00", dryrun = False):
    '''
    submits a job or joblist the queue depending on the system

    Args:
        cmd (str): the command or a list of commands to submits
        job_name (str): the name for the job
        log_dir (path): paths where the job logs should go
        system : the system that we are running on (i.e. 'kimel' or 'scc')
        cpu_cores (int): the number of CPU cores (default: 1) for the job (on scc)
        walltime  (time) : the walltime for the job (default 2:00:00, two hrs)
        dryrun (bool): do not submit the job
    '''
    if dryrun:
        return

    # Bit of an ugly hack to allow job submission on the scc. Should be replaced
    # with drmaa or some other queue interface later
    if system is 'kimel':
        job_file = '/tmp/{}'.format(job_name)

        with open(job_file, 'wb') as fid:
            fid.write('#!/bin/bash\n')
            fid.write(cmd)
        job = "qsub -V -q main.q -N {} {}".format(job_name, job_file)
        rtn, out = run(job)
    else:
        job = "echo {} | qbatch -N {} --logdir {} --ppj {} -i -c 1 -j 1 --walltime {} -".format(
                cmd, job_name, log_dir, cpu_cores, walltime)
        rtn, out = run(job, specialquote=False)

    if rtn:
        logger.error("Job submission failed.")
        if out:
            logger.error("stdout: {}".format(out))
        sys.exit(1)

def get_resources(open_zipfile):
    # filter dirs
    files = open_zipfile.namelist()
    files = filter(lambda f: not f.endswith('/'), files)

    # filter files named like dicoms
    files = filter(lambda f: not is_named_like_a_dicom(f), files)

    # filter actual dicoms :D.
    resource_files = []
    for f in files:
        try:
            if not is_dicom(io.BytesIO(open_zipfile.read(f))):
                resource_files.append(f)
        except zipfile.BadZipfile:
            logger.error('Error in zipfile:{}'.format(f))
    return resource_files

def is_named_like_a_dicom(path):
    dcm_exts = ('dcm', 'img')
    return any(map(lambda x: path.lower().endswith(x), dcm_exts))

def is_dicom(fileobj):
    try:
        dcm.read_file(fileobj)
        return True
    except dcm.filereader.InvalidDicomError:
        return False

def make_zip(source_dir, dest_zip):
    # Can't use shutil.make_archive here because for python 2.7 it fails on
    # large zip files (seemingly > 2GB) and zips with more than about 65000 files
    # Soooo, doing it the hard way. Can change this if we ever move to 3
    with ZipFile(dest_zip, "w", compression=ZIP_DEFLATED,
            allowZip64=True) as zip_handle:
        # We want this to use 'w' flag, since it should overwrite any existing zip
        # of the same name. If the script made it this far, that zip is incomplete
        for current_dir, folders, files in os.walk(source_dir):
            for item in files:
                item_path = os.path.join(current_dir, item)
                archive_path = item_path.replace(source_dir + "/", "")
                zip_handle.write(item_path, archive_path)

# vim: ts=4 sw=4 sts=4:
