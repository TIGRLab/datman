import operator
import os
from datetime import datetime

from pyxnat import Interface

from datman import config as CON
from datman import scanid

dateformat = "%Y-%m-%d"
datetimeformat = "%Y-%m-%d %H:%M:%S.%f"
date = "date"
uploaddate = "insert_date"
uploaddiff = "upload_difference"

phan = "phantom"
hum = "human"


def main():
    quit = "n"

    username = os.environ["XNAT_USER"]
    password = os.environ["XNAT_PASS"]
    central = Interface(server="https://xnat.imaging-genetics.camh.ca",
                        user=username,
                        password=password)

    while (quit != "y"):
        study = input("Which study do you want to track scans for? ")
        con = CON.config()

        try:
            projects = set(con.get_xnat_projects(study))
        except ValueError:
            print("Study does not exist")
            return 0

        tracking_table = dict()

        for project in projects:
            constraints = [('xnat:mrSessionData/PROJECT', '=', project)]
            table = central.select('xnat:mrSessionData',
                                   ['xnat:mrSessionData/SUBJECT_LABEL',
                                    'xnat:mrSessionData/DATE',
                                    'xnat:mrSessionData/INSERT_DATE']
                                   ).where(constraints)
            sort = sorted(table.items(), key=operator.itemgetter(2))
            for item in sort:
                site_name = scanid.parse(item[0]).site
                if scanid.is_phantom(item[0]):
                    site_name += "_PHA"
                    if "FBN" in item[0]:
                        site_name += "_FBN"
                    elif "ADN" in item[0]:
                        site_name += "_ADN"
                site_dict = tracking_table.setdefault(site_name, dict())
                last_update = site_dict.setdefault(uploaddate, datetime.min)
                current_update = datetime.strptime(item[2], datetimeformat)
                if last_update < current_update:
                    site_dict[date] = item[1]
                    site_dict[uploaddate] = current_update
                    if last_update == datetime.min:
                        site_dict[uploaddiff] = "No Other Uploads"
                    else:
                        site_dict[uploaddiff] = dttostr(current_update -
                                                        last_update)

        printdict(tracking_table)

        quit = input("Quit? y/n ")


def printdict(output):
    print("{:<15} {:<15} {:<30} {:<40}".format("Site", "Scan Date",
                                               "Latest Upload Date",
                                               "Time Between Last Uploads"))
    for key, values in output.items():
        pdate = values[date]
        update = values[uploaddate]
        updiff = values[uploaddiff]
        print("{:<15} {:<15} {:<30} {:<40}".format(key, str(pdate),
                                                   str(update), str(updiff)))


def dttostr(dt):
    hours, rem = divmod(dt.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return "%03d days %02d hours" % (dt.days, hours)


if __name__ == "__main__":
    main()
