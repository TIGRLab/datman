    % extract 2 sets of of 2 consecutive middles slices (ie. 2 central slices 
    % (odd+even #) and the next 2 (odd+even#) ) and later take the average 
    % of each two consecutive slices (this is needed instead to correct for 
    % the interleaved acquisition (sometimes called "blinds" that might happen 
    % in some scans. In this case if you simply subtract two consecutive images 
    % without averaging you will see a shift away from 0 in the mean noise 
        
%       if there are N slices in the scan: ctrsl= floor(N/2), so ave slices: ctrl-2,ctrsl-1,ctrsl and then average: ctrsl+1, ctrsl+2,ctrsl+3 and look at the difference between those 2 averaged images.
        sc=floor(nsl/2);
        B0_S3_5=squeeze(Dsort(:,:,1,(sc-2):sc));
        B0_S6_8=squeeze(Dsort(:,:,1,(sc+1):(sc+3)));    
        
        
        B0_mean_S3_5=mean(B0_S3_5,3);
        B0_mean_S6_8=mean(B0_S6_8,3);
        B0_2S(:,:,1)=B0_mean_S3_5;
        B0_2S(:,:,2)=B0_mean_S6_8;
            
        
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
            
            
        figure(200)
        subplot(2,2,1)
            imagesc(Diff_B0(1:Nx,1:Ny))
            axis image
            axis off
            title(['DiffImg of 2 Mean of 3 Consecutive Centre Slice of B0#'])
    
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
            
            
            
            %         size(Dsort)

%         %% case of more than one B0 ... this is for testing purposes only 
%         B0_1=all_B0s(:,:,:,1);
%         B0_2=all_B0s(:,:,:,2);
%         B0_3=all_B0s(:,:,:,3);
%         
%         B0_1_S4_S5=B0_1(:,:,(sc-1):sc);
%         B0_1_S6_S7=B0_1(:,:,(sc+1):(sc+2));
%         B0_1_mean_S4_5=mean(B0_1_S4_S5,3);
%         B0_1_mean_S6_7=mean(B0_1_S6_S7,3);
%         B0_2S(:,:,1)=B0_1_mean_S4_5;
%         B0_2S(:,:,2)=B0_1_mean_S6_7;
% 
%         
%         B0_2_S4_S5=B0_2(:,:,(sc-1):sc);
%         B0_2_S6_S7=B0_2(:,:,(sc+1):(sc+2));
%         B0_2_mean_S4_5=mean(B0_2_S4_S5,3);
%         B0_2_mean_S6_7=mean(B0_2_S6_S7,3);
%         B0_2S(:,:,1)=B0_2_mean_S4_5;
%         B0_2S(:,:,2)=B0_2_mean_S6_7;
%  
%         B0_3_S4_S5=B0_3(:,:,(sc-1):sc);
%         B0_3_S6_S7=B0_3(:,:,(sc+1):(sc+2));
%         B0_3_mean_S4_5=mean(B0_3_S4_S5,3);
%         B0_3_mean_S6_7=mean(B0_3_S6_S7,3);
%         B0_2S(:,:,1)=B0_3_mean_S4_5;
%         B0_2S(:,:,2)=B0_3_mean_S6_7;
        %%
        
        
%         B0_mean_S4_5=mean(B0_S4_S5,3);
%         B0_mean_S6_7=mean(B0_S6_S7,3);
%         B0_2S(:,:,1)=B0_mean_S4_5;
%         B0_2S(:,:,2)=B0_mean_S6_7;