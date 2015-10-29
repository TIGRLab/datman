from nose.tools import *
import importlib
import sys
from StringIO import StringIO

check_headers = importlib.import_module('bin.dm-check-headers')


class mock_header(dict):

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)

    def dir(self):
        return self.keys()


def test_empty_headers():
    stdhdr = mock_header()
    cmphdr = mock_header()
    mismatches = check_headers.compare_headers(stdhdr, cmphdr)

    expected = []
    assert mismatches == expected


def test_header_in_std_only():
    stdhdr = mock_header({"do-not-ignore": 1})
    cmphdr = mock_header()

    mismatches = check_headers.compare_headers(stdhdr, cmphdr)

    expected = [check_headers.Mismatch(
        header="do-not-ignore",
        expected=1,
        actual=None,
        tolerance=None)]
    assert mismatches == expected


def test_header_in_cmp_only():
    stdhdr = mock_header()
    cmphdr = mock_header({"do-not-ignore": 1})

    mismatches = check_headers.compare_headers(stdhdr, cmphdr)

    expected = [check_headers.Mismatch(
        header="do-not-ignore",
        expected=None,
        actual=1,
        tolerance=None)]
    assert mismatches == expected


def test_header_single_match():
    stdhdr = mock_header({"same": 1})
    cmphdr = mock_header({"same": 1})

    mismatches = check_headers.compare_headers(stdhdr, cmphdr)

    expected = []
    assert mismatches == expected


def test_header_single_mismatch():
    stdhdr = mock_header({"same": 1})
    cmphdr = mock_header({"same": 2})

    mismatches = check_headers.compare_headers(stdhdr, cmphdr)

    expected = [check_headers.Mismatch(
        header="same",
        expected=1,
        actual=2,
        tolerance=None)]
    assert mismatches == expected

# vim: set ts=4 sw=4 :
