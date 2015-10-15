"""
This holds the commands for the EPItome CLI. To install a new command, one only
needs to drop an appropriate .py function into this folder.
"""

# thanks to http://stackoverflow.com/questions/1057431/loading-all-modules-in-a-folder-in-python

import os, glob

modules = glob.glob(os.path.dirname(__file__)+"/*.py")
__all__ = [ os.path.basename(f)[:-3] for f in modules]

from . import *
#import __all__