function processSPINS

MAINDIR='/home/sofia/data/SPINS-QA/'
basename='SPN01_'

sitev={'CMH','MRC', 'ZHH'}

for n=1:3
    site=sitev{n}

%     for i=1:6

        
        i=8;
    
            QAdate=strcat(basename,site,'_PHA_FBN000',num2str(i)) 
            [fMRIscan,DTInoASSET,DTIwASSET]=findSPINS_QAsenums(QAdate)
    
            pause
            QAdate1=strcat(QAdate,'/scans/',fMRIscan,'/DICOM')
            QAdate2=strcat(QAdate,'/scans/',DTInoASSET,'/DICOM')
            QAdate3=strcat(QAdate,'/scans/',DTIwASSET,'/DICOM')
           
            %rename all as Ex##Se##Im## with info from dicom headers
            renameDCM_standardExSeIm(strcat(MAINDIR,QAdate1));
            renameDCM_standardExSeIm(strcat(MAINDIR,QAdate2));
            renameDCM_standardExSeIm(strcat(MAINDIR,QAdate3));
            
            DTIQA_Handout(site,QAdate2,'y')            
            DTIQA_Handout(site,QAdate3,'n')
            SPINS_fMRIQAv2(QAdate,fMRIscan)

%     end
end
close all
