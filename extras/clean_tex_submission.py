import numpy as np
import biblib.bib as bbl
import os, sys, re

####
# Run some cleaning on a tex file for a bunch of things that aren't compatible with tex2jats
# Recommended usage is to take bits and pieces that apply and tailor them for a particular article
# Things that are particularly useful might eventually get moved to a more "universal" script
#
# included here:
    # change \Cref to \ref, cases for figures and section labels
        # (and add 'Fig.' to text before the replaced figure references)
    # change \cite to \citet (useful sometimes but not always!)
    # remove \par that is not necessary
    # remove commented-out credit lines so 'people' doesn't end up in jats file
    # find \newcommand*{} macros, substitute them in the text, remove the \newcommand lines
    # change (\citeauthor, \citeyear) syntax to \citep, using bibfile to sort keys by first author
    # fix some specific cases where \SI{}{} commands are in $math$ environments
####

ifile_tex = '/path_to_tex_file.tex'
ifile_bib = '/path_to_bibfile.bib'
ofile_tex = ifile_tex.split('.tex')[0] + '_jats.tex'

# read all the text at once
f_in = open(ifile_tex,'r')
text = f_in.read()
f_in.close()

# read bibfile
parser = bbl.Parser()
biblio = parser.parse(open(ifile_bib,'r'))
ens = biblio.get_entries()

# first few things to clean, relatively easy
text = re.sub(r'\\Cref{fig',r'Fig.~\\ref{fig',text)  # clean Crefs to refs for figs
text = re.sub(r'\\Cref{',r'Section~\\ref{',text)  # clean Crefs to refs for sections
text = re.sub(r'\\cite{',r'\\citet{',text)  # cite -> citet
text = re.sub(r'\\par',r'',text)  # clean out unneeded \par terminators
text = re.sub(r'\\citeauthor{(.*?)}, ',r'',text)  # get rid of all \citeauthors, keep \citeyears

# remove CRediT roles that are unused so they don't get jats-ified
text = re.sub(r'\%\\credit{.*?}\n',r'',text)

# fix things that were Crefs with multiple figures in them
mref = re.findall(r'Fig.\~\\ref{(.*?)}',text)
for m in mref:
    if ',' in m:
        to_use = r'Figs.~'+','.join([r'\\ref{%s}' % e for e in m.split(',')])
        to_yeet = r'Fig.\~\\ref{%s}' % m
        text = re.sub(to_yeet,to_use,text)

# transate and clean all the custom macros
macros = re.findall(r'\\newcommand\*{(.*?)}{(.*?)}\n',text)
for q in macros[:-1]:  # skipping the last one bc we know it is \sh and only messes up shorttitle
    text = re.sub(re.sub(r'\\',r'\\\\',q[0]),re.sub(r'\\',r'\\\\',q[1]),text)
text = re.sub(r'\\newcommand(.*?)}\n',r'',text)

# look for all parens that have citations in them
all_parens = re.findall(r'\((.*?)\)',text)
# loop those, find all bibkeys and any prefix text (in-cite text can't be added tex'd so ignore it)
for c in all_parens:
    if re.findall(r'\\citeyear',c):
        keys = re.findall(r'\\citeyear{(.*?)}',c)
        pre_text = re.split(r'\\citeyear',c)[0].strip()

        # sort keys by actual first author so that they come out ok in jats???
        # NOTE do this on author info from bibfile instead of bibkey, key is not always last name
        auths = []
        for k in keys:
            auths.append(ens[k].authors()[0].last)
        sort_order = np.argsort([k.lower() for k in auths])
        keys = np.array(keys)

        # format the cleaned tex citation
        new_cite = r'\\citep['+pre_text+'][]{'+','.join(keys[sort_order])+'}'

        try:
            # place this new citation in the string
            to_rep = r'\('+re.sub(r'\\',r'\\\\',c)+r'\)'
            text = re.sub(to_rep,new_cite,text)
        except:
            print('FIX THIS: ', new_cite, to_rep)

# try to fix at least some cases of \SI within math environments
# NOTE specifically handles $$ math with \SI{number}{\units} in it,
# and specifically cases where the math before the \SI{}{} consists of no text or
# some variation/combination of <>='{} \delta \phi \pm \sim \approx (13 char or less)
SIms = re.findall(r"\$([\\adehilmpstrox<>=\{\}\s']{0,13})\\SI{([0-9.-]{1,4})}{(\\[a-z\%]{1,10})}\$",text)
for i in range(len(SIms)):
    actual_math = re.sub(r'\\',r'\\\\',SIms[i][0])
    val = SIms[i][1]
    unit = re.sub(r'\\',r'\\\\',SIms[i][2])
    to_yeet = r'\$%s\\SI\{%s\}{%s}\$' % (actual_math, val, unit)
    if actual_math == '':
        to_use = r'\\SI{%s}{%s}' % (val, unit)
    else:
        to_use = r'$%s$\\SI{%s}{%s}' % (actual_math, val, unit)
    text = re.sub(to_yeet,to_use,text)

# write out to cleaner tex file for jats conversion
f_out = open(ofile_tex,'w')
f_out.write(text)
f_out.close()
