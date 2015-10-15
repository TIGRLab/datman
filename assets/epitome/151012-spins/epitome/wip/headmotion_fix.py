#!/usr/bin/env python

import fnmatch
import os
import csv

import numpy as np
import scipy as sp
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt

import nibabel as nib

## Options ###
oPre = 'func_brain'
oMsk = 'anat_EPI_brain'

oHeadSize    = 50  # head diamater in mm
oFDthresh    = 2   # We will censor runs with values over these thresholds 
oDVARSthresh = 10  # 

## ##########################################################################
f = open( oDir + "/" + oExp + "/" + "motion_corrupted_files.txt", "wb")

for subject in oSub:
    directory = os.path.join(oDir, oExp, subject, 'task_fmri/')
    for session in os.listdir(directory):
        if os.path.isdir(os.path.join(directory, session)) == True:

            count = 0

            for fileName in os.listdir(os.path.join(directory, session)):
                if fnmatch.fnmatch(fileName, oPre + '*'):
                    
                    count = count + 1

                    # load in masked data
                    dat = nib.load(os.path.join(directory, session, fileName))
                    msk = nib.load(os.path.join(directory, session, oMsk + '.nii.gz')).get_data()
                    outA = dat.get_affine()
                    outH = dat.get_header()
                    dat = dat.get_data()
                    dim = np.shape(dat)
                    dat = np.reshape(dat, (dim[0] * dim[1] * dim[2], dim[3]))
                    msk = np.reshape(msk, (dim[0] * dim[1] * dim[2]))
                    dat = dat[msk > 0, :]

                    for fileName in os.listdir(os.path.join(directory, session, 'params')):
                        if fnmatch.fnmatch(fileName, 'params_mot' + str(count) + '*'):
                            FD = np.genfromtxt(os.path.join(directory, session, 'params', fileName))

                            FD[:,0] =np.radians(FD[:,0])*oHeadSize # degrees roll to mm
                            FD[:,1] =np.radians(FD[:,1])*oHeadSize # degrees pitch to mm
                            FD[:,2] =np.radians(FD[:,2])*oHeadSize # degrees yaw to mm

                            # sum over absolute derivative for the 6 motion paramaters
                            FD = np.sum(np.abs(np.diff(FD, n=1, axis=0)), axis=1)
                            FD = np.insert(FD, 0, 0) # align FD & DVARS

                        if fnmatch.fnmatch(fileName, 'params_DVARS' + str(count) + '*'):
                            DV = np.genfromtxt(os.path.join(directory, session, 'params', fileName))
                            DV = DV / 10 # convert to % signal change
                    
                    # find TRs above both thresholds, mask TRs 1 back and 2 forward from 
                    idxFD = np.where(FD >= oFDthresh)[0]
                    idxDV = np.where(DV >= oDVARSthresh)[0] 
                    idxC = np.union1d(idxFD, idxDV)
                    idxC = np.union1d(np.union1d(np.union1d(idxC - 1, idxC), idxC + 1), idxC + 2)

                    if idxC.size > 0:
                        if np.max(idxC) > dim[3]:
                            idxC[np.where(idxC > dim[3])[0]] = dim[3]
                            idxC = np.unique(idxC)

                    if idxC.size < dim[3] / 10:

                        idx = 0
                        # for all elements in the censor index
                        while idx <= len(idxC) - 1: 
                            # if there is room for a sequence
                            while idx <= len(idxC) - 2: 
                                # and we find a sequence
                                if idxC[idx] + 1 == idxC[idx + 1]: 
                                    # set the lower bound
                                    idxLo = idxC[idx]

                                    # find the upper bound
                                    while idxC[idx] + 1 == idxC[idx + 1]: 
                                        idx = idx + 1
                                        #if we hit the end of the sequence
                                        if idxC[idx] == idxC[-1]:
                                            # set the upper bound
                                            idxHi = idxC[idx]
                                            idx = idx + 1
                                            break
                                    else:
                                        # set the upper bound
                                        idxHi = idxC[idx] 
                                        idx = idx + 1
                            
                                else:
                                    # if this isn't a sequence, upper and lower bounds are equal
                                    idxLo = idxC[idx] 
                                    idxHi = idxC[idx]
                                    idx = idx + 1
                                
                                for x in np.arange(len(dat)):
                                    # create interpolate over boundaries
                                    if idxHi < dim[3]-1 and idxLo > 0:
                                        vec = np.array([idxLo - 1, idxHi + 1]) # set the bound indicies
                                        fxn = interp1d(np.arange(len(vec)), dat[x, vec], kind='linear')
                                        new = fxn(np.linspace(0, len(vec) - 1, len(vec) + 1 + (idxHi - idxLo)))
                                    
                                        # delete the first & last values, wrtie interp values over data
                                        new = np.delete(new, [0, len(new)-1])
                                        dat[x, idxLo:idxHi + 1] = new

                                    # if our censor vector goes beyond acquisition on either side
                                    elif idxLo <= 0 and idxHi < dim[3]-1:
                                        # insert idxHi into earlier TRs
                                        new = np.repeat(dat[x, idxHi+1], idxHi) # < fixed
                                        dat[x, 0:idxHi] = new

                                    elif idxHi >= dim[3]:
                                        # insert idxLo into later TRs
                                        new = np.repeat(dat[x, idxLo-1] ,dim[3] - idxLo)
                                        dat[x, idxLo:dim[3] + 1] = new

                            # now do the final value, if it wasn't in a sequence [is this still relevant?]
                            if idx <= len(idxC) - 1:
                                # this isn't a sequence, so these are equal 
                                idxLo = idxC[idx]
                                idxHi = idxC[idx]
                                idx = idx + 1

                                for x in np.arange(len(dat)):
                                    # create interpolate over boundaries
                                    if idxHi < dim[3]:
                                        vec = np.array([idxLo - 1, idxHi + 1]) 
                                        fxn = interp1d(np.arange(len(vec)), dat[x, vec], kind='linear')
                                        new = fxn(np.linspace(0, len(vec) - 1, len(vec) + 1 + (idxHi-idxLo)))
                                
                                        # delete the first & last values, wrtie interp values over data
                                        new = np.delete(new, [0, len(new) - 1]) 
                                        dat[x, idxLo:idxHi + 1] = new
                                        print('this just happened!')

                                    # if our censor vector goes beyond acquisition
                                    else:
                                        # repeat the last good value
                                        new = np.repeat(dat[x, idxLo-1] ,dim[3] - idxLo)
                                        dat[x, idxLo:dim[3] + 1] = new
                                        print('this just happened!')                                    

                    else:
                        # write offending file name out to report
                        f.write('subject ' + str(subject) + ' run ' + str(count) + ' has > 10/100 corrupted TRs \n')
                        # and skip scrubbing

                    out = np.zeros((dim[0]*dim[1]*dim[2], dim[3]))
                    out[msk > 0, :] = dat 
                    out = np.reshape(out, (dim[0], dim[1], dim[2], dim[3]))
                    out = nib.nifti1.Nifti1Image(out, outA, outH)
                    out.to_filename(os.path.join(directory, session, 
                                                'func_scrubbed' + str(count) + '.nii.gz'))

                    # update us and continue the loop
                    print('subject ' + subject + ' run ' + str(count) + ' complete')

f.close() # write out the report