#!/usr/bin/env python

import sys, os
from copy import copy

# template text used to generate each post note Y2K+100 BUG!
HEADER = """\
---
category: {imagetype}
title: {imagetype} 20{date}
tags: [{imagetype}]
---
{imagetype} plots for the 20 previous scans at each site. Multiple scans per \
week denotes multiple uploads that week.
"""

BODY = """\
<figure>
    <a href="{{{{ production_url }}}}/spins/assets/images/{imagetype}/{fname}">\
<img src="{{{{ production_url }}}}/spins/assets/images/{imagetype}/{fname}"></a>
</figure>

"""

def filter_posted(files, dates):
    """
    This removes files containing any of the dates supplied in the filename.
    """
    for date in dates:
        files = filter(lambda x: date not in x, files)

    return files

def get_unique_dates(files, begin=2, end=10):
    """
    Gets all the unique dates in a list of input files. Defined as a region 
    of the input file that begins at 'begin' and ends and 'end.'
    """
    dates = copy(files)
    for i, f in enumerate(files):
        dates[i] = f[begin:end]
    dates = list(set(dates))

    return dates

def get_posted_dates(base_path):
    """
    This gets all of the currently posted dates from the website.
    """
    try:
        posts = os.listdir(base_path + '/website/_posts/')
        posts = get_unique_dates(posts, 2, 10)

    except:
        print("""Bro, you don't even have a website.""")
        sys.exit()

    return posts

def get_new_files(base_path, dates):
    """
    This gets the output pdfs for the adni, fmri, and dti qc plots, and 
    returns each as a list. If a type of these outputs does not exist for
    a given study, we return None for that type.

    We also filter out any of these that have already been posted.
    """
    try:
        adni = os.listdir(base_path + '/data/qc/phantom/adni')
        adni = filter(lambda x: '.pdf' in x, adni)
        adni = filter_posted(adni, dates)
        adni.sort()

        if len(adni) == 0:
            adni = None
    except:
        adni = None

    try:
        fmri = os.listdir(base_path + '/data/qc/phantom/fmri')
        fmri = filter(lambda x: '.pdf' in x, fmri)
        fmri = filter_posted(fmri, dates)
        fmri.sort()

        if len(fmri) == 0:
            fmri = None
    except:
        fmri = None

    try:
        dti = os.listdir(base_path + '/data/qc/phantom/dti')
        dti = filter(lambda x: '.pdf' in x, dti)
        dti = filter_posted(dti, dates)
        dti.sort()

        if len(dti) == 0:
            dti = None
    except:
        dti = None

    return adni, fmri, dti

def get_imagetype_from_filename(filename):
    """
    Determines the type of plot from the filename.
    """
    if 'adni' in filename.lower():
        imagetype = 'adni'
    elif 'fmri' in filename.lower():
        imagetype = 'fmri'
    elif 'dti' in filename.lower():
        imagetype = 'dti'
    else:
        print('ERROR: Unknown input file ' + f)
        imagetype = None

    return imagetype

def convert_to_web(base_path, files):
    """
    Converts .pdfs to .pngs in the website folder. Also changes the associated
    filenames to contain the new file extensions.
    """
    for i, f in enumerate(files):
        imagetype = get_imagetype_from_filename(f) 
        cmd = ('convert '
               '{base_path}/data/qc/phantom/{imagetype}/{f} '
               '{base_path}/website/assets/images/{imagetype}/{out_f}'.format(
                    base_path=base_path, imagetype=imagetype, 
                    f=f, out_f=f[:-4] + '.png'))
        os.system(cmd)
        files[i] = f[:-4] + '.png'

    return files

def create_posts(base_path, files):
    """
    Loops through unique dates, and generates a jekyll post for each one using
    all of the images from that date.
    """
    imagetype = get_imagetype_from_filename(files[0])
    dates = get_unique_dates(files, 0, 8)

    for date in dates:
        
        current_files = filter(lambda x: date in x, files)

        # NB: Y2K+100 BUG
        post_name = '{base_path}/website/_posts/{date}-{imagetype}.md'.format(
                        base_path=base_path, 
                        date='20' + date, 
                        imagetype=imagetype)
        
        # write header, loop through files, write body for each
        f = open(post_name, 'wb')
        f.write(HEADER.format(imagetype=imagetype, date=date))
        for fname in current_files:
             f.write(BODY.format(imagetype=imagetype, fname=fname))
        f.close()

        print('Wrote page for ' + imagetype + ' ' + date + '.')

def main(base_path):

    # finds all of the dates we've already posted
    dates = get_posted_dates(base_path)

    # gets a list of all the unposted pdfs
    adni, fmri, dti = get_new_files(base_path, dates)

    # converts uncopied pdfs to website, converts to .png, generates markdown
    if adni:
        print('converting ADNI')
        adni = convert_to_web(base_path, adni)
        create_posts(base_path, adni)

    if fmri:
        print('converting fMRI')
        fmri = convert_to_web(base_path, fmri)
        create_posts(base_path, fmri)

    if dti:
        dti = convert_to_web(base_path, dti)
        create_posts(base_path, dti)

if __name__ == '__main__':

    base_path = os.path.dirname(os.path.realpath(sys.argv[0]))[:-4]
    print(base_path)
    main(base_path)
