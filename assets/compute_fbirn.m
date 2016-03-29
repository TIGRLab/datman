%   To perform a quantitation of snr, sfnr, stability and drift
%   includes weisskoff plot  MRM 36:643 (1996)
%
%   rev 0   3/3/00      original from noiseave and imgroi
%   rev 1   3/29/02     fix a few header things
%   rev 2   9/4/02      add weissnoise plot
%   rev 3   1/28/03     add phase drift plot
%               .freq image is scaled 10x
%   rev 4   4/1/03      for fbirn

%   acq: 35 slice 64x64 TR 3.0 TE 30 (3T) 40 (1.5T) 200 frames
%   grecons -s 18 -e 18 Pxxxxx

%% adapted to SPINS by Sofia Chavez, Sep.2014
%% modified to fit SPINS pipeline by Joseph Viviano, Jan.2015

function compute_fbirn(basepath, subj, data)

    % datapath = '/projects/spins/data/';
    % addpath('/projects/spins/code/nifti-tools')
    % subj = 'SPN01_ZHH_PHA_FBN0005';
    % data = 'SPN01_ZHH_PHA_FBN0005_03_Resting_State_212_1.nii.gz';

    qcpath = strcat(basepath, '/qc/phantom/fmri/');

    % load in the data as I4d LOL (untouched prevents scaling)
    I4d = load_untouch_nii([basepath '/data/nii/' subj '/' data]);
    I4d = I4d.img;

    % update user about subject
    disp(['fBIRN fMRI for ' subj])

    outflname=strcat(qcpath, subj, '.csv');
    fid=fopen(outflname,'w');
    count=fprintf(fid, '%s,%s,%s,%s,%s,%s,%s,%s\n', ...
                 'subj','mean','std','%fluct','drift','snr','sfnr','rdc');

    more off;
    clear roi;
    clear roir;

    % some defaults
    NPIX = 64; % NPIX = 128; %NPIX = input('npix (cr = 64) = '); % matrix
    numsl=40;
    I1 = 3403;      % first image
    I2 = 3600;      % last image
    TR = 2.0;       % rep time, s

    % parse the settings
    if(isempty(NPIX))
        NPIX = 128;
    end

    if(NPIX == 128)
        R = 30; % ROI width
    else
        R = 15; % probably 64x64
    end

    % calculate remaining constants
    npo2 = NPIX/2;
    ro2 = fix(R/2);
    X1 = npo2 - ro2;
    X2 = X1 + R - 1;
    Y1 = X1;
    Y2 = X2;
    r1 = 1;
    r2 = R;

    %  set up input and ROI mask
    mask = ones(R);
    npx = sum(sum(mask));
    img = zeros(NPIX);
    mag = zeros(NPIX);

    %% enter start and end TR
    i1 = 5; % remove the first 5 TRs to double-ensure we are stable.
    i2 = 212; % end of the run (grab this from the input dimensions).

    N = i2 - i1 + 1; % num time frames
    M = r2 - r1 + 1; % num ROI's
    roir = zeros(N, M);
    fkern = subj;
    numwin = 3;

    %  begin loop through images
    A=zeros(NPIX);
    Iodd = zeros(NPIX*NPIX,1);
    Ieven = zeros(NPIX*NPIX,1);
    Syy = zeros(NPIX*NPIX,1);
    Syt = zeros(NPIX*NPIX,1);
    St = 0;
    Stt = 0;
    S0 = 0;

    slicenum=floor(numsl/2);
    totsl=numsl;
    for j = i1:i2 %i1 and i2 are time pts

        A=squeeze(I4d(:,:,slicenum,j));

        tmpI=[];
        for xx=1:NPIX
            tmp=A(xx,1:NPIX);
            tmpI=[tmpI,tmp];
        end
        I(1:NPIX*NPIX,1)=double(tmpI(1:NPIX*NPIX));

        % record the odd and even frames seperately
        if(mod(j,2)==1)
            Iodd = Iodd + I;
        else
            Ieven = Ieven + I;
        end

        Syt = Syt + I*j;
        Syy = Syy + I.*I;
        S0 = S0 + 1;
        St = St + j;
        Stt = Stt + j*j;
        img(:) = I;
        sub = img(X1:X2,Y1:Y2);
        roi(S0) = sum(sum(sub))/npx;

        for r = r1:r2 % each roi size
            ro2 = fix(r/2);
            x1 = npo2 - ro2;
            x2 = x1 + r - 1;
            sub = img(x1:x2,x1:x2);
            roir(j-i1+1, r) = mean(sub(:));
        end

        if(numwin == 4) % do the phase
            fname = sprintf('%s.%03dp', fkern, j);
            fid = fopen(fname, 'r');
            [buf, n] = fread(fid, 'short');
            fclose(fid);
            img(:) = buf;
            phase = img*.001;
            img1 = exp(i*phase);
            z = img1./base;
            phi = atan2(imag(z), real(z));
            freq = phi/(2*pi*TE);
            sub = freq(X1:X2,Y1:Y2);
            roip(j-i1+1) = mean(sub(:));
        end
    end

    %  write out diff image
    Isub = Iodd - Ieven;
    img(:) = Isub;
    sub = img(X1:X2,Y1:Y2);
    varI = var(sub(:));

    %  write out ave image
    Sy = Iodd + Ieven;
    Iave = Sy/N;
    img(:) = Iave;
    sub = img(X1:X2,Y1:Y2);
    meanI = mean(sub(:));

    % find trend line at + b
    D = (Stt*S0 - St*St);
    a = (Syt*S0 - St*Sy)/D;
    b = (Stt*Sy - St*Syt)/D;

    % make sd image
    Var = Syy + a.*a*Stt +b.*b*S0 + 2*a.*b*St - 2*a.*Syt - 2*b.*Sy;
    Isd = sqrt(Var/(N-1));

    % make sfnr image
    sfnr = Iave./(Isd + eps);
    img(:) = sfnr;
    sub = img(X1:X2,Y1:Y2);
    sfnrI = mean(sub(:));

    snr = meanI/sqrt(varI/N);
    fprintf('\nmean, SNR, SFNR = %5.1f  %5.1f  %5.1f\n', meanI, snr, sfnrI);

    for jj = 1:NPIX
        Iaveimg(jj, 1:NPIX) = Iave((1:NPIX) + (NPIX*(jj-1)));
        Isubimg(jj, 1:NPIX) = Isub((1:NPIX) + (NPIX*(jj-1)));
        Isdimg(jj, 1:NPIX) = 10*Isd((1:NPIX) + (NPIX*(jj-1)));
        Isfnrimg(jj, 1:NPIX) = 10*sfnr((1:NPIX) + (NPIX*(jj-1)));
    end

    % generate images
    figure(1)

    subplot(2,2,1)
    imagesc(Iaveimg);
    title('Average')
    colormap(gray)
    set(gca,'DataAspectRatio',[1 1 1]);

    subplot(2,2,2)
    imagesc(Isdimg);
    title('Std')
    set(gca,'DataAspectRatio',[1 1 1]);
    colormap(gray)

    subplot(2,2,3)
    imagesc(Isubimg);
    title('Noise')
    set(gca,'DataAspectRatio',[1 1 1]);
    colormap(gray)

    subplot(2,2,4)
    imagesc(Isfnrimg, [0 4000]);
    title('SFNR')
    set(gca,'DataAspectRatio',[1 1 1]);
    colormap(gray)

    % Fluctation analysis
    x=(1:N);
    p=polyfit(x,roi,2);
    yfit = polyval(p, x);
    y = roi - yfit;

    % generate plots
    figure(2)
    subplot(numwin,1,1)
    plot(x,roi,x,yfit);
    xlabel('frame num');
    ylabel('Raw signal');
    grid
    m=mean(roi);
    sd=std(y);
    drift = (yfit(N)-yfit(1))/m;
    title(sprintf('%s   percent fluct (trend removed), drift= %5.2f %5.2f', fkern, 100*sd/m, 100*drift));

    fprintf('std, percent fluc, drift = %5.2f  %6.2f %6.2f \n', sd, 100*sd/m, 100*drift);

    z = fft(y);
    fs = 1/TR;
    nf = N/2+1;
    f = 0.5*(1:nf)*fs/nf;
    subplot(numwin,1,2);plot(f, abs(z(1:nf)));grid
    ylabel('spectrum');
    xlabel('frequency, Hz');
    ax = axis;

    text(ax(2)*.2, ax(4)*.8, sprintf('mean, SNR, SFNR = %5.1f  %5.1f  %5.1f', meanI, snr, sfnrI));

    % ROI-varied analysis
    t = (1:N);

    for r = r1:r2
        y = roir(:, r)';
        % 2nd order trend
        yfit = polyval(polyfit(t, y, 2), t);
        F(r) = std(y - yfit)/mean(yfit);
    end

    rr = (r1:r2);
    % percent
    F = 100*F;
    fcalc = F(1)./rr;
    % decorrelation distance
    rdc = F(1)/F(r2);

    subplot(numwin,1,3);
    loglog(rr, F, '-x', rr, fcalc, '--');
    grid
    xlabel('ROI full width, pixels');
    ylabel('Relative std, %');
    axis([r1 r2 .01 1]);
    text(6, 0.5, 'solid: meas   dashed: calc');
    text(6, 0.25, sprintf('rdc = %3.1f pixels',rdc));

    if(numwin==4)
        subplot(numwin,1,4);
        plot(x,roip)
        xlabel('frame num');
        ylabel('freq drift, Hz');
        grid
    end

    % print figures and txt file results
    count=fprintf(fid,'%s,%09.3f,%09.3f,%09.3f,%09.3f,%09.3f,%09.3f,%09.3f\n', subj,meanI,sd,sd*100/m,100*drift,snr,sfnrI,rdc);

    fig1name=strcat(qcpath, subj, '_fmri_qa_images.jpg');
    fig2name=strcat(qcpath, subj, '_fmri_qa_plots.jpg');

    print('-f1','-djpeg',fig1name)
    print('-f2','-djpeg',fig2name)
    close all

exit
end

