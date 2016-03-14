function processSPINS

MAINDIR='/home/schavez/data/SPINS-QA/'
basename='SPN01_'

sitev={'CMH','MRC', 'ZHH'}

for n=1:3
    site=sitev{n}

    istart=1;
    iend=3;
    
    if n==1 
        istart=45; 
        iend=47;      
    elseif n==2
        istart=50;
        iend=51;
    else
        istart=46;
        iend=47;
    end
%         
% istart=40;
% iend=40;

        for i=istart:iend % loops through the desired dates to process
           i          
%         i=8;
    
            QAdate=strcat(basename,site,'_PHA_FBN',num2str(i,'%04d')) 
            
%             if (n==1) && (i==6)
%                 % DTInoASSET doesn't exist
%                 DTInoASSET=num2str(0);
%                 DTIwASSET=num2str(5);
%             else
                [DTInoASSET,DTIwASSET]=findSPINS_QAsenumsv2(QAdate)
%             end
        
            
            QAdate2=strcat(QAdate,'/scans/',DTInoASSET,'/DICOM')
            QAdate3=strcat(QAdate,'/scans/',DTIwASSET,'/DICOM')
           
            %rename all as Ex##Se##Im## with info from dicom headers
%             if (n==1) && (i==6)
%                 renameDCM_standardExSeIm(strcat(MAINDIR,QAdate3));
%             else
                renameDCM_standardExSeIm(strcat(MAINDIR,QAdate2));
                renameDCM_standardExSeIm(strcat(MAINDIR,QAdate3));
%             end
            
            if (n==2) && ((i==22)||(i==25))
%                  SPINS_DTIQA_PartApixshifts(site,QAdate3,'n')
                SPINS_DTIQAv3(site,QAdate3,'n')  
            else
%                 SPINS_DTIQA_PartApixshifts(site,QAdate2,'y')            
%                 SPINS_DTIQA_PartApixshifts(site,QAdate3,'n')
                SPINS_DTIQAv3(site,QAdate2,'y')  
                SPINS_DTIQAv3(site,QAdate3,'n')  
            

            end
            

        end
end
close all
