#!/usr/bin/env python
"""
Tests for datman/config.py
"""

import os
import unittest

import nose.tools
from nose.tools import raises

import datman.config as config

FIXTURE_DIR = "tests/fixture_dm_config"


def test_initialise_from_environ():
    os.environ['DM_CONFIG'] = os.path.join(FIXTURE_DIR, 'site_config.yml')
    os.environ['DM_SYSTEM'] = 'test'
    cfg = config.config()
