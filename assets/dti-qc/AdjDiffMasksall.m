function [averadpixsh,maxradpixsh,avecolpixsh,SigM] = AdjDiffMasksallv2(site,DWI,ndir)

[Nx,Ny,numimgs]=size(DWI)
nb0=numimgs-ndir

%Mojdeh added to fix the lenfill check
lenfill_mult=Nx/128


nrow=9;
ncol=8;
N=Nx;
mask=DWI*0;
lenfillb0(1:nb0)=0;

for i=1:ndir+nb0
    i
    DWItmp=DWI(:,:,i);
    DWItmpsm=medfilt2(DWItmp,[11 11]);
    DWItmpsm2=medfilt2(DWItmpsm,[11 11]);

    switch site
        case {'BYC'}
            DWItmpsm2=medfilt2(DWItmpsm,[5 5]);
            DWItmpsm3=medfilt2(DWItmpsm2,[5 5]);
            figure(1000); imagesc(DWItmpsm3);
            DWItmpsm=DWItmpsm3;
            e=edge(DWItmpsm, 'canny');
            figure(1001); imagesc(e);

        otherwise
            e=edge(DWItmpsm,'canny'); %finds lots of edges
    end

    e(1:15,:)=0;
    e(:,1:15)=0;
    e(N-15:N,:)=0;
    e(:,N-15:N)=0;
    radc=30;
    circ=makecirc(N,N/2,N/2,radc);
    e(find(circ))=0; % remove some central edges from 'canny'

    ef2=imfill(e,[N/2,N/2]); % flood from central points (to overcome closed edges within phantom)
    lenfill=length(find(ef2))
    if i<nb0+1
        lenfillb0(i)=lenfill;
        AVElenfill=mean(lenfillb0(find(lenfillb0)));
    end
    se=strel('disk',3,0);

    %Mojdeh: changed the >7000 to >(7000*lenfill_mult*lenfill_mult) ...
    lenfill_mult*lenfill_mult
    if lenfill>(7000*lenfill_mult*lenfill_mult)
        % all got filled so border is not closed
        e2=imdilate(e,se);
        locations=find(circ);
        ef2=imfill(e2,locations);
        ef2=imfill(ef2,'holes');
        ef2=imerode(ef2,se); % erode the first imdilate around phantom
        lenfill=length(find(ef2))
        lenfillb0(i)=lenfill;
        AVElenfill=mean(lenfillb0(find(lenfillb0)));
        if lenfill>(7000*lenfill_mult*lenfill_mult)
            e2=imdilate(e,se);% try to dilate x2
            e2=imdilate(e2,se);
            ef2=imfill(e2,locations);
            ef2=imerode(ef2,se); % erode x2
            ef2=imerode(ef2,se);
            lenfill=length(find(ef2))
            if i==1
                lenfillb0(i)=lenfill;
                AVElenfill=lenfill;
            end
        end
    end

    %Mojdeh: uncommented for debugging ... comment out when done
    figure (130)
    subplot(1,2,1)
    imagesc(e)
    axis image
    subplot(1,2,2)
    imagesc(ef2)

    if lenfill<AVElenfill*0.97
            figure(999)
            imagesc(ef2)
            title('first pass')
            axis image
            clear locations circ
            radc=radc+2;
            circ=makecirc(N,N/2,N/2,radc);
            locations=find(circ);
            ef3=imfill(ef2,locations);
            lenfill=length(find(ef3))

            imagesc(ef3)
            title('second pass')
            axis image
        lenfill=length(find(ef3))
        if lenfill>(7000*lenfill_mult*lenfill_mult)
                ef3d=imdilate(ef2,se);% try to dilate x2
                ef3d=imdilate(ef3d,se);
                ef3f=imfill(ef3d,locations);
                ef3f=imerode(ef3f,se); % erode x2
                ef3f=imerode(ef3f,se);
                lenfill=length(find(ef3f))
                imagesc(ef3f)
                title('with double dilation')
                axis image
                ef3=ef3f;
        end

        while lenfill<AVElenfill*0.97
            'still not full'
            clear locations circ
            radc=radc+2
            circ=makecirc(N,N/2,N/2,radc);
            locations=find(circ);
            ef3f=imfill(ef3,locations);
            lenfill=length(find(ef3f))
            if lenfill>(7000*lenfill_mult*lenfill_mult)
                ef3d=imdilate(ef3,se);% try to dilate x2
                ef3d=imdilate(ef3d,se);
                ef3f=imfill(ef3d,locations);
                ef3f=imerode(ef3f,se); % erode x2
                ef3f=imerode(ef3f,se);
                lenfill=length(find(ef3f))
                imagesc(ef3f)
                title('with double dilation')
                axis image
            end
            pause(0.5)
            imagesc(ef3f)
            axis image
            ef3=ef3f;
        end
        ef2=ef3;
    end
    ef=ef2;

    ef1=imerode(ef,se); % erode outer edges
    ef2=imdilate(ef1,se); % get back the phantom edge
    ef2=imfill(ef2,'holes'); % fill any leftover holes in phantom
    lenfill=length(find(ef2));
    if lenfill>(7000*lenfill_mult*lenfill_mult)
            %Mojdeh added for debugging ... remove once done!
            figure(278)
            subplot(1,2,1)
            imagesc(e)
            axis image
            subplot(1,2,2)
            imagesc(ef2)
    end

    if i<nb0+1, lenfillb0(i)=lenfill
        AVElenfill=mean(lenfill(find(lenfill)))
    end

    figure(333)
    subplot(2,4,1)
    imagesc(DWItmpsm)
    title(['image #',num2str(i)])
    axis image
    subplot(2,4,2)
    imagesc(e)
    axis image
    subplot(2,4,3)
    imagesc(ef1)
    axis image
    subplot(2,4,4)
    imagesc(ef2)
    axis image

    diff1=ef-ef1;
    subplot(2,4,7)
    imagesc(diff1)
    axis image
    diff2=ef-ef2;
    subplot(2,4,8)
    imagesc(diff2)
    axis image

    mask(:,:,i)=ef2(:,:);
end

SigM=mask;

for i=1:numimgs
    DY(:,:,i)=abs(SigM(:,:,i)-SigM(:,:,1));
    clear tmp
    tmp(:,:)=DY(:,:,i);
    tmp2=tmp;
    tmp2(find(tmp==2))=0;
    DY(:,:,i)=tmp2(:,:);
end

clear tmp*

figure(1)

for i=1:numimgs
    subplot(nrow,ncol,i)
    imagesc(SigM(:,:,i))
    set(gca,'fontsize',6)
    title(['Image #',num2str(i)])
    colormap(gray)
    axis image
    axis off
end
figure(2)
for i=2:numimgs
    subplot(nrow,ncol,i)
    imagesc(DY(:,:,i))
    set(gca,'fontsize',6)
    title(['Image #',num2str(i)])
    colormap(gray)
    axis image
    axis off
end

% find radial mask thickness
numrad=[];
whichrad=[];
nntotmax=[];
angstep=2;
numradlines=length([1:angstep:359]);
Mask1=mask(:,:,1);

[rmask,cmask]=find(Mask1);
rmaskmin=min(rmask)
rmaskmax=max(rmask)
radx=(rmaskmax-rmaskmin)/2
%Mojdeh: changed /128 to /Nx to take care of images with different
%dimensions
xlen=radx+floor(5*Nx/128)
xctr=rmaskmin+radx;

cmaskmax=max(cmask)
cmaskmin=min(cmask)
rady=(cmaskmax-cmaskmin)/2
%Mojdeh: changed /128 to /Nx to take care of images with different
%dimensions
ylen=rady+(5*Nx/128)
yctr=cmaskmin+rady;

PhantomCentre=[xctr,yctr]
PhantomB0Dist=rady/radx

for i=2:numimgs
    tmp(:,:)=DY(:,:,i);
    [nrad,wrad,nm]=checkradpixsh(tmp,angstep,xlen);
    numrad(i)=nrad;
    whichrad{i}=wrad(:);
    nntotmax{i}=nm(:);
    clear nrad wrad nm
end

% plots
averadpixsh(2:numimgs)=0;
maxradpixsh(2:numimgs)=0;
for i=2:numimgs
    % find the max pixshift value for each grad dir and the radial line with max pixel shift
    clear tmp
    tmp=nntotmax{i};
    [maxpixsh,maxradnj]=max(tmp);
    maxnumpixshift(i)=maxpixsh;
    whrad=whichrad{i};
    maxradj(i)=whrad(maxradnj);
    if maxradj(i)>0, maxang(i)=(maxradj(i)-1)*angstep; else, maxang(i)=0; end
    maxradpixsh(i)=max(tmp);
end

figure(3)
for i=2:numimgs
    tmp=nntotmax{i};
    whrad=whichrad{i};
    subplot(nrow,ncol,i-1)
    plot(whrad(:)*angstep,tmp,'o','MarkerEdgeColor','k','MarkerSize',2)
    set(gca,'fontsize',6)
    set(gca,'XTick',0:180:360)
    axis([0 numradlines*angstep 0 max(maxradpixsh)])
    title(['maxpixsift=',num2str(maxnumpixshift(i)),' @',num2str(maxang(i)),'\circ','\fontsize{6}'])
    averadpixsh(i)=mean(tmp);
end

clear tmp nntot*

%% go thru each col and find #adj mask pixels for thickness along y

for i=2:numimgs
    tmp(:,:)=DY(:,:,i);
    for cj=1:Ny
        n(cj)=0;
        ntot=[];
        for rj=1:Nx
            if tmp(rj,cj)==1
                 n(cj)=n(cj)+1;
            elseif n(cj)>0
                ntot=[ntot n(cj)];
                n(cj)=0;
            end
        end
        nntot{cj}=ntot;
    end
    ncj=0;
    for cj=1:Ny
        if nntot{cj}
            ncj=ncj+1;
            col(i,ncj)=cj;
            nntotmax(i,ncj)=max(nntot{cj});
        end
    end
    numcol(i)=ncj;
end

avecolpixsh(1:numimgs)=0;
figure(4)
for i=2:numimgs
    subplot(nrow,ncol,i-1)
    tmp(3:numcol(i)-2)=nntotmax(i,3:numcol(i)-2);
    plot(col(i,3:numcol(i)-2),nntotmax(i,3:numcol(i)-2),'o','MarkerSize',2,'MarkerEdgeColor','k') % omit ends where phantom edge is vertical
    set(gca,'fontsize',6)
    axis([floor(N*0.1) floor(N*0.9) 0 10])

    if isempty(tmp(3:numcol(i)-2))
        avecolpixsh(i)=0;
        maxcolpixsh(i)=0;
    else
        avecolpixsh(i)=mean(tmp(3:numcol(i)-2));
        maxcolpixsh(i)=max(tmp(3:numcol(i)-2));
    end

    if i< nb0+1
        title(['b=0 #',num2str(i)])
    else
        title([' grad dir#',num2str(i-nb0)])
    end

end

figure(5)
plot(averadpixsh,'b*-')
title(['Pixel Shifts Due to Eddy Currents for Phantom with ctr @[',num2str(PhantomCentre(1)),',',num2str(PhantomCentre(2)),'] and B0Dist=',num2str(PhantomB0Dist)])
hold on
plot(maxradpixsh,'b*--') % gives info about a large pixel shift which may be lost in average
hold on
plot(avecolpixsh,'r*-') % don't plot max pix shift for col because misleadingly large at vertical boundaries
legend('ave radial pixsh','max radial pixsh','ave column pixsh')

