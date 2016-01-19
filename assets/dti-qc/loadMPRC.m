function Dsort=loadMPRC(dirpath_alldcms,numsl,N)
%       Use for MRC data
%Mojdeh: commented out ... not sure what was the purpose!
% if nargin==4
% N=128; % expect 128x128 images- this will get them from the Seimens mozaic
% end


files=dir(dirpath_alldcms);
names2={files.name};
%lnames2=length(names2);


% Mojdeh: added the next two lines instead of the the next commented block
% this ignores the first two enteries of names2: . and .. 
% Note that the MAINDIR2 should only contain the dicom files
% if you have any other directoried and files here, move
% them to somewhere else before running this code
% I had to do this for now since the naming pattern of the dicom files is
% different for each site

% names=names2(3:length(names2));
% lnames=length(names); 

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

% n=0;
% for i=1:lnames2
%     names2{i}
%     %Mojdeh: changed Ex to MR
%     if strfind(names2{i},'MR')==1
%     %if strfind(names2{i},'Ex')==1
%         n=n+1;
%         names1{n}=names2{i};
%     end
%   
% end
% lnames=length(names1);

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


    