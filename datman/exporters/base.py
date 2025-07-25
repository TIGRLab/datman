"""Base classes to use for any datman exporter.

To allow datman to export to a new format or organizational style create a
class that inherits from either SessionExporter if it must work on an entire
scan session at once, or a SeriesExporter if it works on a single individual
scan series at a time.
"""

from abc import ABC, abstractmethod
import os
import logging

logger = logging.getLogger(__name__)

__all__ = ["SeriesExporter", "SessionExporter"]


class Exporter(ABC):
    """An abstract base class for all Exporters.
    """

    # Subclasses must define this
    type = None

    @classmethod
    def get_output_dir(cls, session):
        """Retrieve the exporter's output dir without needing an instance.
        """
        return getattr(session, f"{cls.type}_path")

    @abstractmethod
    def outputs_exist(self):
        """Whether outputs have already been generated for this Exporter.

        Returns:
            bool: True if all expected outputs exist, False otherwise.
        """

    @abstractmethod
    def needs_raw_data(self):
        """Whether raw data must be downloaded for the Exporter.

        Returns:
            bool: True if raw data must be given, False otherwise. Note that
                False may be returned if outputs already exist.
        """

    @abstractmethod
    def export(self, raw_data_dir, **kwargs):
        """Exports raw data to the current Exporter's format.

        Args:
            raw_data_dir (:obj:`str`): The directory that contains the
                downloaded raw data.
        """

    def make_output_dir(self):
        """Creates the directory where the Exporter's outputs will be stored.

        Returns:
            bool: True if directory exists (or isn't needed), False otherwise.
        """
        try:
            os.makedirs(self.output_dir)
        except FileExistsError:
            pass
        except AttributeError:
            logger.debug(f"output_dir not defined for {self}")
        except PermissionError:
            logger.error(f"Failed to make output dir {self.output_dir} - "
                         "PermissionDenied.")
            return False
        return True


class SessionExporter(Exporter):
    """A base class for exporters that take an entire session as input.

    Subclasses should override __init__ (without changing basic input args)
    and call super().__init__(config, session, experiment, **kwargs).

    The init function for SessionExporter largely exists to define expected
    input arguments and set some universally needed attributes.
    """

    def __init__(self, config, session, experiment, dry_run=False, **kwargs):
        self.experiment = experiment
        self.config = config
        self.session = session
        self.dry_run = dry_run

    def __repr__(self):
        fq_name = str(self.__class__).replace("<class '", "").replace("'>", "")
        name = fq_name.rsplit(".", maxsplit=1)[-1]
        return f"<{name} - {self.experiment.name}>"


class SeriesExporter(Exporter):
    """A base class for exporters that take a single series as input.
    """

    # Subclasses should set this
    ext = None

    def __init__(self, output_dir, fname_root, echo_dict=None, dry_run=False,
                 **kwargs):
        self.output_dir = output_dir
        self.fname_root = fname_root
        self.echo_dict = echo_dict
        self.dry_run = dry_run

    def outputs_exist(self):
        return os.path.exists(
            os.path.join(self.output_dir, self.fname_root + self.ext))

    def needs_raw_data(self):
        return not self.outputs_exist()

    def __repr__(self):
        fq_name = str(self.__class__).replace("<class '", "").replace("'>", "")
        name = fq_name.rsplit(".", maxsplit=1)[-1]
        return f"<{name} - {self.fname_root}>"
