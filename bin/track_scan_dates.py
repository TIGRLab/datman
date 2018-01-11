from pyxnat import Interface
from datetime import datetime
import json
import operator
from datman import config as CON
from datman import scanid

username = "mathum"
dateformat = "%Y-%m-%d"
datetimeformat = "%Y-%m-%d %H:%M:%S.%f"
xdate = "date"
xuploaddate = "insert_date"
xuploaddiff = "upload_difference"

def main():
    quit = "n"
    #central = Interface(server="https://xnat.imaging-genetics.camh.ca", user=username)


    while (quit != "y"):
        study = raw_input("Which study do you want to track scans for? ")
        print study

        con = CON.config()

        try:
            projects = set(con.get_xnat_projects(study))
        except ValueError:
            print "Study does not exist"


        if False:
            constraints = [('xnat:mrSessionData/PROJECT', '=', project)]

            table = central.select('xnat:mrSessionData', ['xnat:mrSessionData/XNAT_COL_MRSESSIONDATAACQUISITION_SITE']).where(constraints)
            a = set()
            for item in table:
                for val in item.values():
                    a.add(val)

            output = dict()
            first = True

            constraints = [('xnat:mrSessionData/PROJECT', '=', project)]
            table = central.select('xnat:mrSessionData',
                                ['xnat:mrSessionData/DATE',
                                'xnat:mrSessionData/INSERT_DATE',
                                'xnat:mrSessionData/XNAT_COL_MRSESSIONDATAACQUISITION_SITE']
                                 ).where(constraints)


            for value in a:
                output[value] = dict()
                constraints = [('xnat:mrSessionData/XNAT_COL_MRSESSIONDATAACQUISITION_SITE', '=', value), 'AND', ('xnat:mrSessionData/PROJECT', '=', project)]
                table = central.select('xnat:mrSessionData',
                                    ['xnat:mrSessionData/DATE',
                                    'xnat:mrSessionData/INSERT_DATE']
                                     ).where(constraints)


                sort = sorted(table.items(), key=operator.itemgetter(1), reverse=True)
                if (len(sort) >=2):
                    output[value][xdate] = sort[0][0]
                    output[value][xuploaddate] = sort[0][1]
                    latest = datetime.strptime(output[value][xuploaddate], datetimeformat)
                    secondlatest = datetime.strptime(sort[1][1], datetimeformat)
                    output[value][xuploaddiff] =  latest - secondlatest
                elif (len(sort) ==1):
                    output[value][xdate] = sort[0][0]
                    output[value][xuploaddate] = sort[0][1]
                    output[value][xuploaddiff] = None
                elif (len(sort) ==0):
                    output[value][xdate] = None
                    output[value][xuploaddate] = None
                    output[value][xuploaddiff] = None


                    printdict(output)



        quit = raw_input("Quit? y/n ")


def printdict(output):
    print "{:<30} {:<15} {:<30} {:<40}".format("Project", "Scan Date", "Latest Upload Date", "Time Since Last Upload")
    for key, values in output.iteritems():
        pdate = values[xdate]
        uploaddate = values[xuploaddate]
        updiff = values[xuploaddiff]
        print "{:<30} {:<15} {:<30} {:<40}".format(key, str(pdate), str(uploaddate), str(updiff))

def json_to_string(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        raise TypeError ("Type %s not serializable" % type(obj))


if __name__ == "__main__":
    main()
