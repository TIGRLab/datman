function [DTInoASSET,DTIwASSET]=findSPINS_QAsenumsv2(QAdate)

MAINDIR='/home/schavez/data/SPINS-QA/'
% up to and containing the Ex#####Se## directory

% scrsz=get(0,'ScreenSize')


MAINDIR2=strcat(MAINDIR,QAdate,'/');

dir2=dir(strcat(MAINDIR2,'scans'));
dir2fnames={dir2.name}

for l=3:length(dir2fnames)
    l
    testscannum=dir2fnames{l}
    testdata=dir(strcat(MAINDIR2,'scans/',testscannum,'/DICOM/'));
    testdataname={testdata.name}
    testname=strcat(MAINDIR2,'scans/',testscannum,'/DICOM/',testdataname{3})
    testinfo=dicominfo(testname);
    testinfo.SeriesDescription
    if ~isempty(strfind(testinfo.SeriesDescription,'DTI'))
        if ~isempty(strfind(testinfo.SeriesDescription,'NO'))
            DTInoASSET=testscannum;
            ExnumDTInoASSET=testinfo.StudyID;
        else
            DTIwASSET=testscannum;
            ExnumDTIwASSET=testinfo.StudyID;
        end
    end
 
end

% site=QAdate(7:9)
% 
% % pause
% QAdate2=strcat(QAdate,'/scans/',DTInoASSET,'/DICOM')
% SPINS_DTIQAv3(site,QAdate2)
% 
% QAdate3=strcat(QAdate,'/scans/',DTIwASSET,'/DICOM')
% SPINS_DTIQAv3(site,QAdate3)



