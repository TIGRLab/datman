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

    def get_full_subjectid(self):
        return "_".join([self.study, self.site, self.subject])

    def __str__(self):
        return "_".join([self.study, self.site, self.subject, self.timepoint,
                        self.session])

class PhantomIdentifier(Identifier):
    def __init__(self, study, site, subject):
        self.study = study
        self.site = site
        self.subject = subject
        self.timepoint = None 
        self.session = None 

    def __str__(self):
        return self.get_full_subjectid()

def parse(identifier):
    try:
        # Phantom's have a different ID format: 
        # <study>_<site>_<subjectid>
        #
        # where <subjectid> starts with PHA_
        #
        if "_PHA_" in identifier:
            study, site, pha, subject = identifier.split("_")
            if pha != "PHA":
                raise ParseException()
            return PhantomIdentifier(study, site, "PHA_" + subject)
        else:       
          study, site, subject, timepoint, session = identifier.split("_")
          return Identifier(study, site, subject, timepoint, session)
    except (ValueError, TypeError):
        raise ParseException()


def is_scanid(identifier):
    try: 
        parse(identifier)
        return True
    except ParseException:
        return False
    
# vim: ts=4 sw=4:
