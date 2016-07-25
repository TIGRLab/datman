#!/usr/bin/env python
"""
Reads from yml config file and export info to determine what to put in run.sh for this project.
Then writes run.sh file.

Usage:
    tigr-write-runsh [options] <config.yml>

Arguments:
    <config.yml>             Configuration file in yml format

Options:
    --outputpath <path>      Full path to top of output tree
    --project NAME           Specify the name of the project to write run script for (default will write all)
    --local-system STR       Specify the system current system to read project metadata from
    --dest-system STR        Specitfy the system where you want to run your analysis
    --quiet                  Don't print warnings
    --verbose                Print warnings
    --help                   Print help


DETAILS

Reads from yml config file and export info to determine what to put in run.sh for this project.
Then writes run.sh file.

The systems given in the --local-system and --dest-system flags should match the
keys of the SystemSetting Dictionary within the config_yml.
Example: to write run scripts on the tigrlab cluster
            that are too be run on the scc
    tigr-write-runsh --local-system kimel --dest-system scc ${DATMAN_ASSETSDIR}/tigrlab_config.yaml

"""
from docopt import docopt
import datman as dm
import datman.utils
import datman.scanid
import yaml
import os
import sys


import filecmp
import difflib

arguments       = docopt(__doc__)
config_yml      = arguments['<config.yml>']
project         = arguments['--project']
dest_system     = arguments['--dest-system']
local_system    = arguments['--local-system']
outputpath      = arguments['--outputpath']
VERBOSE         = arguments['--verbose']
QUIET           = arguments['--quiet']

def write_software_loading(software_packages,runsh, SystemSettingsDest, indent = '  '):
    '''
    parses the SystemSettingsDest dictionary to figure out what bash line
    to write in order to load software then prints that line to runsh handle
    '''
    module_load_cmd = '{}module load'.format(indent)
    software_bash = ''
    for software_package in software_packages:
        if software_package in list(SystemSettingsDest['Software'].keys()):
            if 'module' in SystemSettingsDest['Software'][software_package].keys():
                if SystemSettingsDest['Software'][software_package]['module']:
                 module_load_cmd += ' {}'.format(
                        SystemSettingsDest['Software'][software_package]['module'])
            if 'bash_cmd' in SystemSettingsDest['Software'][software_package].keys():
               if SystemSettingsDest['Software'][software_package]['bash_cmd']:
                 software_bash += '{}\n'.format(
                        SystemSettingsDest['Software'][software_package]['bash_cmd'])
        else:
            sys.exit("{} software not found in {}".format(software_package, config_yml))
    runsh.write(module_load_cmd)
    runsh.write('\n{}'.format(software_bash))

## Read in the configuration yaml file
if not os.path.isfile(config_yml):
    sys.exit("configuration file not found. Try again.")

## load the yml file
with open(config_yml, 'r') as stream:
    config = yaml.load(stream)

## check that the expected keys are there
ExpectedKeys = ['PipelineSettings', 'Projects', 'ExportSettings', 'SystemSettings']
diffs = set(ExpectedKeys) - set(config.keys())
if len(diffs) > 0:
    sys.exit("configuration file missing {}".format(diffs))

GeneralPipelineSettings = config['PipelineSettings']

ExportSettings = config['ExportSettings']

## load systems setting and check that the expected fields are present
ExpectedSysKeys = ['DATMAN_ASSETSDIR','DATMAN_PROJECTSDIR','Software']
if dest_system:
    if dest_system in config['SystemSettings'].keys():
        SystemSettingsDest = config['SystemSettings'][dest_system]
else:
    SystemSettingsDest = config['SystemSettings']
diffs = set(ExpectedSysKeys) - set(SystemSettingsDest.keys())
if len(diffs) > 0:
    sys.exit("Destination System Setting {} not read \n.You might need to specify the system with the --dest-system option".format(diffs))

if local_system:
    if local_system in config['SystemSettings'].keys():
        SystemSettingsLocal = config['SystemSettings'][local_system]
else:
    SystemSettingsLocal = SystemSettingsDest
diffs = set(ExpectedSysKeys) - set(SystemSettingsLocal.keys())
if len(diffs) > 0:
    sys.exit("Local System Setting {} not read \n.You might need to specify the system with the --local-system option".format(diffs))
WorkFlows = SystemSettingsDest['PipelineSettings_torun']
#get the project names
Projects = [project] if project else config['Projects'].keys()

for Project in Projects:
    print("Working on Project {}".format(Project))
    projectdir = config['Projects'][Project]
    projectdir_dest = projectdir.replace('<DATMAN_PROJECTSDIR>',
                                    SystemSettingsDest['DATMAN_PROJECTSDIR'])
    ## check that the projectdir exists
    projectdir_dest =  os.path.normpath(projectdir_dest)

    projectdir_local = projectdir.replace('<DATMAN_PROJECTSDIR>',
                                    SystemSettingsLocal['DATMAN_PROJECTSDIR'])

    ## read in the project settings
    project_settings = os.path.join(projectdir_local, 'metadata', 'project_settings.yml')
    if not os.path.isfile(project_settings):
        sys.exit("{} file not found. Try again.".format('project_settings'))

    ## load the yml file
    with open(project_settings, 'r') as stream:
        ProjectSettings = yaml.load(stream)

    ## read in the site names as a list and the ScanTypes from their exportinfo field
    SiteNames = []
    ScanTypes = []
    for site in ProjectSettings['Sites']:
        SiteName = site.keys()[0]
        SiteNames.append(SiteName)
        ## read export info for each site
        for ScanType in site[SiteName]['ExportInfo']:
            ScanTypes.append(ScanType.keys()[0])
    ## take the unique scan types as an unordered list
    ScanTypes = list(set(ScanTypes))

    ## sets some variables using defaults if not given
    if 'XNAT_PROJECT' in ProjectSettings.keys():
        XNAT_PROJECT = ProjectSettings['XNAT_PROJECT']
    else:
        XNAT_PROJECT = Project

    if 'PREFIX' in ProjectSettings.keys():
        PREFIX = ProjectSettings['PREFIX']
    else:
        PREFIX = Project

    if 'MRUSER' in ProjectSettings.keys():
        MRUSER = ProjectSettings['MRUSER']
    else:
        MRUSER = Project

    if 'MRFOLDER' in ProjectSettings.keys():
        MRFOLDER = ProjectSettings['MRFOLDER']
    else:
        MRFOLDER = '${MRUSER}*/*'

    ## Update the General Settings with Project Specific Settings
    QC_Phantoms = False ## set QC_Phatoms to False

    ## the next section seems to to updating the original no matter how hard I try...
    with open(config_yml, 'r') as stream:
        config = yaml.load(stream)
    for workflow in WorkFlows:
        PipelineSettings = config['PipelineSettings'][workflow]

        if 'PipelineSettings' in ProjectSettings:
            for cmdi in ProjectSettings['PipelineSettings']:
                for cmdj in PipelineSettings:
                    if cmdi.keys()[0] in cmdj.keys()[0]:
                        cmdj.update(cmdi)

        ## unless an outputfile is specified, set the output to ${PROJECTDIR}/bin/run.sh
        if not outputpath:
            outputfile = os.path.join(projectdir_local,'bin','run_{}_{}.sh'.format(workflow,dest_system))
        else:
            projectoutput = os.path.join(outputpath,Project,'bin')
            dm.utils.makedirs(projectoutput)
            outputfile = os.path.join(projectoutput,'run_{}_{}.sh'.format(workflow,dest_system))

        # print("ScanTypes are {}".format(ScanTypes))
        #open file for writing
        runsh = open(outputfile,'w')

        runsh.write('''\
#!/bin/bash -l
# Runs pipelines like a bro
#
# Usage:
#   run.sh [options]
#
# Options:
#   --quiet     Do not be chatty (does nnt apply to pipeline stages)
#

set -u  # fail on unset variable
        ''')

        ## write the top bit
        runsh.write('\n\nexport DATMAN_PROJECTSDIR=' + SystemSettingsDest['DATMAN_PROJECTSDIR'] + '     # Top path of data structure\n')
        runsh.write('export DATMAN_ASSETSDIR=' + SystemSettingsDest['DATMAN_ASSETSDIR'] + '     # path to <datman>/assets/ \n')
        runsh.write('export XNAT_ARCHIVEDIR=' + SystemSettingsDest['XNAT_ARCHIVEDIR'] + '     # path to XNAT archive\n')
        runsh.write('export STUDYNAME=' + Project + '     # Data archive study name\n')
        runsh.write('export XNAT_PROJECT=' + XNAT_PROJECT + '  # XNAT project name\n')
        runsh.write('export MRUSER=' + MRUSER +'         # MR Unit FTP user\n')
        runsh.write('export MRFOLDER="'+ MRFOLDER +'"         # MR Unit FTP folder\n')
        runsh.write('export PROJECTDIR='+ projectdir_dest +'\n')
        runsh.write('export PREFIX='+ PREFIX +'\n')
        runsh.write('export SITES=('+ ' '.join(SiteNames) +')\n\n')

        ## write the export from XNAT
        for siteinfo in ProjectSettings['Sites']:
            site = siteinfo.keys()[0]
            xnat = siteinfo[site]['XNAT_Archive']
            runsh.write('export XNAT_ARCHIVE_' + site + '=' + xnat + '\n')
        runsh.write('\n')

        ## write the gold standard info
        if len(SiteNames) == 1:
            runsh.write('export ' + site + '_STANDARD=')
            runsh.write(projectdir_dest + '/metadata/gold_standards/\n')
        else:
            for site in SiteNames:
                runsh.write('export ' + site + '_STANDARD=')
                runsh.write(projectdir_dest + '/metadata/gold_standards/' + site + '\n')

        ## set some settings and load datman module
        runsh.write('''
args="$@"                           # commence ugly opt handling
DATESTAMP=$(date +%Y%m%d)
''')

        if 'to_load_quarantine' in SystemSettingsDest.keys():
            runsh.write('{}\n'.format(SystemSettingsDest['to_load_quarantine']))

        write_software_loading(['datman'],runsh, SystemSettingsDest, indent = '')
        runsh.write('export PATH=$PATH:${PROJECTDIR}/bin\n')

        ## define the message function
        runsh.write('function message () { [[ "$args" =~ "--quiet" ]] || echo "$(date): $1"; }\n\n')

        ## start running stuff
        runsh.write('{\n')
        runsh.write('  message "Running pipelines for study: $STUDYNAME"\n')

        ## get the scans from the camh server
        for cmd in PipelineSettings:
            cmdname = cmd.keys()[0]
            if cmd[cmdname] == False: continue
            if 'runif' in cmd[cmdname].keys():
                if not eval(cmd[cmdname]['runif']): continue
            if cmdname == 'qc-phantom.py': QC_Phantoms = True
            if 'message' in cmd[cmdname].keys():
                runsh.write('\n  message "'+ cmd[cmdname]['message']+ '..."\n')
            runsh.write('  (\n')
            if 'dependancies' in cmd[cmdname].keys():
                dependancies = cmd[cmdname]['dependancies']
                if type(dependancies) is str: dependancies = [dependancies]
                write_software_loading(dependancies,runsh, SystemSettingsDest)
            if 'environment' in cmd[cmdname].keys():
                runsh.write('  '+ cmd[cmdname]['environment']+'\n')
            if 'qbatch' in cmd[cmdname].keys():
                qbatchcmd = '  qbatchsub.sh ' + ' '.join(cmd[cmdname]['qbatch']) + ' -- \\\n'
                runsh.write(qbatchcmd)
            if 'CallMultipleTimes' in cmd[cmdname].keys():
                for subcmd in cmd[cmdname]['CallMultipleTimes'].keys():
                    arglist = cmd[cmdname]['CallMultipleTimes'][subcmd]['arguments']
                    thiscmd = '  ' + cmdname + ' \\\n    ' + ' \\\n    '.join(arglist) + '\n'
                    runsh.write(thiscmd)
            else:
                fullcmd = '  ' + cmdname + ' \\\n    ' + ' \\\n    '.join(cmd[cmdname]['arguments']) + '\n'
                if 'IterateOverSites' in cmd[cmdname].keys():
                    for site in SiteNames:
                        thiscmd = fullcmd.replace('<site>',site)
                        runsh.write(thiscmd)
                else:
                    runsh.write(fullcmd)
            runsh.write('  )\n')

        if workflow == "data":
            ## pushing stuff to git hub
            runsh.write(
            '''
  message "Pushing QC documents to github..."
  ( # subshell invoked to handle directory change
    cd ${PROJECTDIR}
    git add qc/
    git add metadata/checklist.csv
    git add metadata/checklist.yaml
    git diff --quiet HEAD || git commit -m "Autoupdating QC documents"
  )
  ''')

            ## pushing website ness
            if (QC_Phantoms == True) & (len(SiteNames) > 1):
                runsh.write(
                '''
  message "Pushing website data to github..."
  (
    cd ${PROJECTDIR}/website
    git add .
    git commit -m "Updating QC plots"
    git push --quiet
  ) > /dev/null
  ''')

        ### tee out a log
        runsh.write('\n  message "Done."\n')
        runsh.write('} | tee -a ${PROJECTDIR}/logs/run-all-${DATESTAMP}.log\n')

        ## close the file
        runsh.close()
        os.chmod(outputfile, 0o774) ## chmod 774 in python
    del(PipelineSettings)
#
# ### change anything that needs to be changed with Find and Replace
# if config['FindandReplace'] != None :
#     with open (outputfile,'r') as runsh:
#         allrun = runsh.read()
#     for block in config['FindandReplace']:
#         toFind = block['Find']
#         toReplace = block['Replace']
#         if block['Find'] in allrun:
#             allrun = allrun.replace(block['Find'],block['Replace'])
#         else:
#             print('WARNING: could not find {} in run.sh file'.format(block['Find']))
#     with open (outputfile,'w') as runsh:
#         runsh.write(allrun)
