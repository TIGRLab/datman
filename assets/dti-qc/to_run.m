mylist = dir('BYC01*')

for i=1:length(mylist)
myfile=mylist(i).name
eval(['cd ' myfile '/scans'])
myscan=dir('*-PAR')
QAdate=strcat(myfile, '/scans/', myscan(1).name)
cd ../../
DTIQA_Handout_moj_SGEversion('BYC',QAdate,'n')

eval(['cd ' myfile '/scans'])
myscan=dir('*-NPAR')
QAdate=strcat(myfile, '/scans/', myscan(1).name)
cd ../../
DTIQA_Handout_moj_SGEversion('BYC',QAdate,'y')
end