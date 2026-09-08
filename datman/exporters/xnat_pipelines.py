"""Exporter for XNAT pipeline outputs.

Pipeline outputs that were generated on XNAT, rather than locally, can be
'exported' to the local file system. Outputs will be copied from their
original home in 'resources' to the user's chosen destination. Symlinks
will be left behind to document where they were moved to and prevent
repeated downloads from XNAT.
"""
import logging
import os
from pathlib import Path
from shutil import move

from datman.exceptions import ConfigException

from .base import SessionExporter

logger = logging.getLogger(__name__)

__all__ = ["XnatPipelineSettings", "XnatPipelines"]


class XnatPipelineSettings:
    """Parses XNAT pipeline settings provided by the user.

    The configuration may be specified at the global, study, or scan site
    level. Config blocks also override each other in that order, if defined in
    multiple places, which means that default settings can be provided
    globally and then overridden per study or per scan site.

    The configuration block must start with the 'XnatPipeline' key. At a
    minimum you must provide the name of the resources folder on XNAT where
    the pipeline outputs are stored (per experiment) and a relative local path
    indicating where to deposit it in the study's directory on the file system.

    Optionally you can also use the 'override' setting to indicate that a
    specific local exporter should be 'turned off' because the xnat copy
    replaces it. This value must match the 'type' of a
    datman.exporters.SessionExporter class. For example, if XNAT will be
    responsible for generating bids output, add 'override': 'bids' to prevent
    a local bids copy from being created from the dicoms.

    For example:

    # This starts the config block
    XnatPipelines:
        # This key should match the folder name (case-sensitive) in each
        # experiment's resources folder that holds the pipeline outputs.
        'BIDS':
          # This stops the built in exporter from running to prevent
          # redundant outputs / wasted time.
          # If 'override' is defined, then 'dest' must be also.
          'override': 'bids'
          # The location to store the files, relative to the study's root dir.
          'dest': 'data/bids'

        # If override isn't used, the 'dest' path can be supplied directly.
        'MRIQC': 'pipelines/mriqc_25'
        'FMRIPREP': 'pipelines/fmriprep'

    """
    def __init__(self, config):
        """Retrieves and verifies pipeline settings from the datman config.
        """
        if not config.study_name:
            raise ConfigException(
                'Attempted to use study-specific functionality without '
                'setting a study for the config object.'
            )

        self.study = config.study_name

        base_dir = Path(config.get_study_base())

        parsed_settings = {}
        overrides = []
        for site in config.get_sites():
            # Will raise UndefinedSetting if XnatPipelines completely missing
            raw_settings = config.get_key('XnatPipelines', site=site)
            site_settings, site_overrides = self._parse_settings(
                base_dir,
                raw_settings
            )
            parsed_settings[site] = site_settings
            overrides.extend(site_overrides)

        self.settings = parsed_settings
        self.overrides = list(set(overrides))

    def _parse_settings(
            self, base_dir: Path, raw_settings: dict
    ) -> (dict[str, Path], list[str]):
        """Parse and validate an XnatPipelines settings block.

        Raises:
            ConfigException if an invalid entry is found.
        """
        settings = {}
        overrides = []
        for pipeline, entry in raw_settings.items():

            if isinstance(entry, str):
                full_path = base_dir / entry
                settings[pipeline] = full_path
                continue

            if not isinstance(entry, dict):
                raise ConfigException(
                    f'Malformed "XnatPipelines" entry found: {entry} '
                    'valid entries must be a relative path or a dict '
                    'containing the "dest" key.'
                )

            if 'dest' not in entry:
                raise ConfigException(
                    f'Malformed "XnatPipelines" entry found: {entry} '
                    'valid entries must be a relative path or a dict '
                    'containing the "dest" key.'
                )

            if 'override' in entry:
                overrides.append(entry['override'])

            full_path = base_dir / entry['dest']
            settings[pipeline] = full_path

        for pipeline in list(settings.keys()):
            try:
                settings[pipeline].mkdir(parents=True)
            except FileExistsError:
                pass
            except OSError as e:
                logger.error(
                    f'Failed to create destination dir {settings[pipeline]} '
                    f'for XNAT pipeline {pipeline}. Pipeline will be '
                    f'ignored. Cause: {e}'
                )
                del settings[pipeline]

        return settings, overrides

    def __repr__(self):
        return f"<XnatPipelineSettings - {self.study}>"


class XnatPipelines(SessionExporter):
    """An exporter for pipelines (bids, etc.) that run directly on XNAT.

    Find and pull the user-configured xnat pipeline contents into their
    appropriate directories. Leaves a symlink behind in the RESOURCES
    folder to avoid repeated downloading of duplicate resources.
    """

    type = 'xnat_pipelines'

    def __init__(self, config, session, experiment, xp_opts=None,
                 dry_run=False, **kwargs):

        if not xp_opts:
            xp_opts = XnatPipelineSettings(config)

        self.opts = xp_opts.settings[session.site]
        self.source = Path(session.resource_path)

        super().__init__(config, session, experiment, **kwargs)

    def needs_raw_data(self):
        return False

    def outputs_exist(self):
        """True if every 'exported' resource has been changed to a symlink.
        """
        if not self.source.exists():
            # There's nothing in resources to pull.
            return False

        for src_path in self.source.iterdir():
            if not src_path.is_dir():
                continue

            if src_path.name not in self.opts:
                continue

            for base_path, _, files in src_path.walk():
                for item in files:
                    src_item = base_path / item
                    if not src_item.is_symlink():
                        # Data hasn't been moved to intended destination
                        return False
                    # We can't check that the link points to the intended
                    # destination here because some dataset files are
                    # identical across all subs and will only need to be
                    # linked once (therefore pointing to the first sub
                    # extracted)
                    if not src_item.exists():
                        # Clean up broken symlinks here so they can be
                        # redownloaded from xnat if the item still exists.
                        self.handle_broken_link(src_item)
        return True

    def export(self, _, **kwargs):
        """Move all pipeline files from 'resources' to their intended home.

        This leaves a symlink behind in the resources dir for each moved file.
        """
        if self.outputs_exist():
            return

        for src_path in self.source.iterdir():
            if not src_path.is_dir():
                continue

            if src_path.name not in self.opts:
                continue

            dest_path = self.opts[src_path.name]

            for base_path, _, files in src_path.walk():
                for item in files:
                    in_path = base_path / item
                    out_path = dest_path / in_path.relative_to(src_path)

                    if out_path.exists() and in_path.is_symlink():
                        continue

                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    move(in_path, out_path)
                    in_path.symlink_to(
                        os.path.relpath(out_path, start=in_path.parent)
                    )

    def handle_broken_link(self, src_item):
        """Re-link items that have been blacklisted, remove broken links.

        If a pipeline output is one that gets reviewed, it may be blacklisted
        and moved to a new location, which then breaks the source
        link and creates a danger of repeated downloading. This will fix these
        links or remove them if they actually represent missing data.
        """
        orig_location = src_item.readlink()

        # Fix the source for a file that has been blacklisted
        rel_bl_dir = orig_location.parent.parent / 'blacklisted'
        bl_item = src_item.parent / rel_bl_dir / orig_location.name

        if not bl_item.exists():
            logger.debug(f"Removing broken symlink {src_item}")
            src_item.unlink()
            return

        new_target = os.path.relpath(bl_item, start=src_item.parent)
        logger.debug(
            f"Fixing broken link {src_item}: changing target from "
            f"{orig_location} to {new_target}"
        )
        src_item.unlink()
        src_item.symlink_to(new_target)
