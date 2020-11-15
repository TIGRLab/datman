#!/usr/bin/env python
"""
This copies and converts files in nii folder to a bids folder in BIDS format

Usage:
  bidsify.py [options] [-s <SUBJECT>]... <study>

Arguments:
    <study>                     Study name defined in master configuration
                                .yml file to convert to BIDS format

Options:
    -s SUBID, --subject SUBID   Can repeat multiple times for multiple subjects
    -b PATH, --bids-dir PATH    Path to directory to store data in BIDS format
    -y PATH, --yaml PATH        YAML path for BIDS specification constraints
    -r, --rewrite               Overwrite existing BIDS outputs
    --debug                     Debug logging

Info on FMAP matching algorithm:

    The one key assumption bidsify makes is that pairing fmaps
    are collected sequentially in order. If order is
    non-sequential then algorithm will crash. A more sophisticated routine
    will be needed.
"""

import os
import json
import glob
from shutil import copyfile
import logging
from string import Template

from docopt import docopt

import datman.config as config
import datman.scanid as scanid
import datman.scan as scan
import datman.dashboard as dashboard

from datman.bids.check_bids import BIDSEnforcer

from collections import namedtuple
from itertools import groupby, product
from operator import attrgetter

# Set up logger
logging.basicConfig(level=logging.WARN,
                    format="[% (name)s % (levelname)s:"
                    "%(message)s]")
logger = logging.getLogger(os.path.basename(__file__))
YAML = os.path.abspath(
    os.path.join(os.path.dirname(__file__),
                 "../assets/bids/requirements.yaml"))


class BIDSFile(object):

    # Store and compute on information required to generate a BIDS file
    def __init__(self, sub, ses, series, dest_dir, bids_prefix, bids_spec):

        # Grab description of file and associated BIDS description
        self.sub = sub
        self.ses = ses
        self.series = series
        self.dest_dir = dest_dir
        self.bids = bids_prefix
        self.spec = bids_spec
        self.path = ""

        # Store JSON meta-data in cache for manipulation
        meta_json = get_json(series.path)
        self.json = self._load_json(meta_json)

    def __repr__(self):
        return self.bids

    @property
    def datman(self):
        return self.series.full_id

    @property
    def series_num(self):
        return int(self.series.series_num)

    @property
    def source(self):
        if not self.path:
            return self.series.path
        else:
            return self.path

    @source.setter
    def source(self, path):
        self.path = path

    @property
    def bids_type(self):
        return self.get_spec("class")

    @property
    def subject(self):
        return self.sub

    @property
    def session(self):
        return "ses-" + self.ses

    @property
    def rel_path(self):
        return os.path.join(self.session, self.bids_type,
                            self.bids + ".nii.gz")

    @property
    def dest_nii(self):
        return os.path.join(self.dest_dir, self.bids + ".nii.gz")

    def copy(self):
        """
        Create an identical instance
        """

        return BIDSFile(self.sub, self.ses, self.series, self.dest_dir,
                        self.bids, self.spec)

    def transfer_files(self):
        """
        Perform data transformation from DATMAN into BIDS
        """

        # Make destination directory
        os.makedirs(self.dest_dir, exist_ok=True)

        # Copy over NIFTI file and transform into BIDS name
        copyfile(self.source, self.dest_nii)

        # Write JSON file
        json_destination = os.path.join(self.dest_dir, self.bids + ".json")
        with open(json_destination, "w") as j:
            json.dump(self.json, j, indent=3)

        # For diffusion data you need to copy over bvecs and bvals
        if self.bids_type == "dwi":
            for b in [".bval", ".bvec"]:
                src = self.source.replace(".nii.gz", b)
                dst = os.path.join(self.dest_dir, self.bids + b)

                try:
                    copyfile(src, dst)
                except IOError:
                    logger.error("Cannot find file {}".format(src))
        return

    def update_source(self, cfg, be):
        """
        If for a particular file the BIDS specification indicates an
        alternative source path then update it to match
        """

        try:
            alt = self.get_spec("alt")
        except KeyError:
            return self

        logger.info("Preferred derivative of {} exists!".format(self.source))
        logger.info("Updating source file information...")

        # Specification of template inputs
        template_dict = {"subject": self.datman, "series": self.series_num}

        # Process each alternative
        alts = []
        for d in alt:
            '''
            Allow "self" to propogate itself if the tag itself
            in addition its derivatives need to be converted into BIDS
            i.e SBRef for registration and SBRef for TOPUP
            '''
            if d.get('type') == self.series.tag:
                alts.append(self)
                continue

            alt_template = Template(d["template"]).substitute(template_dict)
            alt_type = d["type"]
            match_file = glob.glob("{proj}/{template}".format(
                proj=cfg.get_study_base(), template=alt_template))

            try:
                new_source = match_file[0]
            except IndexError:
                logger.info(f"Could not find derivative for {self}!")
                continue

            # Produce copy of self
            derivsfile = self.copy()

            # Get bids specification for file and assign to copy
            new_spec = {
                **get_tag_bids_spec(cfg, alt_type),
                **d.get("inherit", {})
            }
            derivsfile.spec = new_spec

            # Update with additional subject/session metadata
            new_spec.update({"sub": self.sub, "ses": self.ses})

            # Construct name
            new_bids = be.construct_bids_name(new_spec)

            # Update pathing and name as well as JSON file sidecar
            new_json = new_source.replace(".nii.gz", ".json")
            derivsfile.source = new_source
            derivsfile.bids = new_bids
            derivsfile.json = derivsfile._load_json(new_json)
            derivsfile.dest_dir = os.path.abspath(
                os.path.join(derivsfile.dest_dir, os.pardir,
                             derivsfile.spec['class']))

            alts.append(derivsfile)

        return alts

    def _load_json(self, meta_json):

        try:
            with open(meta_json, "r") as jfile:
                j = json.load(jfile)
        except IOError:
            logger.error("Missing JSON for {}".format(self.source))
            j = {}
        except ValueError:
            logger.error("JSON file for {} is invalid!".format(self.source))
            j = {}

        return j

    def add_json_list(self, spec, value):
        """
        To internal dictionary add a list type json value to spec
        If non-existant make a new list, otherwise append to current
        """

        try:
            self.json[spec].append(value)
        except KeyError:
            self.json[spec] = [value]
        return

    def get_spec(self, *args, return_default=False, default=None):
        """
        Iteratively enter dictionary by sequence of keys in order
        """

        tmp = self.spec
        try:
            for a in args:
                tmp = tmp[a]
        except KeyError:
            if not return_default:
                raise
            else:
                return default

        return tmp

    def is_spec(self, *args):

        try:
            self.get_spec(*args)
        except KeyError:
            return False
        else:
            return True


# SCRIPT DEFINITIONS


def make_directory(path, suppress=False):

    try:
        os.mkdir(path)
    except OSError:
        logger.info("Pre-existing folder {}. "
                    "Skipping folder creation".format(path))

    return


def sort_by_series(scans_list):
    """
    Sort scans by their series number
    """

    sorted_scans = sorted(scans_list, key=lambda s: s.series_num)
    seen = []

    def unique(series):
        if (series.tag, series.series_num) not in seen:
            seen.append((series.tag, series.series_num))
            return series

    return filter(unique, sorted_scans)


def get_json(nifti_path):
    """
    Get associated JSON of input file
    """
    return nifti_path.replace(".nii.gz", ".json").replace(".nii", ".json")


def get_tag_bids_spec(cfg, tag):
    """
    Retrieve the BIDS specifications for a Tag defined in datman config
    """

    # Copy is being used here since python passes by reference and any
    # downstream updates modify the original data which is bad
    try:
        bids = cfg.system_config["ExportSettings"][tag]["bids"].copy()
    except KeyError:
        logger.error("No BIDS tag available for scan type:"
                     "{}, skipping conversion".format(tag))
        return None

    return bids


def pair_fmaps(series_list):
    """
    Pairing heuristic for associating fieldmaps with each other

    Method:
        For each BIDSFile get the pairing key and the associated values allowed
        When another file with an associated value is found, get the
        intersection of the allowed values
        This yields the left over requirements that needs to be fulfilled
        If the other file is not matching (case of lone TOPUP) then a mismatch
        results in a lone fmap

    """
    def pair_on(x):
        return x.get_spec("pair", "label")

    def pair_with(x):
        return set(x.get_spec("pair", "with"))

    pair_list = []
    lone = []
    stored = []
    pairs2go = []
    for s in series_list:

        # If fmap is not intended to be paired
        if not s.is_spec("pair"):
            lone.append(s)
            continue

        # Get the image if nothing is being used as a comparator
        if not stored:
            stored = s
            pairs2go = pair_with(s)
            pair_spec = pair_on(s)
            pairs = [s]
            continue

        # If stored is available then in the next fmap type check!
        try:
            pairing_val = s.get_spec(pair_spec)
        except KeyError:
            logger.error("Mismatch of fieldmap types breaking key assumption!")
            logger.error("This functionality is not yet supported!")
            raise

        # If match then add on and intersect to cut down requirements list
        if pairing_val in pairs2go:
            pairs.append(s)
            pairs2go = pairs2go & pair_with(s)

            # If after intersection pairs2go is empty that means no more
            # matches required for set of fmaps
            if not pairs2go:
                pair_list.append(pairs)
                pairs = []
                stored = None
        # Otherwise it's a lonely fmap, use next as comparator
        else:
            lone.append([stored])
            stored = s

    # Residuals loners go here
    if stored is not None:
        lone.append([stored])

    pair_list.extend(lone)
    return pair_list


def get_first_series(series_list):
    """
    For each iterable of BIDSFiles calculate the average series number
    """

    return min(series_list, key=lambda x: x.series_num).series_num


def is_fieldmap_candidate(scan, scan_type):
    """
    Given a candidate scan, check whether it is of the correct type and is
    meant to be corrected
    """

    # First check if meant for fieldmaps
    try:
        use_fieldmaps = scan.get_spec("fieldmaps")
    except KeyError:
        use_fieldmaps = True

    match_type = scan.bids_type in scan_type

    if use_fieldmaps and match_type:
        return True
    else:
        return False


def process_intended_fors(grouped_fmaps, non_fmaps):
    """
    Derive intended fors using series value matching

    Considerations:
        1. When matching should first scrape the kind of data you can
        apply fmaps to
        2. Then loop through acquisitions
        3. Filter scans
        4. Calculate distances and minimizes
        5. Done

    Patch 2020-11-12
    ------------------------
    Naive minimization of the series metric may result in
    EPIs meant to be grouped together to be associated with
    different fmaps.

    To remove this bug while maintaining bidirectional matching
    of fmaps the candidate scans are chunked based on their containment within
    2 pairs of fmaps of a (acq, intended_for) tuple and assigned their
    min(series) key for matching.

    """

    EpiChunk = namedtuple("EpiChunk", ['series', 'chunk'])

    def chunk_epis(epis, series_blocks):
        '''
        Implement chunking with series_blocks as
        bounds for each chunk
        '''

        # Loop through series blocks and chunk
        chunks = []
        edges = [0, *series_blocks, 1e10]
        for i in range(0, len(edges) - 1):

            chunk = [
                e for e in epis
                if e.series_num >= edges[i] and e.series_num < edges[i + 1]
            ]

            if chunk:
                min_ser = min(chunk, key=lambda x: x.series_num)
                chunks.append(EpiChunk(min_ser.series_num, chunk))

        return chunks

    # For each acq/intended tuple
    series_list = non_fmaps
    for g, l in grouped_fmaps:

        candidate_fmaps = list(l)
        intended_for = g.intended_for

        # Get candidate list of scans to match on
        candidate_scans = [
            s for s in non_fmaps if is_fieldmap_candidate(s, intended_for)
        ]

        # 2020-11-12 patch
        cfmaps_sers = [get_first_series(f) for f in candidate_fmaps]
        chunks = chunk_epis(candidate_scans, cfmaps_sers)

        # Minimize over chunks
        for c in chunks:

            # Calc dists and get minimum index
            dists = [abs(f - c.series) for f in cfmaps_sers]
            min_ind = dists.index(min(dists))

            # Add each scan in chunk to each grouped fmap
            [
                f.add_json_list("IntendedFor", s.rel_path)
                for f, s in product(candidate_fmaps[min_ind], c.chunk)
            ]

        # Add processed fmaps to series list
        series_list += [i for k in candidate_fmaps for i in k]

    return series_list


def prepare_fieldmaps(series_list):
    """
    Args:
        series_list                     A list of BIDSFile objects
        be                              BIDSEnforcer object

    Method:
    1. Pull fmaps by class key
    2. Pair fmaps using pair key
    3. Assign fmaps using series

    """

    Fmap_ID = namedtuple('Fmap_ID', ['acq', 'intended_for'])

    def group_fmaps(x):
        '''
        Returns unique grouping keys for fieldmaps

        Rule:
        If fieldmaps share the same intended for, then we
        differentiate their application based on their acquisition
        parameter. This allows us to collect multiple fieldmap types
        for a single given sequence/set of sequences.
        '''
        return Fmap_ID(x.get_spec('acq', return_default=True, default=''),
                       x.get_spec('intended_for'))

    # Filter out non_fmap files
    fmaps = [s for s in series_list if s.bids_type == "fmap"]

    if not fmaps:
        return series_list

    non_fmaps = [s for s in series_list if s.bids_type != "fmap"]

    # Pair up fmaps
    pair_list = pair_fmaps(fmaps)
    pair_list.sort(key=lambda x: group_fmaps(x[0]))

    # Split fmaps based on type
    groupings = groupby(pair_list, lambda x: group_fmaps(x[0]))
    series_list = process_intended_fors(groupings, non_fmaps)

    return series_list


def make_bids_template(bids_dir, subject, session):
    """
    Set up folders for making BIDS directory
    Arguments:
        bids_dir                    Directory to create BIDS project in
                                    (project-level directory)
        study_name                  Study code for dataset_description
        subject                     BIDS subject ID
        session                     BIDS session ID

    Return:
        p_bids_sub_ses              Path to BIDS subject-session
                                    specific directory
    """

    p_bids_sub = os.path.join(bids_dir, subject)
    make_directory(p_bids_sub)

    p_bids_sub_ses = os.path.join(bids_dir, subject, session)
    make_directory(p_bids_sub_ses)

    return p_bids_sub_ses


def make_dataset_description(bids_dir, study_name, version):
    """
    Make boilerplate dataset_description.json file
    """

    make_directory(bids_dir)

    # Should be separate functionality
    p_dataset_desc = os.path.join(bids_dir, "dataset_description.json")
    if not os.path.isfile(p_dataset_desc):
        with open(p_dataset_desc, "w") as f:
            json.dump({
                "Name": study_name,
                "BIDSVersion": version
            },
                      f,
                      indent=3)

    return


def prioritize_scans(series_list):
    """
    Given a list of scans apply prioritization heuristics
    based on spec key "over"
    """

    to_filt = set()
    for s in series_list:

        try:
            label = s.get_spec("over", "label")
            on = s.get_spec("over", "value")
        except KeyError:
            continue

        # If prioritization spec found,
        # then look for it in other scans to replace
        for f in [k for k in series_list if k != s]:
            try:
                f_label = f.get_spec(label)
            except KeyError:
                continue

            if f_label == on:
                logger.info("{priority} is prioritized over \
                    {scan}, not copying {scan}".format(priority=s, scan=f))
                to_filt.add(f)

    # Remove object in filt list from series_list
    return [f for f in series_list if f not in to_filt]


def process_subject(subject, cfg, be, bids_dir, rewrite):
    """
    Convert subject in DATMAN folder to BIDS-style
    """

    ident = scanid.parse(subject)
    subscan = scan.Scan(subject, cfg)
    bids_sub = ident.get_bids_name()
    bids_ses = ident.timepoint
    exp_path = make_bids_template(bids_dir, "sub-" + bids_sub,
                                  "ses-" + bids_ses)

    dm_to_bids = []

    if dashboard.dash_found:
        db_subject = dashboard.get_subject(subject)
        db_subject.add_bids(bids_sub, bids_ses)

    # Construct initial BIDS transformation info
    scan_list = list(sort_by_series(subscan.niftis))
    for i, series in enumerate(scan_list):

        # Construct bids name
        logger.info("Processing {}".format(series))
        bids_dict = get_tag_bids_spec(cfg, series.tag)
        if not bids_dict:
            continue
        bids_dict.update({"sub": bids_sub, "ses": bids_ses})

        # Deal with reference scans
        if bids_dict.get('is_ref', False):
            target_dict = get_tag_bids_spec(cfg, scan_list[i + 1].tag)
            bids_dict.update({'task': target_dict['task']})

        bids_prefix = be.construct_bids_name(bids_dict)
        class_path = os.path.join(exp_path, bids_dict["class"])

        # Make dm2bids transformation file, update source if applicable
        bidsfiles = BIDSFile(bids_sub, bids_ses, series, class_path,
                             bids_prefix, bids_dict).update_source(cfg, be)

        if bidsfiles is None:
            logger.error("Cannot find derivative of {}".format(series))
            logger.warning("Skipping!")
            continue

        if isinstance(bidsfiles, list):
            dm_to_bids.extend(bidsfiles)
        else:
            dm_to_bids.append(bidsfiles)

    # Apply prioritization calls
    dm_to_bids = prioritize_scans(dm_to_bids)

    # Prepare fieldmap information (requires knowledge about all scans)
    dm_to_bids = prepare_fieldmaps(dm_to_bids)

    # Transfer files over
    for k in dm_to_bids:
        if os.path.exists(k.dest_nii) and not rewrite:
            logger.info("Output file {} already exists!".format(k.dest_nii))
            continue
        k.transfer_files()
        if dashboard.dash_found:
            db_series = dashboard.get_scan(k.series.path)
            db_series.add_bids(str(k))

    return


def main():

    arguments = docopt(__doc__)

    study = arguments["<study>"]

    cfg = config.config(study=study)

    subjects = arguments["--subject"]
    bids_dir = arguments["--bids-dir"] or cfg.get_path("bids")
    yml = arguments["--yaml"] or YAML
    rewrite = arguments["--rewrite"]
    debug = arguments["--debug"]

    be = BIDSEnforcer(yml)

    if debug:
        logger.setLevel(logging.DEBUG)

    make_dataset_description(bids_dir, study, be.version)

    if not subjects:
        subjects = os.listdir(cfg.get_path("nii"))

    for s in subjects:

        if "PHA" in s:
            logger.info("{} is a Phantom scan - skipping...".format(s))
            continue

        logger.info("Processing: {}".format(s))
        process_subject(s, cfg, be, bids_dir, rewrite)


if __name__ == "__main__":
    main()
