#!/usr/bin/env python

from setuptools import setup
import glob

# pypi doesn't like markdown
# https://github.com/pypa/packaging-problems/issues/46
try:
    import pypandoc
    description = pypandoc.convert('README.md', 'rst')
except (IOError, ImportError):
    description = ''

setup(
    name='datman',
    version='0.9',
    description='Manage neuroimaging data like a bro',
    author="Erin Dickie, Jon Pipitone, Joseph Viviano",
    author_email="erin.w.dickie@gmail.com, jon@pipitone.ca, joseph@viviano.ca",
    license='Apache 2.0',
    url="https://github.com/tigrlab/datman",
    long_description=description,
    scripts=glob.glob('bin/*.py') + glob.glob('bin/*.sh') + glob.glob('assets/*.sh'),
    packages=['datman'],
    classifiers=[
       'Development Status :: 4 - Beta',
       'Environment :: Console',
       'Intended Audience :: Science/Research',
    ],
    install_requires=['docopt', 'matplotlib', 'numpy', 'pandas', 'requests',
        'scipy', 'scikit-image', 'pyyaml', 'nibabel', 'pydicom', 'qbatch'],
 )
