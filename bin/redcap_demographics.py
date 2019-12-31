#!/usr/bin/env python

'''
This script is used to bring redcap demographics variables into our filesystem.

Usage:
    redcap_demographics.py [options] <study>

Arguments:
    <study>            Name of the datman managed study

Options:
    --URL PATH         set the REDCap URL
                       [default: https://redcap.smh.ca/redcap/api/]
    --output PATH      set the location to save the output csv file
                       [default: clinical/demographics.csv]

'''
import os
import sys

from requests import post
from docopt import docopt

import datman.config


def main():
    arguments = docopt(__doc__)
    url = arguments['--URL']
    study = arguments['<study>']
    output_path = arguments['--output']

    config = datman.config.config(study=study)
    meta_path = config.get_path('meta')
    token_file = 'ahrc_token'
    token_path = os.path.join(meta_path, token_file)
    output_path = os.path.join(config.get_path('data'), output_path)

    token = get_token(token_path)
    payload = get_payload(token)

    REDCap_variables = ['record_id',
                        'redcap_event_name',
                        'demo_sex_birth',
                        'demo_age_study_entry',
                        'demo_highest_grade_self',
                        'term_premature_yn']

    data = make_rest(url, payload, REDCap_variables)
    column_headers = ['record_id',
                      'group',
                      'sex',
                      'age',
                      'education',
                      'terminated']

    make_csv(output_path, data, column_headers)


def get_token(token_path):
    if not os.path.exists(token_path):
        print('Path {} does not exist.'.format(token_path))
        sys.exit(1)

    with open(token_path, 'r') as token_file:
        lines = token_file.readlines()
    try:
        token = lines[0]
    except IndexError:
        print("Empty file.")
    return token.strip('\n')


def get_payload(token):
    payload = {'token': token,
               'format': 'json',
               'content': 'record'}
    return payload


def make_rest(url, payload, REDCap_variables):
    response = post(url, data=payload)
    if response.status_code != 200:
        print('Cannot talk to server, response code is {}.'
              ''.format(response.status_code))
        sys.exit(1)
    return parse_data(response.json(), REDCap_variables)


def parse_data(SPINS_data, REDCap_variables):
    lines = []
    for record_id in SPINS_data:
        entry = []
        for variable in REDCap_variables:
            item = record_id[variable]
            entry.append(item)
        lines.append(entry)
    return lines


def make_csv(output_path, data, column_headers):
    with open(output_path, 'w') as data_file:
        line = ','.join(column_headers)
        data_file.write(line + '\n')
        for item in data:
            line = ','.join(item)
            data_file.write(line + '\n')


if __name__ == '__main__':
    main()
