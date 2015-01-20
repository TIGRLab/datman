"""
These commands are currently specific to the spins project, and will eventually be made more general for use across projects.
"""
# thanks to http://stackoverflow.com/questions/1057431/loading-all-modules-in-a-folder-in-python
import os, glob

modules = glob.glob(os.path.dirname(__file__)+"/*.py")
__all__ = [ os.path.basename(f)[:-3] for f in modules]

from . import *

