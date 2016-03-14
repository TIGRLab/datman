function [nd,tmp]=noisedist_DTISmask(Y,Smask);
% added signal mask that gets passed in to remove any pixels from phantom
% so that can safely move away from edges and avoid phantom signal
% if phantom is postioned strangely some day


%define roi regions
%lenY=length(Y);

[Nx,Ny]=size(Y)

 % use preset regions of noise
 
 
 roi1_r1=floor((Nx/512)*150);
 roi1_r2=floor((Nx/512)*350); 
 roi1_c1=floor((Ny/512)*25);
 roi1_c2=floor((Ny/512)*65);
 
 roi2_r1=floor((Nx/512)*150);
 roi2_r2=floor((Nx/512)*350); 
 roi2_c1=floor((Ny/512)*440);
 roi2_c2=floor((Ny/512)*480);
 

%  
 maxval=max(max(Y))*.8;

% make ROIs

roimsk=zeros(Nx,Ny);
roimsk(roi1_r1:roi1_r2, roi1_c1:roi1_c2)=1;
roimsk(roi2_r1:roi2_r2, roi2_c1:roi2_c2)=1;

roimsk(find(Smask))=0; % remove any pixels that belong to the signal from phantom
 
nd=Y(find(roimsk));



