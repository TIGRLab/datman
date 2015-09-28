"""
Some tools for interacting with YAML files.
"""
import yaml
import sys
import collections

def load_yaml(filename):
    """
    Attempts to load a YAML file. Complains and exits if it fails.
    """

    try:
        with open(filename, 'r') as stream:
            data = yaml.load(stream)
    except:
        print("ERROR: Supplied configuration file {} is not a properly-formatted YAML file.".format(filename))
        sys.exit()

    return data

def save_yaml(filename, data):
    """
    Saves a YAML file.
    """
    
    try:
        with open(filename, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)
    except:
        print('ERROR: Do not have permissions to edit submitted YAML file.')
        sys.exit()

def blacklist_series(filename, stage, series, message):
    """
    Adds a series to the list of ignored for the defined stage of the pipeline in 
    the configuration file. It also appends a diagnostic message to the series.
    """

    # kickflip to create a recursive defaultdict, and register it with pyyaml
    tree = lambda: collections.defaultdict(tree)
    yaml.add_representer(collections.defaultdict, yaml.representer.Representer.represent_dict)

    data = load_yaml(filename)
    data['ignore'][stage][series] = message
    save_yaml(filename, data)

def whitelist_series(filename, stage, series):
    """
    Checks if a series in a particular stage is blacklisted. If so, this removes it.
    """

    # kickflip to create a recursive defaultdict, and register it with pyyaml
    tree = lambda: collections.defaultdict(tree)
    yaml.add_representer(collections.defaultdict, yaml.representer.Representer.represent_dict)

    data = load_yaml(filename)
    serieslist = data['ignore'][stage].keys()

    if series in serieslist:
        _ = data['ignore'][stage].pop(series)
        save_yaml(filename, data)

def list_series(filename, stage):
    """
    Returns all of the series from a stage as a list.
    """

    data = load_yaml(filename)
    serieslist = data['ignore'][stage].keys()

    return serieslist
