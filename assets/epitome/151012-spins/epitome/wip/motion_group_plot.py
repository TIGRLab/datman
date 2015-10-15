#!/usr/bin/env python

import fnmatch
import os
import csv

import numpy as np
import scipy as sp
from scipy.stats import ttest_ind
import matplotlib.pyplot as plt

oG1 = ['ATOL_301', 'ATOL_302', 'ATOL_304', 'ATOL_305', 'ATOL_307', 'ATOL_308', 
       'ATOL_309', 'ATOL_311', 'ATOL_312', 'ATOL_313', 'ATOL_316', 'ATOL_317', 
       'ATOL_319', 'ATOL_320', 'ATOL_321', 'ATOL_322', 'ATOL_323', 'ATOL_324']
oG2 = ['ATOL_401', 'ATOL_403', 'ATOL_404', 'ATOL_405', 'ATOL_407', 'ATOL_408', 
       'ATOL_409', 'ATOL_411', 'ATOL_412', 'ATOL_413', 'ATOL_414', 'ATOL_415', 
       'ATOL_416', 'ATOL_418', 'ATOL_419', 'ATOL_420', 'ATOL_421', 'ATOL_422']

oHeadSize = 50   # head diamater in mm
oG1Name = 'group 300'
oG2Name = 'group 400'
oFDThresh = 2  
oDVThresh = 10 
oPubQuality = 0    # set to 1 for dpi = 300

########################################################################

report = {}

## Group 1 Framewise Displacement & DVARS ##
g1FD = []
g1DV = []
g1Keys = []
for subject in oG1:
    directory = os.path.join(oDir, oExp, subject, 'task_fmri/')
    for session in os.listdir(directory):
        if os.path.isdir(os.path.join(directory, session)) == True:
            for fileName in os.listdir(os.path.join(directory, session, 'params')):  
                
                if fnmatch.fnmatch(fileName, 'params_mot*'):
                    f = np.genfromtxt(os.path.join(directory, session, 'params', fileName))
                    # convert degrees (roll, pitch, yaw) to mm
                    f[:,0] =np.radians(f[:,0])*oHeadSize
                    f[:,1] =np.radians(f[:,1])*oHeadSize
                    f[:,2] =np.radians(f[:,2])*oHeadSize
                    # take the sum of the absolute derivative
                    f = np.abs(np.diff(f, n=1, axis=0))
                    f = np.sum(f, axis=1)
                    g1FD.append(f)

                if fnmatch.fnmatch(fileName, 'params_DVARS*'):
                    f = np.genfromtxt(os.path.join(directory, session, 'params', fileName))
                    f = f[1:] / 10 # remove the zero at the beginning and convert to % signal change
                    g1DV.append(f)
                    g1Keys.append(subject)
       
g1FD = np.array(g1FD, dtype=np.float64)
g1DV = np.array(g1DV, dtype=np.float64)

## Group 2 Framewise Displacement % DVARS ##
g2FD = []
g2DV = []
g2Keys = []
for subject in oG2:
    directory = os.path.join(oDir, oExp, subject, 'task_fmri/')
    for session in os.listdir(directory):
        if os.path.isdir(os.path.join(directory, session)) == True:
            for fileName in os.listdir(os.path.join(directory, session, 'params')):
                
                if fnmatch.fnmatch(fileName, 'params_mot*'):
                    f = np.genfromtxt(os.path.join(directory, session, 'params', fileName))        
                    # convert degrees (roll, pitch, yaw) to mm
                    f[:,0] =np.radians(f[:,0])*oHeadSize
                    f[:,1] =np.radians(f[:,1])*oHeadSize
                    f[:,2] =np.radians(f[:,2])*oHeadSize
                    # take the sum of the absolute derivative
                    f = np.abs(np.diff(f, n=1, axis=0))
                    f = np.sum(f, axis=1)
                    g2FD.append(f)

                if fnmatch.fnmatch(fileName, 'params_DVARS*'):
                    f = np.genfromtxt(os.path.join(directory, session, 'params', fileName))
                    f = f[1:] / 10 # remove the zero at the beginning and convert to % signal change
                    g2DV.append(f)
                    g2Keys.append(subject)

g2FD = np.array(g2FD, dtype=np.float64)
g2DV = np.array(g2DV, dtype=np.float64)

## Generate a Report for each group
g1Vec = []
g1Sum = []

for x in np.arange(len(g1FD[:, 1]) - 1):
    
    # find TRs above both thresholds, mask TRs 1 back and 2 forward from 
    idxFD = np.where(g1FD[x,:] >= float(oFDThresh))[0]
    idxDV = np.where(g1DV[x,:] >= float(oDVThresh))[0] 
    idxC = np.union1d(idxFD, idxDV)
    idxC = np.union1d(np.union1d(np.union1d(idxC - 1, idxC), idxC + 1), idxC + 2)

    g1Vec.append(len(idxC))
    if report.get(g1Keys[x], 'None') == 'None':
        report[g1Keys[x]] = []
        report[g1Keys[x]].append(len(idxC))
    else:
        report[g1Keys[x]].append(len(idxC))

g1Sum = sum(g1Vec)

g2Vec = []
g2Sum = []

for x in np.arange(len(g2FD[:, 1]) - 1):
    
    # find TRs above both thresholds, mask TRs 1 back and 2 forward from 
    idxFD = np.where(g2FD[x,:] >= float(oFDThresh))[0]
    idxDV = np.where(g2DV[x,:] >= float(oDVThresh))[0] 
    idxC = np.union1d(idxFD, idxDV)
    idxC = np.union1d(np.union1d(np.union1d(idxC - 1, idxC), idxC + 1), idxC + 2)

    g2Vec.append(len(idxC))
    if report.get(g2Keys[x], 'None') == 'None':
        report[g2Keys[x]] = []
        report[g2Keys[x]].append(len(idxC))
    else:
        report[g2Keys[x]].append(len(idxC))

g2Sum = sum(g2Vec)

# Write out report on # of TRs removed per subject
if os.path.isfile(os.path.join(oDir, oExp, 'motion_report.txt')) == True:
    os.remove(os.path.join(oDir, oExp, 'motion_report.txt'))
out = open(os.path.join(oDir, oExp, 'motion_report.txt'), 'w')
for subject in report:
    print>>out, subject + ', ' + str(report[subject])
out.close()

###########################################################################
## Calculate some statistics ##
# Number of runs per group
n1 = np.shape(g1FD)[0]
n2 = np.shape(g2FD)[0]

# Mean and standard deviation per time point
mFD1 = np.mean(g1FD, axis=0)
mFD2 = np.mean(g2FD, axis=0)
mDV1 = np.mean(g1DV, axis=0)
mDV2 = np.mean(g2DV, axis=0)

sFD1 = np.std(g1FD, axis=0)
sFD2 = np.std(g2FD, axis=0) 
sDV1 = np.std(g1DV, axis=0) 
sDV2 = np.std(g1DV, axis=0) 

t = np.arange(len(mDV1))

# Group-Wise total DVARS / Displacement over run
motion = [np.sum(g1FD, axis = 1), np.sum(g2FD, axis = 1)]
DVARS = [np.sum(g1DV,  axis = 1), np.sum(g2DV,  axis = 1)]

# t-test 1: Total motion over run
[t1, p1] = ttest_ind(motion[0], motion[1], equal_var=True)

# t-test 2: Total DVARS over run
[t2, p2] = ttest_ind(DVARS[0], DVARS[1], equal_var=True)

# t-test 3: 
[t3, p3] = ttest_ind(g1Vec, g2Vec, equal_var=True)

if os.path.isfile(os.path.join(oDir, oExp, 'stats_report.txt')) == True:
    os.remove(os.path.join(oDir, oExp, 'stats_report.txt'))
out = open(os.path.join(oDir, oExp, 'stats_report.txt'), 'w')
print>>out, 'total motion: t=' + str(t1) + ', p=' + str(p1)
print>>out, 'total DVARS: t=' + str(t2) + ', p=' + str(p2)
print>>out, 'number of removed TRs: t=' + str(t3) + ', p=' + str(p3)  
out.close()

##############################################################################
## Plot statistics over runs ##
if oPubQuality == 1:
    fig1, ax = plt.subplots(nrows=1, ncols=2, figsize=(12, 4), dpi=300, facecolor='white')
else:
    fig1, ax = plt.subplots(nrows=1, ncols=2, figsize=(12, 4), dpi=72, facecolor='white')

ax[0].plot(t, mFD1, lw=2, label=oG1Name, color='blue')
ax[0].plot(t, mFD2, lw=2, label=oG2Name, color='green')
ax[0].fill_between(t, mFD1 + sFD1, mFD1, facecolor='blue', alpha=0.25)
ax[0].fill_between(t, mFD2 + sFD2, mFD2, facecolor='green', alpha=0.25)
#ax[0].fill_between(t, mFD1+sFD1, mFD1-sFD1, facecolor='blue', alpha=0.25)
#ax[0].fill_between(t, mFD2+sFD2, mFD2-sFD2, facecolor='green', alpha=0.25)
#ax[0].set_title('Group Framewise Displacement $\mu$ and $\pm \sigma$')
ax[0].set_title('Group Framewise Displacement $\mu$ and $\sigma$')
lg = ax[0].legend(loc='upper right', fontsize=10)
lg.draw_frame(False)
ax[0].set_xlabel('Time (TRs)')
ax[0].set_ylabel('Framewise Displacement (mm/TR)')
ax[0].tick_params(axis='both', which='both', size=10)
ax[0].set_xlim([0, len(t)-1])
xTicks = np.linspace(0, len(t), 5)
xTicks[-1] = xTicks[-1] - 1
ax[0].set_xticks(xTicks)
ax[0].set_xticklabels((xTicks+1).astype(np.int))
#ax[0].grid()

ax[1].plot(t, mDV1, lw=2, label=oG1Name, color='blue')
ax[1].plot(t, mDV2, lw=2, label=oG2Name, color='green')
ax[1].fill_between(t, mDV1 + sDV1, mDV1, facecolor='blue', alpha=0.25)
ax[1].fill_between(t, mDV2 + sDV2, mDV2, facecolor='green', alpha=0.25)
#ax[1].fill_between(t, mDV1+sDV1, mDV1-sDV1, facecolor='blue', alpha=0.25)
#ax[1].fill_between(t, mDV2+sDV2, mDV2-sDV2, facecolor='green', alpha=0.25)
#ax[1].set_title('Group DVARS $\mu$ and $\pm \sigma$')
ax[1].set_title('Group DVARS $\mu$ and $\sigma$')
lg = ax[1].legend(loc='upper right', fontsize=10)
lg.draw_frame(False)
ax[1].set_xlabel('Time (TRs)')
ax[1].set_ylabel('DVARS (% signal change/TR)')
ax[1].tick_params(axis='both', which='both', size=10)
ax[1].set_xlim([0, len(t)-1])
xTicks = np.linspace(0, len(t), 5)
xTicks[-1] = xTicks[-1] - 1
ax[1].set_xticks(xTicks)
ax[1].set_xticklabels((xTicks + 1).astype(np.int))
#ax[1].grid()

#fig1.savefig(os.path.join(oDir, oExp, 'group_FD_DVARS_timeseries.tiff'))
fig1.savefig(os.path.join(oDir, oExp, 'group_FD_DVARS_timeseries.pdf'))

## Boxplot: Total Motion ##
if oPubQuality == 1:
    fig2, ax = plt.subplots(nrows=1, ncols=2, figsize=(12, 4), dpi=300, facecolor='white')
else:
    fig2, ax = plt.subplots(nrows=1, ncols=2, figsize=(12, 4), dpi=72, facecolor='white')

ax[0].boxplot(motion)
ax[0].set_title('Total Framewise Displacement per Group')
ax[0].set_ylabel('Total Framewise Displacement (mm)')
ax[0].tick_params(axis='both', which='both', size=10)
ax[0].set_xticklabels([str(oG1Name), str(oG2Name)])

ax[1].boxplot(DVARS)
ax[1].set_title('Total DVARS per Group')
ax[1].set_ylabel('Total DVARS (% signal change)')
ax[1].tick_params(axis='both', which='both', size=10)
ax[1].set_xticklabels([str(oG1Name), str(oG2Name)])

#fig2.savefig(os.path.join(oDir, oExp, 'group_FD_DVARS_total.tiff'))
fig2.savefig(os.path.join(oDir, oExp, 'group_FD_DVARS_total.pdf'))

## Boxplot: # of deleted TRs ##
if oPubQuality == 1:
    fig3, ax = plt.subplots(nrows=1, ncols=1, figsize=(12, 4), dpi=300, facecolor='white')
else:
    fig3, ax = plt.subplots(nrows=1, ncols=1, figsize=(12, 4), dpi=72, facecolor='white')

ax.boxplot([g1Vec, g2Vec])
ax.set_title('Number of TRs Scrubbed per Run')
ax.set_ylabel('Number of TRs')
ax.tick_params(axis='both', which='both', size=10)
ax.set_xticklabels([str(oG1Name), str(oG2Name)])

#fig3.savefig(os.path.join(oDir, oExp, 'group_scrubbed_total.tiff'))
fig3.savefig(os.path.join(oDir, oExp, 'group_scrubbed_total.pdf'))

## JDV Jul 16 2013 ##