import biblib.bib as bbl
from biblib.messages import InputError
import dateutil.parser as dp
import sce_utils.utils as scu
import numpy as np
from habanero import Crossref
from argparse import ArgumentParser
from collections import OrderedDict, Counter
from urllib.request import Request, urlopen, HTTPError
import os, sys, re

####
# clean up bibtex file produced by anystyle *or* a bib file provided by an author
    # try to find dois where they are missing
    # get nice citations from doi.org when we do have dois
    # neaten up all bibtex entries (date/year, pages, url)
        # if docx/odt parsing, create standardized entry keys for matching
        # if from tex template, use --keepkeys or -k flag to keep the initial entry keys
    # fallback on all queries (crossref and doi.org) is to keep the input entry

# Usage: 
    # python3 fix_bibtex.py -i path/to/input.bib -o path_to_output.bib [-k]

# TODO format terminal printing/inputs better (\033[1m and \033[0m for bold)
# TODO actually un-tex/html-escape special characters from doi.org bibtex entries?
    # like &lt; and {\'{e}} or whatever (this tends to come up with authors and titles)
    # for now this is taken care of by option to keep old entry title and/or authors
# TODO do we really need to keep page number info? tends to be poorly curated/mixed bag
# TODO query limit 5 or so, options for scrolling back and forth before choosing a ref (or not)
####

parser = ArgumentParser()
parser.add_argument('--ifile','-i',type=str,help='path to input bib file')
parser.add_argument('--ofile','-o',type=str,help='path to output bib file')
parser.add_argument('--keepkeys','-k',action='store_true',help='flag to retain input bib entry keys for output')
parser.add_argument('--nosearch','-n',action='store_true',help='flag to not do any crossref querying')
args = parser.parse_args()

in_bib = args.ifile
if in_bib == None:
    in_bib = input('Enter path to input file: ') or 'refs.bib'
assert os.path.isfile(in_bib),'input bibfile does not exist'
out_bib = args.ofile
if out_bib == None:
    of1 = in_bib[:-4]+'_corr.bib'
    out_bib = input('Enter path to output file, or skip to use %s: ' % of1) or of1 
if os.path.isfile(out_bib):
    iq = input('warning: %s already exists. Overwrite? [y]/n: ' % out_bib) or 'y'
    if iq == 'n':
        sys.exit()

########################################################################
# Part 0: load entries, and check for trailing apostrophes
########################################################################

parser = bbl.Parser()  # parser for bibtex
parsed = parser.parse(open(in_bib,'r'))  # parse the input file with biblib
# get entries
bib_OD = parsed.get_entries()   # returns collections.OrderedDict

# check if all the titles end with an apostrophe; if so, probably an error and they need to 
# be removed (anystyle is not great with titles in quotes)
last_char = np.array([bib_OD[key]['title'][-1] for key in bib_OD])
strp_last = False
lc = Counter(last_char)
if max(lc.values()) >= len(last_char)/2:  # this is a red flag, most entries have the same end char
    print('title trailing characters:')
    for i,k in enumerate(lc.keys()):
        print('[%i] %i instances of %s' % (i,lc[k],k))
    irem = int(input('enter index to remove: ') or -1)
    if irem >= 0: 
        strp_last = True  # and we'll remove the one with that index in the keys list
        char_out = list(lc.keys())[irem]

if strp_last:  # remove trailing character if set to do so
    for key in bib_OD:
        entry = bib_OD[key]
        if entry['title'].endswith(char_out):
            entry['title'] = entry['title'][:-1]  # remove trailing apostrophe (probably)

########################################################################
# Part 1: try to add DOIs (and nice metadata) to entries from input file
########################################################################

if not args.nosearch:
    # connection for querying, being polite for server priority
    cr = Crossref(mailto="tech@seismica.org",ua_string='Seismica SCE, seismica.org')  

    bib_new = OrderedDict()         # to save entries with DOIs added

    for key in bib_OD:  # loop entry keys
        entry = bib_OD[key]
        doi = None   # to start, assume no doi
        print('\nWorking on ', entry)
        if 'doi' in entry.keys(): # get provided doi if present, check to make sure it will work
            if entry['doi'][-1] == '.':             # check if doi ends with . and if it does, get rid of the .
                entry['doi'] = entry['doi'][:-1]    # (this is sometimes an anystyle problem)
            doi = entry['doi']
            ourl = scu.make_doi_url(doi)
            req = Request(ourl, headers=dict(Accept='application/x-bibtex'))
            try:
                bibtext = urlopen(req).read().decode('utf-8')
            except HTTPError:
                doi = None  # authors made a DOI mistake or anystyle messed up; try a search

        # if url looks like a doi link and we don't have the doi already, try the url
        if 'url' in entry.keys() and re.search(r"doi\.org",entry['url']) and not doi:
            req = Request(entry['url'], headers=dict(Accept='application/x-bibtex'))
            try:
                bibtext = urlopen(req).read().decode('utf-8')
            except HTTPError:
                doi = None  # url is not actually a good DOI link

        if not doi:  # try querying crossref to get a doi
            print('no DOI, querying crossref to try and find one')
            try:
                q = cr.works(query_bibliographic=entry['title'],query_author=entry['author'],\
                            limit=2,select='DOI,title,author,score,type,published',sort='score')
            except HTTPError:  # shouldn't happen, but if it does anyway we give up on this one
                continue
            except bbl.FieldError:  # probably no 'author' - might be 'editor'
                # in this (pretty edge) case, just keep the entry as is and move on
                entry_new = entry  # keep whatever the initial entry was
                entry_new.key = key         # keep the input key for now
                bib_new[key] = entry_new    # as that should be unique, even from anystyle (a/b etc)
                continue
            if q['message']['total-results'] > 0:  # TODO deal with case where exactly 1 result
                q0 = scu.format_crossref_query(q, i=0)
                print('\nqueried for:\ntitle: %s\nby: %s' % (entry['title'],entry['author']))
                if q['message']['total-results'] == 1:
                    iok = scu.print_query_options(q0, i=1)
                else:
                    iok = scu.print_query_options(q0, i=0)
                if iok.lower() == 'y':   # if it matches, save the doi
                    doi = q0['doi']
                elif iok.lower() == 'n':
                    doi = None
                elif iok.lower() == 'p':
                    q1 = scu.format_crossref_query(q, i=1)
                    iok = scu.print_query_options(q1, i=1)
                    if iok.lower() == 'y':   # if it matches, save the doi
                        doi = q1['doi']
                    elif iok.lower() == 'n':
                        doi = None
                    elif iok.lower() == 'p':
                        doi = q0['doi']

        if doi:  # if doi not none, use to query for a clean citation
            print('DOI provided/obtained, checking for cleaner citation into')
            ourl = scu.make_doi_url(doi)
            req = Request(ourl, headers=dict(Accept='application/x-bibtex'))
            try:
                bibtext = urlopen(req).read().decode('utf-8')

                # parse bibtex to an Entry and check to make sure all the main pieces are there
                # we need this bc some metadata deposited with DOIs is imperfect in weird ways
                parser = bbl.Parser()  # need a new parser every time which is annoying
                parsed = parser.parse(bibtext)
                key0 = list(parsed.get_entries().keys())[0]
                entry_new = parsed.get_entries()[key0]  # keyed based on doi.org convention

                # see if we need to fix/un-replace authors or titles
                # this is a kind of patch for dealing with the odd formatting (tex escaping,
                # html escaping) that occastionally shows up in the doi.org bibtex entries
                rereparse = False
                # first check if there are author list inconsistencies, see if we want old or new list
                if 'author' in entry_new.keys() and 'author' in entry.keys():
                    if len(entry.authors()) != len(entry_new.authors()): #or \
                            #re.search(r'[^\.a-zA-Z, -]',entry_new['author']):  # TODO this needs work - say which criterion was hit
                        print('\nchecking '+entry.key+' author list: ')
                        print('old: %s' % entry['author'])
                        print('new: %s' % entry_new['author'])
                        ika = input('keep (o)ld or [n]ew? >> ') or 'n'
                        if ika == 'o':
                            entry_new['author'] = entry['author']
                            rereparse = True
                elif 'author' not in entry_new.keys() and 'author' in entry.keys():  # avoid losing info
                    entry_new['author'] = entry['author']
                    rereparse = True

                # next check if there are title inconsistencies (easier to check tbh)
                if 'title' in entry_new.keys() and 'title' in entry.keys():
                    if entry['title'].lower() != entry_new['title'].lower():  # case is not as important
                        print('\nchecking '+entry.key+' title: ')
                        print('old: %s' % entry['title'])
                        print('new: %s' % entry_new['title'])
                        ikt = input('keep (o)ld or [n]ew? >> ') or 'n'
                        if ikt == 'o':
                            entry_new['title'] = entry['title']
                            rereparse = True
                elif 'title' not in entry_new.keys() and 'title' in entry.keys():
                    entry_new['title'] = entry['title']
                    rereparse = True

                if rereparse:  # info has been re-added, re-parse to reset field_pos
                    parser = bbl.Parser()
                    parsed = parser.parse(entry_new.to_bib())
                    entry_new = parsed.get_entries()[key0]

            except InputError:     # crossref returned text that biblib doesn't like to parse
                entry_new = entry  # keep whatever the initial entry was
            except HTTPError:      # this is some kind of crossref issue, maybe a bad DOI
                entry_new = entry
                            
        else:  # no doi, from authors or from crossref
            entry_new = entry  # keep whatever the initial entry was

        entry_new.key = key         # keep the input key for now
        bib_new[key] = entry_new    # as that should be unique, even from anystyle (a/b etc)
else:
    bib_new = bib_OD

########################################################################
# Part 2: go through the new OrderedDict with "cleaner" entries and fix up as needed
########################################################################

# open final outfile for writing
fout = open(out_bib,'w')  # will overwrite if file exists

newkey_list = []  # for tracking keys used in case we need 'a' and 'b', when not keeping keys
n_with_doi = 0
n_without_doi = 0
for key in bib_new:  # loop entry keys
    entry = bib_new[key]
    # for each, if 'date' is a key and 'year' is not, make 'year' based on 'date'
    if 'date' in entry.keys() and 'year' not in entry.keys():
        if len(entry['date']) == 4: # assume this means it's a year, which is probably true
            entry['year'] = entry['date']
        else: # some other format, try to parse
            try:
                try_year = str(dp.parse(entry['date']).year)
            except:  # unspecified error with dateutil parsing
                try_year = entry['date']
            print('date is %s, year set to %s' % (entry['date'],try_year))
            iy = input('enter corrected year if needed: ') or None
            if iy != None:
                entry['year'] = iy
            else:
                entry['year'] = try_year

    if 'url' in entry.keys():
        if re.search(r"doi\.org",entry['url']):  # check if url is just a doi link
            _ = entry.pop('url')  # if it is, we should have used it earlier and can clean now

    if 'pages' in entry.keys():
#        _ = entry.pop('pages')
        entry['pages'] = entry['pages'].rstrip(',')  # anystyle often leaves trailing commas
        if "n/a" in entry['pages']:  # sometimes get "n/a -- n/a" or similar from crossref
            _ = entry.pop('pages')

    if 'note' in entry.keys():
        entry['note'] = re.sub(r'Available at','',entry['note'])
        if len(entry['note']) <= 3:  # if we've only got 3 characters left or less, probably nothing
            _ = entry.pop('note')  # should take care of case with : at the end

    if 'title' in entry.keys() and entry['title'].endswith("'"):
        entry['title'] = entry['title'][:-1]  # remove trailing apostrophe if present

    if 'title' not in entry.keys():
        entry['title'] = " "  # TODO is this a good workaround?

    if 'journal' in entry.keys():  # check for ampersands, regex them
        entry['journal'] = re.sub(r" &amp; ",r" \& ",entry['journal'])  # misplaced xml
        entry['journal'] = re.sub(r" & ",r" \& ",entry['journal'])  # and any others not escaped

    if not args.keepkeys:  # if we want to make new entry keys (docx/odt input file)
        if 'author' not in entry.keys():  # our key convention is based on authors and years
            if 'editor' in entry.keys():
                entry['author'] = entry['editor']
            else:
                print('no author found! available keys are:')
                print(entry.keys())
                akey = input('enter a key to use for author: ') or entry.keys()[0]
                if akey not in entry.keys():
                    akey = entry.keys()[0]  # fallback for typos
                entry['author'] = entry[akey]
            parser = bbl.Parser()  # need to re-parse to get field_pos right in Entry
            parsed = parser.parse(entry.to_bib())
            entry = parsed.get_entries()[key]

        # clean up first author last name: no {}, no spaces
        auth0 = re.sub(r'[ ]',r'',entry.authors()[0].last.lstrip('{').rstrip('}'))

        # for each, reformat key to be what we will look for in inline citations
        # first, count authors: if >2, key is firstauthorEAYYYY, if 2 or less is author(author)YYYY
        try:
            if len(entry.authors()) > 2:
                newkey = auth0 + 'EA' + entry['year']
            elif len(entry.authors()) == 2:
                auth1 = re.sub(r'[ ]',r'',entry.authors()[1].last.lstrip('{').rstrip('}'))
                newkey = auth0 + auth1 + entry['year']
            elif len(entry.authors()) == 1:
                newkey = auth0 + entry['year']
        except:
            newkey = auth0+"MessyKey"
            print('problem with key: ',newkey)
        newkey = newkey.replace(" ","")  # get rid of spaces if there are any (like van Keken or something)
        newkey = newkey.replace("-","")  # get rid of hyphens, which tex2jats doesn't like
        nextletter = 'a'
        if newkey + nextletter in newkey_list:  # already have 'a', try the next letter
            thisauthor = [e for e in newkey_list if e.startswith(newkey)]
            alphabet = [e[-1] for e in thisauthor]
            nextletter = chr(ord(alphabet[-1]) + 1)
        newkey = newkey + nextletter  # this is what we'll use for bibtex

        newkey_list.append(newkey)
        entry.key = newkey

    # check if doi field is present
    if 'doi' in entry.keys() or 'DOI' in entry.keys():
        n_with_doi += 1
        # escape any underscores that might be in DOIs for the sake of tex
        # (only do this just before writing bc needs to be clean for queries)
        entry['doi'] = re.sub(r'_',r'\_',entry['doi'])
    else:
        n_without_doi += 1

    # write entry to new bib file
    fout.write(entry.to_bib())
    fout.write('\n')

fout.close()

print('%i items have doi, %i do not have doi' % (n_with_doi, n_without_doi))
print('%.2f percent lack doi' % (100*n_without_doi/(n_with_doi + n_without_doi)))
#print('if many dois are missing, try searching the plain text reference list with %s' % ("https://apps.crossref.org/SimpleTextQuery"))
