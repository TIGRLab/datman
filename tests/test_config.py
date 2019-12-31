#!/usr/bin/env python
"""
Tests for datman/config.py
"""

import os

import datman.config as config

FIXTURE_DIR = "tests/fixture_dm_config"


def test_initialise_from_environ():
    os.environ['DM_CONFIG'] = os.path.join(FIXTURE_DIR, 'site_config.yml')
    os.environ['DM_SYSTEM'] = 'test'
    config.config()
