import collections
import yaml

tree = lambda: collections.defaultdict(tree)

# register a recursive defaultdict with pyyaml
yaml.add_representer(collections.defaultdict,
                     yaml.representer.Representer.represent_dict)


class FormatError(Exception):
    """An exception thrown when the YAML document isn't formatted correctly"""
    pass


class Checklist:
    """Manipulates a checklist of items backed by a yaml document. 

    Currently the checklist is aimed at recording when specific MR series are
    to be blacklisted (i.e. deemed to be problematic in someway and so ought to
    be ignored) for specific datman processing stages. 

    See tests/test_checklist.py for examples of use, but in short: 

        import datman
        c = datman.checklist.load(yamlfile)

        c.blacklist("dm-proc-rest", "DTI_CMH_H001_01_01_T1_MPRAGE", 
            "Truncated scan")

        assert c.is_blacklisted("dm-proc-rest", "DTI_CMH_H001_01_01_T1_MPRAGE")

        datman.checklist.save(c, yamlfile)

    The underlying YAMl document is expected to have the following format (but 
    may also have other sections): 

        blacklist: 
            stage: 
                series:
                ...
            ... 

    That is, the top-level must be a dictionary, and entries below it must also 
    be dictionaries. 
    """

    def __init__(self, stream=None):
        if not stream:
            self.data = tree()
        else:
            self.data = yaml.load(stream) or tree()

        try:
            self._blacklist = self.data['blacklist']
        except TypeError:
            raise FormatError("node /blacklist is not a dict")

    def blacklist(self, section, key, value=None):
        try:
            self._blacklist[section][key] = value
        except TypeError:
            raise FormatError('node /blacklist/{}/{} is not a dict'.format(
                section, value))

    def is_blacklisted(self, section, key):
        try:
            return section in self._blacklist and key in self._blacklist[section]
        except TypeError:
            raise FormatError('node /blacklist/{}/{} is not a dict'.format(
                section, key))

    def unblacklist(self, section, key):
        try:
            del self._blacklist[section][key]
        except KeyError:
            pass

    def save(self, stream):
        yaml.dump(self.data, stream, default_flow_style=False)

    def __str__(self):
        return yaml.dump(self.data, default_flow_style=False)

    def __repr__(self):
        return str(self)


def load(stream_or_file=None):
    """Convenience method for loading a checklist from a file or stream"""
    stream = stream_or_file
    if isinstance(stream_or_file, basestring):
        stream = open(stream_or_file, 'r')

    return Checklist(stream)

def save(checklist, stream_or_file):
    """Convenience method for saving a checklist from a file or stream"""
    stream = stream_or_file
    if isinstance(stream_or_file, basestring):
        stream = open(stream_or_file, 'w')

    checklist.save(stream)
