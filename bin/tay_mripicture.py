#!/usr/bin/env python

"""
Creates MRI axial pictures for custom t-shirt for TAY cohort study. 
"""

import glob
import matplotlib.pyplot as plt
import numpy as np

# Specify Participant ID
SUBJ = 'TAY01_CMH_P99999_01'

# Input and Output Directories
INDIR = '/external/rprshnas01/tigrlab/archive/data-2.0/TAY/qc/'
OUTDIR = '/external/mgmt3/imaging/home/kimel/jwong/Tshirt/'

def main(): 
    # Set Path
    IMGPATH_WC = ''.join([INDIR,SUBJ,'/*Sag-MPRAGE-T1.png'])
    IMGPATH = glob.glob(IMGPATH_WC)[0]
    OUTPATH = ''.join([OUTDIR,SUBJ,'_T1.png'])

    # Crop Image and Remove Direction Label
    final = plt.imread(IMGPATH)[800:1290,:,:]
    final[:,0:10,:]=0
    final[:,205:220,:]=0
    final[:,410:425,:]=0
    final[:,620:635,:]=0
    final[:,830:845,:]=0
    final[:,1040:1055,:]=0
    final[:,1245:1260,:]=0

    # Output Image
    plt.figure(num=None, figsize=(10, 10), dpi=300, facecolor='w', edgecolor='k')
    plt.axis('off')
    plt.imshow(final)
    plt.savefig(OUTPATH,bbox_inches='tight', pad_inches=0)

if __name__ == "__main__":
    main()
