function nd=noisedistNyqSmask(Y,Smask);
% added signal mask that gets passed in to remove any pixels from phantom
% so that can safely move away from edges and avoid phantom signal
% if phantom is postioned strangely some day
% Mojdeh: excluded tmp from the output which was redundant

%define roi regions
%lenY=length(Y);

[Nx,Ny]=size(Y)


 % use preset regions of noise
 
 
 roi1_r1=floor((Nx/512)*40);
 roi1_r2=floor((Nx/512)*80); 
 roi1_c1=floor((Ny/512)*65);
 roi1_c2=floor((Ny/512)*175);
 
 roi2_r1=floor((Nx/512)*440);
 roi2_r2=floor((Nx/512)*480); 
 roi2_c1=floor((Ny/512)*65);
 roi2_c2=floor((Ny/512)*175); 
 
 roi3_r1=floor((Nx/512)*40);
 roi3_r2=floor((Nx/512)*80); 
 roi3_c1=floor((Ny/512)*340);
 roi3_c2=floor((Ny/512)*450);
 
 roi4_r1=floor((Nx/512)*440);
 roi4_r2=floor((Nx/512)*480); 
 roi4_c1=floor((Ny/512)*340);
 roi4_c2=floor((Ny/512)*450);
 

maxval=max(max(Y))*.8;

% make ROIs

roimsk=zeros(Nx,Ny);
roimsk(roi1_r1:roi1_r2, roi1_c1:roi1_c2)=1;
roimsk(roi2_r1:roi2_r2, roi2_c1:roi2_c2)=1;
roimsk(roi3_r1:roi3_r2, roi3_c1:roi3_c2)=1;
roimsk(roi4_r1:roi4_r2, roi4_c1:roi4_c2)=1;
% 

roimsk(find(Smask))=0; % remove any pixels that belong to the signal from phantom

tmp=roimsk;
 
nd=Y(find(roimsk));

