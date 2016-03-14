function renameDCM_standardExSeIm(pname)

% MAINDIR='~/MATLAB/prgms/multi-site-NIH-AV/'

if nargin==0
    pname=uigetdir('~/data/SPINS-QA/')
end

dirp=dir(pname);
fnamesp={dirp.name}
fname=fnamesp{3};
% 

% [fname,pname]=uigetfile('~/data/SPINS-QA/')

filename=strcat(pname,'/',fname)

info=dicominfo(filename);
% Exnum=str2double(info.StudyID)
Exnum=str2num(info.StudyID)

    if isempty(Exnum)|| strcmp(Exnum,'NaN')
        Exnum=1;
    end
    Exnum
Senum=info.SeriesNumber
Imnum=info.InstanceNumber;
whos *num
name_old=fname
name_old_base=name_old(1:1)
name_new=strcat('Ex',num2str(Exnum,'%05d'),'Se',num2str(Senum,'%05d'),'Im',num2str(Imnum,'%05d'),'.dcm')

if strcmp(name_old,name_new)
    'nothing to rename'
    return
end

dir2=dir(pname);
fnames={dir2.name};
length(fnames)
% pause
n=0;
for i=1:length(fnames)
    tmp=fnames{i};
 
    if ~isempty(strfind(tmp,name_old_base));
        n=n+1;
        fnamesbase{n}=tmp;
        
    end
end

'number of files to rename:..'
numfiles=n
pause(0.2)

for i=1:numfiles
    name_old=fnamesbase{i}
    info=dicominfo(fullfile(pname,name_old));
    info.StudyID
   
    Exnum=str2num(info.StudyID);
    if isempty(Exnum)
        Exnum=1;
    end
    Senum=info.SeriesNumber;
    Imnum=info.InstanceNumber
%     whos *num
%     pause
    name_new=strcat('Ex',num2str(Exnum,'%05d'),'Se',num2str(Senum,'%05d'),'Im',num2str(Imnum,'%05d'),'.dcm')
%     pause
%     oldfname=strcat(pname,'/',name_old)
   
      
    oldfname=fullfile(pname,name_old)
    newfname=fullfile(pname,name_new)
    movefile(oldfname,newfname)
    
%     pause
end
