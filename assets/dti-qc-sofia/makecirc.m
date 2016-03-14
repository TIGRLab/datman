function circ=makecirc(N,ctrx,ctry,rad)

circ(1:N,1:N)=0;
for xx=1:N
    for yy=1:N  
        if (((xx-ctrx)^2 + (yy-ctry)^2) <= rad^2 )
                circ(xx,yy)=1;          
        end      
    end    
end