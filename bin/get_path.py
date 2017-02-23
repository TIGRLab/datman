#!/usr/bin/env python
"""Returns the paths for a datman project

Usage:
    get_path.py <study> <path>

Arguments:
    <study>     Name of the study
    <path>      Path to get (see details)

Details:
    uses datman/config.py for project details, returns path definitions
    from tigrlab_config.yaml or project_settings.yml
"""
from __future__ import print_function
import sys
from docopt import docopt
from datman import config


def main():
    arguments = docopt(__doc__)
    study = arguments['<study>']
    path = arguments['<path>']

    try:
        cfg = config.config()
        p = cfg.get_path(path, study=study)
        print(p)
    except Exception as e:
        eprint(str(e))


def eprint(*args, **kwargs):
    """Print to stderr"""
    print(*args, file=sys.stderr, **kwargs)


if __name__ == '__main__':
    main()
