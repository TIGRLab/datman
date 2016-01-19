function [Y,Y_all_B0]=load_singleDWI_allSites(dirpath_alldcms,nslice, ndir, nb0, whichslice)
%       Use for ZHH data
%		This function loads a single set or series of DW dicom files for a
%		given slice
%        ->  all raw images (b0+directions)
%      
%       Images are arranged by grad direction: first all slices at b0, then
%       all slices at 1st grad direction etc. 

% dirpath_alldcms is a full path to the files

% 
% dirstart=1;
% dirend=ndir;

totimages=(ndir+nb0)*nslice

files=dir(dirpath_alldcms);
names2={files.name};

% Mojdeh: ignore the first two enteries of names2: . and .. 
% note that for now the "dirpath_alldcms" should only contain the dicom
% files ... if you have any other directoried and files here, move
% them to somewhere else before running this code ... this might need to be
% fixed later depending on the data structure we are going to use.

n=1;
for i=1:length(names2)
    fname=names2{i};
    if ~files(i).isdir
        names3(n)=names2(i);
        n=n+1;
    end            
end

names=names3;
lenF=length(names);

% check to see if the number of files in the directory matches the expected
% total number of images 
if (lenF~=totimages)
    disp(strcat('There are... ',num2str(lenF),' images'))
    disp(strcat('We expect... ',num2str(totimages),' images'))
    'wrong number of image files!'
    pause
end


% (0020,1002) Images In Acquisition — overall number of slices in acquisition
% (0020,0013) Instance Number — a counter from 1 to the value of (0020,1002) Images In Acquisition
% (0020,1041) Slice Location —gives you the slice location in scanner space
% 
% - use the dicominfo Matlab function to read the header, 
% - check for whether this is a DTI scan using (0008,103E) Series Description
% - Find the rest of slices which belong to this acquisition by matching (0020,000e) Series Instance UID
% - if you encounter a file whose (0008,103E) Series Description is “DTI" but (0020,000e) Series Instance UID is different, you have several identically named scans - throw an error or handle that
% 
% You can pass through all the files to collect a cell array of file names, a vector of Instance Numbers and Slice Locations. After collecting this info, you can find the number of slices in one volume/direction (by looking at unique Slice Locations), find the middle slices (by sorting unique SliceLocations and using InstanceNumber to tell you which direction/volume they belong to).



% reading in all dicom files in the directory 
for i=1:length(names)
    filename = strcat(dirpath_alldcms,names{i});
    infodcms{i}=dicominfo(filename);
    sliceNums(i)=infodcms{i}.InstanceNumber;    %(0020,0013) Instance Number — a counter from 1 to the value of (0020,1002)=Total Images In Acquisition
    sliceLocs(i)=infodcms{i}.SliceLocation;     %(0020,1041) Slice Location —gives you the coordinate of slice location in scanner space  

end

% sliceLocs
% sliceNums
sliceLocsUnique=unique(sliceLocs);

if (nslice~=length(sliceLocsUnique))
    disp(strcat('There are... ',num2str(sliceLocsUnique),' unique slice locations'))
    disp(strcat('We expect... ',num2str(nslice),' slices'))
    'number of slices entered does not match the number of unique slice locations in the dicom header!'
    pause
end

% assuming the dicom files as stored sequentially 
n=0;
Y=[];

for nn=1:ndir+nb0
    i=whichslice+((nn-1)*nslice)
    n=n+1;
    A=dicomread(infodcms{i});
    Y=cat(3,Y,A);
end


Y_all_B0=[];
for nn=1:nb0
    Y_B0=[];
    nn
    for i=1:nslice
        i
        s=i+((nn-1)*nslice);
        s
        A_B0=dicomread(infodcms{s});
        size(A_B0);
        Y_B0=cat(3,Y_B0,A_B0);
        size(Y_B0)
    end
    Y_all_B0=cat(4,Y_all_B0,Y_B0);
    size(Y_all_B0)
end



