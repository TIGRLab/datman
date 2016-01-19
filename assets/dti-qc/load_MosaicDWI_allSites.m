function Dsort=load_MosaicDWI_allSites(dirpath_alldcms,numsl,N)

% Use to read in mosaic-format dicom files
% N=128; % expect 128x128 images - this will get them from the Seimens mozaic

files=dir(dirpath_alldcms);
names2={files.name};


% Mojdeh added this part
n=1;
for i=1:length(names2)
    fname=names2{i};
    if ~files(i).isdir
        names3(n)=names2(i);
        n=n+1;
    end            
end

names=names3;
lnames=length(names)

D(1:N,1:N,1:lnames,1:numsl)=0;

for i=1:lnames 
    fname=names{i};
    info=dicominfo(strcat(dirpath_alldcms,'/',fname));
    A=dicomread(info);
    Ntot=length(A);
    numImgperRow=Ntot/N;
    rv=-N+1:0;
    

    for j=1:numsl
       
        if rem(j-1,numImgperRow)==0
            rv=rv+N;
            cv=[1:N];
        else
            cv=cv+N;
        end
        Atmp(1:N,1:N)=A(rv,cv);
        D(1:N,1:N,i,j)=Atmp(1:N,1:N);
    end
    
end

Dsort=D;


    