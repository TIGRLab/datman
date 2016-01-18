function [numrad,whichrad,nntotmax]=checkradpixsh(Y,angstep,radlen)

%'in checkradpixsh'

[Nx,Ny]=size(Y);


rc=floor(Nx/2);
cc=floor(Ny/2);
xlen=radlen;
x=[0:xlen];
nn=0;

% figure
% tmp=Y;
% imagesc(tmp)
% colormap('gray')
% colorbar
% maxval=max(max(tmp))*1.2;

for ang=0:angstep:359
        angrad=ang*pi/180;
        y=sin(angrad).*x;
        xadd=cos(angrad).*x;
        r=rc+y;
        c=cc+xadd;
        nn=nn+1;
        radlin{nn}=[round(r)',round(c)'];
        % draw a line to view it
%         for i=1:xlen
%             tmp(round(r(i)),round(c(i)))=maxval;
%         end
%         imagesc(tmp)
%         pause
end 

for i=1:nn
      n(i)=0;
      ntot=[];
     radrc=radlin{i};
     
      for ln=1:xlen
        rln=radrc(ln,1);
        cln=radrc(ln,2);
        if rln>Nx, rln=Nx; end
        if cln>Ny, cln=Ny; end
        
       
        if Y(rln,cln)==1
            n(i)=n(i)+1;
 %           tmp(rln,cln)=2;
%             imagesc(tmp)
%             pause
        elseif n(i)>0
            ntot=[ntot n(i)];
             n(i)=0;
             
        end
      nntot{i}=ntot;
      end
      
  end
  
 
    nj=0;
    whichrad=0;
    nntotmax=0;
    for j=1:nn
        if nntot{j}
            nj=nj+1;
            whichrad(nj)=j;            
            nntotmax(nj)=max(nntot{j});
        end
    end  
     numrad=nj;
     
     
  