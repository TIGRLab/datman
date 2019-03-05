#!/usr/bin/env python
"""
Runs MAGeT brain on all participants in the given study and calculates voxel
counts for the regions defined by the labels of the atlases in use.

If run with the init flag, the step up steps will be run automatically (See the
'DATMAN SETUP' section for this, or 'GENERAL SETUP' for projects that will
be privately/manually managed).

Usage:
    dm_proc_maget_brain.py [options] init <study>
    dm_proc_maget_brain.py [options] <study>

Arguments:
    <study>             A datman managed study to run the script on.

Options:
    --config PATH       Use a configuration file other than the default for
                        this project.
    --system STR        A system to use other than the one defined by the
                        DM_SYSTEM environment variable
    --tag TAG           The string used to identify the T1 images to use
                        [default: T1]
    -q, --quiet
    -v, --verbose
    -d, --debug
    -n, --dry-run

GENERAL SETUP:

For set up of MAGeT brain projects that will be datman managed, keep scrolling.
MAGeT brain requires the following before it can be run for the first
time.

    1. In the magetbrain directory 'mb.sh init' must have been run.

    2. Any atlases that are intended to be used must be present in the
        magetbrain/input/atlas folder and must follow the magetbrain naming
        convention described below (things enclosed in <> represent variables).
        It's strongly recommended to choose an odd number of atlases.

            <atlasname>_t1.ext                  For the mandatory T1 file
            <atlasname>_label_<labelname>.ext   For the mandatory label file
                                                (more than one may be used as
                                                long as it follows this
                                                convention)
            <atlasname>_mask.ext                For optional masks.

    3. Template subjects must have been chosen and copied or linked into the
        magetbrain/input/template folder. The official documentation recommends
        about 21 templates and that an odd number of templates always be
        used. These templates must match their naming convention described
        below (things enclosed in <> represent variables).

            <filename>_t1.ext                   Mandatory.
            <filename>_[t2, pd, fa, md].ext     Optional. If present must be
                                                co-registered to the T1 and
                                                the atlas must have the same
                                                contrast.
            <filename>_mask.ext                 Optional.

    4. All subjects to be used should be copied or linked into the
        magetbrain/input/subject folder. Naming convention should match that
        of the templates. If a subject has been chosen to be a template they
        should still be copied into the subject folder.

For additional details / the full documentation see these links (Retrieved
January 18th, 2017):
    https://github.com/CobraLab/antsRegistration-MAGeT
    https://github.com/CobraLab/MAGeTbrain

DATMAN SETUP:
    - Add magetbrain path to paths
    - Add any needed atlases to the atlases folder (if not already present),
      and ensure they match they naming conventions of magetbrain.
    - Add the path to the atlases folder to the global configuration file (if
      not already there) for the system that magetbrain will be run on.


"""
import os
import sys
import glob
import random
import logging

from docopt import docopt

import datman.config
import datman.utils
import datman.scanid

DRYRUN = False

logging.basicConfig(level=logging.WARN,
        format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(os.path.basename(__file__))

def main():
    global DRYRUN
    arguments = docopt(__doc__)
    init = arguments['init']
    study = arguments['<study>']
    config_file = arguments['--config']
    system = arguments['--system']
    tag = arguments['--tag']
    quiet = arguments['--quiet']
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    DRYRUN = arguments['--dry-run']

    if verbose:
        logger.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)
    if quiet:
        logger.setLevel(logging.ERROR)

    config = datman.config.config(filename=config_file, system=system,
                                  study=study)

    maget_config = MagetConfig(config)

    nii_dir = get_nifti_dir(config)
    subject_list = get_subject_list(nii_dir)

    if init:
        init_magetbrain(maget_config, subject_list)
        return

    # Add any new subjects since the last run
    link_subjects(subject_list, maget_config.subject_dir,
                  maget_config.subject_tags)

    run_maget_brain(maget_config.maget_path)

    for result_file in glob.glob(os.path.join(maget_config.results, '*')):
        datmanize_results(maget_config.maget_dir, result_file,
                          maget_config.subject_tags)

def get_nifti_dir(config):
    try:
        nii_dir = config.get_path('nii')
    except KeyError:
        logger.error("'nii' path is not defined for study {}"
                "".format(config.study_name))
        sys.exit(1)
    if not os.path.exists(nii_dir):
        logger.error("{} does not exist. No data to process.".format(nii_dir))
        sys.exit(1)
    return nii_dir

def get_subject_list(source):
    source_regex = os.path.join(source, "*")
    subjects = [folder for folder in glob.glob(source_regex)]
    if not subjects:
        logger.error("No subjects found in directory {}".format(source))
        sys.exit(1)
    return subjects

def init_magetbrain(maget_config, subject_list):
    init_dirs(maget_config.maget_path)
    link_atlases(maget_config.atlases, maget_config.atlas_dir)
    link_subjects(subject_list, maget_config.subject_dir,
                  maget_config.subject_tags)
    link_templates(subject_list, maget_config.num_templates,
                   maget_config.template_dir, maget_config.subject_tags)

def init_dirs(maget_dir):
    if not os.path.exists(maget_dir):
        logger.debug("Making magetbrain directory {}".format(maget_dir))
        os.makedirs(maget_dir)

    command = 'mb.sh init'
    logger.info("Initializing MAGeT brain directories")
    with datman.utils.cd(maget_dir):
        return_code, out = datman.utils.run(command, DRYRUN)

    if return_code:
        if out:
            logger.error("mb.sh output: {}".format(out))
        logger.error("Cannot set up magetbrain project")
        sys.exit(1)

def link_atlases(atlases, atlas_dir):
    logger.info("Linking atlases {} into destination {}".format(atlases,
            atlas_dir))
    for atlas in atlases:
        for source in glob.glob(os.path.join(atlas, '*.nii*')):
            target = get_target_path(source, atlas_dir)
            make_link(source, target)

def get_target_path(source, target_dir):
    filename = os.path.basename(source)
    target = os.path.join(target_dir, filename)
    return target

def make_link(source, target):
    logger.debug("Linking source file {} to target {}".format(source,
                 target))
    if DRYRUN:
        return
    try:
        os.symlink(source, target)
    except OSError as e:
        logger.debug("Failed to make symlink from source {} to target {}. "
                "Reason: {}".format(source, target, e.strerror))

def link_subjects(subject_paths, destination, tag_dict):
    logger.info("Linking new subject data into {}".format(destination))
    for subject_path in subject_paths:
        for series in glob.glob(os.path.join(subject_path, '*.nii*')):
            series_tag = get_series_tag(series)
            maget_tag = get_maget_tag(tag_dict, series_tag)

            if maget_tag is None:
                continue

            maget_tagged_fname = mangle_series_name(series, maget_tag)
            target = os.path.join(destination, maget_tagged_fname)
            if not os.path.exists(target):
                logger.debug("Adding {} to magetbrain subjects data"
                        "".format(series))
                make_link(series, target)

def get_series_tag(series):
    try:
        _, series_tag, _, _ = datman.scanid.parse_filename(series)
    except datman.scanid.ParseException:
        logger.info("{} is not a datman parseable filename. "
                "Ignoring".format(series))
        series_tag = None
    return series_tag

def get_maget_tag(subject_tags, series_tag):
    try:
        maget_tag = subject_tags[series_tag]
    except KeyError:
        # Not a series meant to be imported for magetbrain
        maget_tag = None
    return maget_tag

def mangle_series_name(series, maget_tag):
    file_name = os.path.basename(series)
    ext = datman.utils.get_extension(file_name)
    mangled_name = file_name.replace(ext, '') + '_' + maget_tag + ext
    return mangled_name

def link_templates(subject_list, requested_templates, template_dir,
                   subject_tags):
    num_templates = set_num_templates(requested_templates, len(subject_list))
    logger.info("Selecting and linking {} templates".format(num_templates))
    templates = select_random_subjects(num_templates, subject_list)
    link_subjects(templates, template_dir, subject_tags)

def set_num_templates(requested_num, num_subjects):
    num_templates = requested_num
    if requested_num > num_subjects:
        logger.debug("{} templates requested but only {} subjects.".format(
                requested_num, num_subjects))
        num_templates = num_subjects
    if num_templates % 2 == 0:
        logger.error("Number of templates should be odd, subtracting one to "
                "enforce this.")
        num_templates -= 1
    logger.debug("Using {} templates".format(num_templates))
    return num_templates

def select_random_subjects(num_templates, subject_list):
    choices = []
    for num in xrange(num_templates):
        random_choice = get_unique_random_subject(subject_list, choices)
        choices.append(random_choice)
    return choices

def get_unique_random_subject(subject_list, chosen_subjects):
    random_index = random.randint(0, len(subject_list) - 1)
    while subject_list[random_index] in chosen_subjects:
        # Rechoose, if already picked.
        random_index = random.randint(0, len(subject_list) - 1)
    return subject_list[random_index]

def run_maget_brain(maget_path):
    logger.info("Submitting all MAGeT stages to the queue.")

    command = "mb.sh"
    with datman.utils.cd(maget_path):
        return_code, out = datman.utils.run(command, DRYRUN)

    if return_code:
        logger.error("MAGeT has experienced an error while submitting jobs.")
        if out:
            logger.error("mb.sh output: {}".format(out))
        sys.exit(1)

def datmanize_results(maget_dir, results_file, defined_tags):
    logger.info("Making datman-style named links to results.")
    ident, tag, series, description = dm.scanid.parse_filename(results_file)
    subject_folder = os.path.join(maget_dir, "_".join(
        [ident.study, ident.site, ident.subject, ident.timepoint]))

    if not os.path.exists(subject_folder):
        os.makedirs(subject_folder)

    label = extract_label(results_file)
    if label is None:
        return

    target = get_new_path(ident, description, series, label, defined_tags,
                          subject_folder)
    source = os.path.relpath(results_file, target)
    make_link(source, target)

def extract_label(file_name):
    match = re.match(".*_(label.*\.nii.*)$", file_name)
    try:
        return "_" + match.group(1)
    except:
        logger.error("Output file {} cannot be parsed into datman "
                "style file name.".format(file_name))
        return None

def get_new_path(ident, description, series, label, tag_types, output_folder):
    # Remove the maget_tag for any defined tags
    for tag in tag_types:
        tag = '_' + tag
        untagged = description.replace(tag, "")
    datman_name = dm.scanid.make_filename(ident, tag, series, description,
                                          label)
    return os.path.join(output_folder, datman_name)

class MagetConfig(object):
    def __init__(self, config):
        self.config = config
        self.maget_path = self.__get_magetbrain_path()
        self.datman_atlas_path = self.__get_datman_atlases()
        self.__maget_settings = self.__get_maget_settings()
        self.__atlas_dict = self.__set_atlas_dict()
        self.atlases = self.__set_atlases()
        self.subject_tags = self.get_subject_tags()
        self.num_templates = self.get_number_of_templates()
        self.atlas_dir = os.path.join(self.maget_path, 'input', 'atlas')
        self.subject_dir = os.path.join(self.maget_path, 'input', 'subject')
        self.template_dir = os.path.join(self.maget_path, 'input', 'template')
        self.results = os.path.join(self.maget_path, 'output/labels/majorityvote')

    def __get_magetbrain_path(self):
        try:
            maget_dir = self.config.get_path('magetbrain')
        except KeyError:
            logger.critical("magetbrain path not defined in site config file.")
            sys.exit(1)
        return maget_dir

    def __get_datman_atlases(self):
        try:
            atlas_dir = self.config.get_key('ATLASES')
        except KeyError:
            logger.critical("Cannot find path to atlases for current system.")
            sys.exit(1)
        if not os.path.exists(atlas_dir):
            logger.critical("Datman atlases path {} defined for this system "
                    "does not exist.".format(atlas_dir))
            sys.exit(1)
        return atlas_dir

    def __get_maget_settings(self):
        try:
            maget_config_dict = self.config.get_key('magetbrain')
        except datman.config.UndefinedSetting:
            logger.critical("Magetbrain configuration not defined for study: {}"
                            "".format(self.config.study_name))
            sys.exit(1)
        return maget_config_dict

    def __set_atlas_dict(self):
        try:
            atlas_dict = self.__maget_settings['atlases']
        except KeyError:
            logger.error("No atlases specified in study settings.")
            sys.exit(1)
        return atlas_dict

    def __set_atlases(self):
        atlas_names = self.__atlas_dict.keys()
        atlases = []
        for name in atlas_names:
            atlas_path = os.path.join(self.datman_atlas_path, name)
            if not os.path.exists(atlas_path):
                logger.error("Specified atlas {} cannot be found in atlas "
                        "directory {}".format(name, self.datman_atlas_path))
                sys.exit(1)
            atlases.append(atlas_path)
        return atlases

    def get_atlas(self, atlas_name):
        try:
            settings = self.__atlas_dict[atlas_name]
        except KeyError:
            logger.error("Atlas {} not defined in settings".format(atlas_name))
            return None

        atlas_path = os.path.join(self.datman_atlas_path, atlas_name)
        if not os.path.exists(atlas_path):
            logger.error("Cannot find atlas {} in {}".format(atlas_name,
                         self.datman_atlas_path))
            return None

        return Atlas(atlas_path, atlas_name, settings)

    def get_subject_tags(self):
        try:
            tags = self.__maget_settings['subject_tags']
        except KeyError:
            logger.info("'subject_tags' not defined in {} "
                    "settings. Using default T1 tag 'T1'."\
                    "".format(self.config.study_name))
            tags = {'T1': 't1'}
        if not isinstance(tags, dict):
            logger.error("'subject_tags' for {} must be defined as a "
                    "dictionary mapping between file name tags and expected "
                    "maget brain tags (e.g. t1)".format(self.config.study_name))
            sys.exit(1)
        if 't1' not in tags.values():
            logger.info("Subject tag for mandatory t1 series not defined. "
                    "Using default tag 'T1'.")
            tags['T1'] = 't1'
        return tags

    def get_number_of_templates(self):
        try:
            num = self.__maget_settings['templates']
        except KeyError:
            logger.info("Number of templates not specified. Using default of 21")
            num = 21
        return num

class Atlas(object):
    def __init__(self, atlas_path, atlas_name, settings):
        self.path = atlas_path
        self.name = atlas_name
        self.__output_labels = settings
        self.output_files = self.__output_labels.keys()

    def get_label_info(self, output_type):
        try:
            label_files = self.__output_labels[output_type]
        except KeyError:
            logger.error("No output label file {} defined for atlas {}."
                    "".format(output_type, self.name))
            return {}

        if not isinstance(label_files, list):
            label_files = [label_files]

        labels = {}
        for label_file_name in label_files:
            csv_contents = self._add_labels(label_file_name, labels)
        return labels

    def _add_labels(self, label_csv, labels):
        lines = self._read_csv(label_csv)
        for line in lines:
            fields = self._split_line(line)
            if len(fields) is not 2:
                logger.error("Cannot parse line {} in label csv {}."
                        "".format(line, label_csv))
                continue
            labels[fields[0]] = fields[1]
        return labels

    def _read_csv(self, csv_name):
        csv_path = os.path.join(self.path, csv_name)
        try:
            with open(csv_path, 'r') as label_file:
                lines = label_file.readlines()
        except:
            logger.error("Cannot read labels info from {}".format(csv_path))
            return []
        return lines

    def _split_line(self, line):
        fields = line.split(',')
        return [item.strip() for item in fields]

if __name__ == '__main__':
    main()
