"""datman's setup script."""
import sys
from setuptools import setup
import versioneer

SETUP_REQUIRES = ["setuptools >= 40.8"]
# This enables setuptools to install wheel on-the-fly
SETUP_REQUIRES += ["wheel"] if "bdist_wheel" in sys.argv else []


if __name__ == "__main__":
    setup(
        name="datman",
        version=versioneer.get_version(),
        cmdclass=versioneer.get_cmdclass(),
        setup_requires=SETUP_REQUIRES,
    )
