function Y=load_singleDWI_SPINS(QAdate,nslice, ndir, whichslice)
%       Use for CMH data
%		This function loads a single set or series of DW dicom files for a
%		given slice
%        ->  all raw images (b0+directions)
%      
%       Images are arranged by grad direction: first all slices at b0, then
%       all slices at 1st grad direction etc. 

% QAdate is a full path to the files
MAINDIR=QAdate;

%sprintf('started load_singleDWI')
numB0=5;

dirstart=1;
dirend=ndir;

totimages=(ndir+numB0)*nslice;
i=0;
dirpath2=strcat(MAINDIR);
files=dir(dirpath2); 
names={files.name};

% Now identify the files begining with Se
Imagefilesubscripts=strmatch('Ex', names);
Imagefilenames=names(Imagefilesubscripts);
Img1=Imagefilenames{1};
lenF=length(Imagefilenames);
% disp(strcat('There are... ',num2str(lenF),' images'))
% disp(strcat('We expect... ',num2str(totimages),' images'))

if (lenF~=totimages)
    disp(strcat('There are... ',num2str(lenF),' images'))
    disp(strcat('We expect... ',num2str(totimages),' images'))
   'not the same!'
    pause
end

% if whichslice==9
%     pause % only the first time
% end


%% start older part (June2011)
n=0;
Y=[];
for nn=1:ndir+numB0
    
    %sprintf('%s%d','direction #',nn)
% for nn=1   
%for i=whichslice:nslice:(totimages-(nslice-whichslice))
    i=whichslice+((nn-1)*nslice);
     n=n+1;

     filename = strcat(MAINDIR,Img1(1:length(Img1)-9),num2str(i,'%05d'),'.dcm');
          
    
            fid = fopen(filename,'r','b');
            if fid == -1
                error('File does not exist.') ;  
            end
        
          infodw=dicominfo(filename);
            A=dicomread(infodw);

         
   
        Y=cat(3,Y,A);
    

    fclose(fid);

    

end

