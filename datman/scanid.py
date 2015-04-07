"""
Represents scan identifiers that conform to the TIGRLab naming scheme
"""
import os.path
import re

SCANID_RE = '(?P<study>[^_]+)_' \
            '(?P<site>[^_]+)_' \
            '(?P<subject>[^_]+)_' \
            '(?P<timepoint>[^_]+)_' \
            '(?P<session>[^_]+)'

SCANID_PHA_RE = '(?P<study>[^_]+)_' \
                '(?P<site>[^_]+)_' \
                '(?P<subject>PHA_[^_]+)' \
                '(?P<timepoint>)' \
                '(?P<session>)'

FILENAME_RE = SCANID_RE + '_' + \
              r'(?P<tag>[^_]+)_' + \
              r'(?P<description>[^\.]*)' + \
              r'(?P<ext>\..*)?'

FILENAME_PHA_RE = SCANID_PHA_RE + '_' + \
              r'(?P<tag>[^_]+)_' + \
              r'(?P<description>[^\.]*)' + \
              r'(?P<ext>\..*)?'

SCANID_PATTERN       = re.compile('^'+SCANID_RE+'$')
SCANID_PHA_PATTERN   = re.compile('^'+SCANID_PHA_RE+'$')
FILENAME_PATTERN     = re.compile('^'+FILENAME_RE+'$')
FILENAME_PHA_PATTERN = re.compile('^'+FILENAME_PHA_RE+'$')

class ParseException(Exception):
    pass

class Identifier:
    def __init__(self, study, site, subject, timepoint, session):
        self.study = study
        self.site = site
        self.subject = subject
        self.timepoint = timepoint
        self.session = session

    def get_full_subjectid(self):
        return "_".join([self.study, self.site, self.subject])

    def __str__(self):
        if self.timepoint:
            return "_".join([self.study, 
                             self.site, 
                             self.subject, 
                             self.timepoint,
                             self.session])
        else:  # it's a phantom, so no timepoints
            return self.get_full_subjectid() 
                  
def parse(identifier):
    if type(identifier) is not str: raise ParseException()

    match = SCANID_PATTERN.match(identifier)
    if not match: match = SCANID_PHA_PATTERN.match(identifier)
    if not match: raise ParseException()

    ident = Identifier(study    = match.group("study"), 
                       site     = match.group("site"),
                       subject  = match.group("subject"),
                       timepoint= match.group("timepoint"),
                       session  = match.group("session"))

    return ident

def parse_filename(path):
    fname = os.path.basename(path)
    match = FILENAME_PATTERN.match(fname)
    if not match: match = FILENAME_PHA_PATTERN.match(fname)
    if not match: raise ParseException()

    ident = Identifier(study    = match.group("study"), 
                       site     = match.group("site"),
                       subject  = match.group("subject"),
                       timepoint= match.group("timepoint"),
                       session  = match.group("session"))

    tag = match.group("tag")
    description = match.group("description")
    return ident, tag, description

def is_scanid(identifier):
    try: 
        parse(identifier)
        return True
    except ParseException:
        return False
    
# vim: ts=4 sw=4:
