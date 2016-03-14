function Dsort=loadMPRC(dirpath,numsl,N)
%       Use for MRC data
if nargin==4
N=128; % expect 128x128 images- this will get them from the Seimens mozaic
end


dir2=dir(dirpath);
names2={dir2.name};
lnames2=length(names2);

n=0;
for i=1:lnames2
    names2{i}
    if strfind(names2{i},'Ex')==1
        n=n+1;
        names1{n}=names2{i};
    end
  
end
lnames=length(names1)

D(1:N,1:N,1:lnames,1:numsl)=0;

for i=1:lnames 
    fname=names1{i};
    info=dicominfo(strcat(dirpath,'/',fname));
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


    