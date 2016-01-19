% extract 2 sets of of 2 consecutive middles slices (ie. 2 central slices 
    % (odd+even #) and the next 2 (odd+even#) ) and later take the average 
    % of each two consecutive slices (this is needed instead to correct for 
    % the interleaved acquisition (sometimes called "blinds" that might happen 
    % in some scans. In this case if you simply subtract two consecutive images 
    % without averaging you will see a shift away from 0 in the mean noise 
    
    
    
%     Also, for a better comparison, I was thinking that it would be good to overlay the histograms of:
% 1) average of 3 slices in first and second B0
% 2) average of three consecutive slices,twice, in first B0
% with the same scales... also, maybe replot with histogram centered on the ave value along x.

% yes, thanks! you sent me the 2 following files on Friday last week:
% 1) noise_BYC_calcs_from_diff2B0oneANDtwoSofiaMethod_NPAR.tif 
% 2) noise_CAM_calcs_from_diff2Cons3sliceAvg_B01_NPAR.tif
% 
% so one for BYC and for CAMH... so I couldn't compare.
% 
% Now I have both data made up of averaging over 3 slices at CAMH so it is a good comparison.
% So, we are comparing across b=0 to within a single one.
% 
% I think the noise stats for that looks good, very close: 
% 1) diff2B0oneANDtwoSofiaMethod_NPAR: ave/std/noiseratio=0.73/42.57/0.02
% 2) diff2Cons3sliceAvg_B01: ave/std/noiseratio=1.15/47.27/0.02
% 
% Do you have the same measure for diff2B0oneANDthreeSofiaMethod? or for twoANDthree?
% What about those same measures for another site?
    
  std_noise=zeros(1,3);
  mean_noise=zeros(1,3);
  noise_ratio=zeros(1,3);

    B0_1=Y_all_B0_CAM(:,:,:,1);
    B0_2=Y_all_B0_CAM(:,:,:,2);
    B0_3=Y_all_B0_CAM(:,:,:,3);
   
           
        
%       if there are N slices in the scan: ctrsl= floor(N/2), so ave slices: ctrl-2,ctrsl-1,ctrsl and then average: ctrsl+1, ctrsl+2,ctrsl+3 and look at the difference between those 2 averaged images.
        sc=floor(nsl/2);
        num2avg=3;
        
        %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
        B0_1_S3_5=B0_1(:,:,(sc-(num2avg-1)):sc);
        B0_1_S6_8=B0_1(:,:,(sc+(num2avg-2)):(sc+num2avg));    
        
        B0_2_S3_5=B0_2(:,:,(sc-(num2avg-1)):sc);
        B0_2_S6_8=B0_2(:,:,(sc+(num2avg-2)):(sc+num2avg));
        
        B0_3_S3_5=B0_3(:,:,(sc-(num2avg-1)):sc);
        B0_3_S6_8=B0_3(:,:,(sc+(num2avg-2)):(sc+num2avg));
        
        %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
        B0_1_mean_S3_5=mean(B0_1_S3_5,3);
        B0_1_mean_S6_8=mean(B0_1_S6_8,3);
        
        B0_2_mean_S3_5=mean(B0_2_S3_5,3);
        B0_2_mean_S6_8=mean(B0_2_S6_8,3);
        
        B0_3_mean_S3_5=mean(B0_3_S3_5,3);
        B0_3_mean_S6_8=mean(B0_3_S6_8,3);
        
        %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
        B0_1_2S(:,:,1)=B0_1_mean_S3_5;
        B0_1_2S(:,:,2)=B0_1_mean_S6_8;
        
        B0_2_2S(:,:,1)=B0_2_mean_S3_5;
        B0_2_2S(:,:,2)=B0_2_mean_S6_8;
        
        B0_3_2S(:,:,1)=B0_3_mean_S3_5;
        B0_3_2S(:,:,2)=B0_3_mean_S6_8;
        
        %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
        %first B0
        
        B0_2S=B0_1_2S;
        [Nx, Ny, numS]=size(B0_2S); 
    
        % difference of the 2 means (each mean of two consecutive odd and even
        % slices from the centre)
        Diff_B0(1:Nx,1:Ny)=double(B0_2S(1:Nx,1:Ny,2)-B0_2S(1:Nx,1:Ny,1));

        %creating an ROI in the centre (a circle centered on (64,64) with r=35)
        phantrad=35*(Nx/128);
        N2=floor(Nx/2);
        noisemskctr=makecirc(Nx,N2,N2,phantrad);

        %masking out the region of the difference image in the circle ROI
        nd2=Diff_B0(find(noisemskctr));
            
        std2ALL=std(nd2);
        ave2ALL=mean(nd2);
            
        noiseratio=ave2ALL/std2ALL;
        [nd2hist,xhist2]=hist(nd2,20);
            
            
        figure(201)
        subplot(2,2,1)
            imagesc(Diff_B0(1:Nx,1:Ny))
            axis image
            axis off
            title(['DiffImg of 2 Mean of 3 Consecutive Centre Slices of B0 #1'])
    
        subplot(2,2,2)
            XX=Diff_B0(1:Nx,1:Ny);
            XX(find(noisemskctr==0))=0;
            %masked noise region 
            imagesc(XX)
            axis image
            axis off
        subplot(2,2,3)
            plot(nd2)
            title(['ave(noise)=',num2str(ave2ALL,'%5.2f'),' std(noise)=',num2str(std2ALL,'%5.2f'),' noiseratio=',num2str(noiseratio,'%5.2f')])
        subplot(2,2,4)
            plot(xhist2,nd2hist)
            title('noise histogram')
            
        std_noise(1,1)=std2ALL;
        mean_noise(1,1)=ave2ALL;
        noise_ratio(1,1)=noiseratio;
        
        %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
        %second B0    
        B0_2S=B0_2_2S;
        [Nx, Ny, numS]=size(B0_2S); 
    
        % difference of the 2 means (each mean of two consecutive odd and even
        % slices from the centre)
        Diff_B0(1:Nx,1:Ny)=double(B0_2S(1:Nx,1:Ny,2)-B0_2S(1:Nx,1:Ny,1));

        %creating an ROI in the centre (a circle centered on (64,64) with r=35)
        phantrad=35*(Nx/128);
        N2=floor(Nx/2);
        noisemskctr=makecirc(Nx,N2,N2,phantrad);

        %masking out the region of the difference image in the circle ROI
        nd2=Diff_B0(find(noisemskctr));
            
        std2ALL=std(nd2);
        ave2ALL=mean(nd2);
            
        noiseratio=ave2ALL/std2ALL;
        [nd2hist,xhist2]=hist(nd2,20);
            
            
        figure(202)
        subplot(2,2,1)
            imagesc(Diff_B0(1:Nx,1:Ny))
            axis image
            axis off
            title(['DiffImg of 2 Mean of 3 Consecutive Centre Slices of B0 #2'])
    
        subplot(2,2,2)
            XX=Diff_B0(1:Nx,1:Ny);
            XX(find(noisemskctr==0))=0;
            %masked noise region 
            imagesc(XX)
            axis image
            axis off
        subplot(2,2,3)
            plot(nd2)
            title(['ave(noise)=',num2str(ave2ALL,'%5.2f'),' std(noise)=',num2str(std2ALL,'%5.2f'),' noiseratio=',num2str(noiseratio,'%5.2f')])
        subplot(2,2,4)
            plot(xhist2,nd2hist)
            title('noise histogram')
         
        std_noise(1,2)=std2ALL;
        mean_noise(1,2)=ave2ALL;
        noise_ratio(1,2)=noiseratio;    
        %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
        %third B0    
        B0_2S=B0_3_2S;
        [Nx, Ny, numS]=size(B0_2S); 
    
        % difference of the 2 means (each mean of two consecutive odd and even
        % slices from the centre)
        Diff_B0(1:Nx,1:Ny)=double(B0_2S(1:Nx,1:Ny,2)-B0_2S(1:Nx,1:Ny,1));

        %creating an ROI in the centre (a circle centered on (64,64) with r=35)
        phantrad=35*(Nx/128);
        N2=floor(Nx/2);
        noisemskctr=makecirc(Nx,N2,N2,phantrad);

        %masking out the region of the difference image in the circle ROI
        nd2=Diff_B0(find(noisemskctr));
            
        std2ALL=std(nd2);
        ave2ALL=mean(nd2);
            
        noiseratio=ave2ALL/std2ALL;
        [nd2hist,xhist2]=hist(nd2,20);
            
            
        figure(203)
        subplot(2,2,1)
            imagesc(Diff_B0(1:Nx,1:Ny))
            axis image
            axis off
            title(['DiffImg of 2 Mean of 3 Consecutive Centre Slices of B0 #3'])
    
        subplot(2,2,2)
            XX=Diff_B0(1:Nx,1:Ny);
            XX(find(noisemskctr==0))=0;
            %masked noise region 
            imagesc(XX)
            axis image
            axis off
        subplot(2,2,3)
            plot(nd2)
            title(['ave(noise)=',num2str(ave2ALL,'%5.2f'),' std(noise)=',num2str(std2ALL,'%5.2f'),' noiseratio=',num2str(noiseratio,'%5.2f')])
        subplot(2,2,4)
            plot(xhist2,nd2hist)
            title('noise histogram')
            
            
        std_noise(1,3)=std2ALL;
        mean_noise(1,3)=ave2ALL;
        noise_ratio(1,3)=noiseratio;