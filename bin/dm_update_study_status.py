#!/usr/bin/env python

import datman.dashboard as dashboard
import datman.config as cfg


def main():
    config = cfg.config()
    studies = config.get_key('Projects').keys()

    for study in studies:
        try:
            config.set_study(study)
        except Exception:
            pass
        is_open = config.get_key('IsOpen')

        dashboard.set_study_status(study, is_open)


if __name__ == '__main__':
    main()
