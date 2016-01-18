function cleanM=cleanmask(M,val)
% remove detached pixels from a mask- keep only those that have neighbours
[Nx,Ny]=size(M);
cleanM=M;
 
for rr=1:Nx
    for cc=1:Ny          
        if (M(rr,cc)==val)
                   
            % check neighbours    
            rup=rr+1;      
            cup=cc+1;  
            rdown=rr-1; 
            cdown=cc-1;
                       
            if (rup>Nx), rup=rup-Nx; end
            
            if (cup>Ny), cup=cup-Ny; end
            
            if (rdown<1), rdown=rdown+Nx; end
            
            if (cdown<1), cdown=cdown+Ny; end
                    
            tot1=0;
            tot2=0;
            tot3=0;
            tot4=0;
            if M(rup,cc)==val, tot1=1;  end       
            if M(rdown,cc)==val, tot2=1; end
            if M(rr,cup)==val, tot3=1; end
            if M(rr,cdown)==val, tot4=1; end
            
            sumneighb1=tot1+tot2;
            sumneighb2=tot3+tot4;
                        
            
            if (sumneighb1==0)||(sumneighb2==0), cleanM(rr,cc)=0; end
            
            
        end
        
    end
end


    
    % figure
    % subplot(2,1,1)
    % colormap(gray);
    % set(gca,'DataAspectRatio',[1 1 1])
    % imagesc(M);
    % subplot(2,1,2)
    % colormap(gray);
    % set(gca,'DataAspectRatio',[1 1 1])
    % imagesc(cleanM);
