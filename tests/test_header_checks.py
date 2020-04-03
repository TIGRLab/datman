#!/usr/bin/env python
import datman.header_checks as header_checks


def test_handle_diff_returns_dict_on_valueerror():

    value = [1, 2, 3]
    expected = [1, 2, 3, 5]
    output = {'expected': [1, 2, 3, 5], 'actual': [1, 2, 3]}
    assert header_checks.handle_diff(value, expected) == output
