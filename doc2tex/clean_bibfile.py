import biblib.bib as bbl
from argparse import ArgumentParser
from collections import OrderedDict
import numpy as np
import os, re, sys

####
# check a bibtex file against a tex file and clean out any unused references in the bib file
# writes out 2 files: clean bib file (*_clean.bib) and a file with the unused entries (junk.bib or name provided)
# before cleaning, checks for duplicate bib keys and exits if any are found

# usage:
    # python3 clean_bibfile.py -b best_bibfile.bib -t copyedited_texfile.tex [-n excess_entries.bib]
####

parser = ArgumentParser()
parser.add_argument('--bibfile','-b',type=str,help='path to bib file')
parser.add_argument('--texfile','-t',type=str,help='path to tex file')
parser.add_argument('--nahfile','-n',type=str,help='path to file for unused entries',default='junk.bib')
args = parser.parse_args()

# make sure there are inputs, warn for overwrite
in_bib = args.bibfile
assert in_bib is not None, 'input bibfile needed (-b)'
in_tex = args.texfile
assert in_tex is not None, 'input texfile needed (-b)'
o_clean = in_bib.rstrip('.bib') + '_clean.bib'
print('output will be in %s (good entries) and %s (unused entries)' % (o_clean,args.nahfile))
if os.path.isfile(args.nahfile):
    input('%s already exists and will be overwritten [hit enter to continue]' % args.nahfile)
if os.path.isfile(o_clean):
    input('%s already exists and will be overwritten [hit enter to continue]' % o_clean)

f = open(in_bib,'r')
text = f.read()
f.close()

items = text.split('@')[1:]

# check for duplicate keys:
keys = [i.split('{')[1].split('\n')[0] for i in items]

un,counts = np.unique(keys,return_counts=True)
if np.any(counts > 1):
    print('duplicated keys found:')
    for k in un[counts>1]:
        print(k)
    sys.exit()

bib_used = OrderedDict()    # for the entries that *should* be in the file
bib_rogue = OrderedDict()   # for the entries that are not referenced in the tex

# read the tex file as one long string
with open(in_tex,'r') as file:
    all_tex_text = file.read()
cks = ','.join(re.findall(r'cite.{(.*?)}',all_tex_text)).split(',')  # join and split for individual keys
cks2 = ','.join(re.findall(r'cite.\[.*?\]{(.*?)}',all_tex_text)).split(',')  # for cite* with pre and/or post text
cks3 = ','.join(re.findall(r'cite{(.*?)}',all_tex_text)).split(',')  # for cite without p or t in case authors used those
cks.extend(cks2)
cks.extend(cks3)
cks = [e.lstrip().rstrip() for e in cks]

# loop items in bibfile and see if the key is in the tex file
for bibitem in items:
    parser = bbl.Parser()
    try:
        q = parser.parse('@' + bibitem)
        key = list(q.get_entries().keys())[0]
        if key in cks:
            bib_used[key] = q.get_entries()[key]
        else:
            bib_rogue[key] = q.get_entries()[key]
    except:  # if we catch something here, it means there is a badly formed entry in the bib file
        print(bibitem)
        print('check your commas, brackets, parens, keys, etc')
        sys.exit()


# write things out
# first write out the *unused* entries in a separate file in case we need them later
with open(args.nahfile, 'w') as f:
    for key in bib_rogue.keys():
        f.write(bib_rogue[key].to_bib())
        f.write('\n')

# then write a new clean bib file with only the entries that are actually used
with open(o_clean, 'w') as f:
    for key in bib_used.keys():
        f.write(bib_used[key].to_bib())
        f.write('\n')
