"""Exporter for XNAT pipeline outputs.

Pipeline outputs generated on XNAT, rather than locally, can be 'exported'
to the local file system using these exporters. Presently these pipeline
outputs are expected to be in the bids format only.
"""
from pathlib import Path

from datman.exceptions import ConfigException

from .base import SessionExporter


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
    replaces it. For example, if XNAT will be responsible for generating bids
    output, add 'override': 'bids' to prevent a local bids copy from being
    created from the dicoms.

    For example:

    # This starts the config block
    XnatPipelines:
        # This key should match the folder name (case-insensitive) in each
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

    def __init__(self, config, session, experiment, dry_run=False, **kwargs):
        super().__init__(config, session, experiment, **kwargs)

    # get_output_dir

    def outputs_exist(self):
        """Should be true if the contents of the xnat resources folder(s) exist
        in the defined output dirs.
        """
        return False

    def needs_raw_data(self):
        # Dependency on resource export...? I guess it should be true
        # except 'raw data' tends to just mean dcms and it needs resources
        # What happens if symlink in resources breaks? e.g. runs successfully
        # once and then pipelines output gets purged. Will it redownload or
        # require manual updating of resources dir?
        return False

    # make_output_dir -> Will need to make multiple...
