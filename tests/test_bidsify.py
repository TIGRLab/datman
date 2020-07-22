import unittest
import logging
import os
import tempfile
import importlib
import json


logging.disable(logging.CRITICAL)

bidsify = importlib.import_module('bin.bidsify')


class CheckBidsifyUpdateOnlyNewFiles(unittest.TestCase):
    """ Check that only new dataset_description files are created. If one
        exists, don't re-write it.
    """

    def setUp(self):
        # Create a temporary directory
        self.studyname = 'STUDYNAME'
        self.bidsdir = tempfile.TemporaryDirectory()

    def test_make_dataset_descriptor(self):
        # create dataset description
        bidsify.make_dataset_description(self.bidsdir.name, self.studyname, '1')
        dataset_description = os.path.join(self.bidsdir.name,
                                           'dataset_description.json')

        # test dataset_description creation
        self.assertTrue(os.path.isfile(dataset_description))
        # cleanup
        os.remove(dataset_description)

    def test_already_exists_dataset_description(self):
        # create dataset description
        bidsify.make_dataset_description(self.bidsdir.name, self.studyname, '1')
        bidsify.make_dataset_description(self.bidsdir.name, self.studyname, '2')
        dataset_description = os.path.join(self.bidsdir.name,
                                           'dataset_description.json')

        with open(dataset_description, 'r') as f:
            data = json.load(f)

        # check that version 2 was skipped because 1 already exists
        self.assertEquals(data['BIDSVersion'], '1')
