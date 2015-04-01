"""
Represents scan identifiers that conform to the TIGRLab naming scheme
"""

class ParseException(Exception):
    pass

class Identifier:
    def __init__(self, study, site, subject, timepoint, session):
        self.study = study
        self.site = site
        self.subject = subject
        self.timepoint = timepoint
        self.session = session

    def __str__(self):
        return "_".join([self.study, self.site, self.subject, self.timepoint,
                        self.session])

def parse(identifier):
    try:
        study, site, subject, timepoint, session = identifier.split("_")
    except:
        raise ParseException()

    return Identifier(study, site, subject, timepoint, session)

def is_scanid(identifier):
    try: 
        parse(identifier)
        return True
    except ParseException:
        return False
    
# vim: ts=4 sw=4:
