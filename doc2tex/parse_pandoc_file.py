import biblib.bib as bbl
import sce_utils.tex_templates as tt
import sce_utils.utils as ut
import numpy as np
from argparse import ArgumentParser
import os, sys, re


########################################################################
# run through a pandoc'd latex file line by line, correcting things pandoc doesn't catch well
# in particular inline citations (so also read corresponding bibtex first)
# NOTE: this script assumes:
    # the input file used the seismica docx/odt template, and used it *properly* (esp. headers/styles)
    # equations were typeset using native equation thing
    # pandoc was run with the right options
    # there are no more than 99 equations, figures, and tables, respectively, in the document
    # a bibtex file using the reference list has already been created (see: anystyle, fix_bibtex.py)
    # references/bibliography is the LAST SECTION of the document, nothing after it will be kept
    # Table and Figure captions start with the capitalized words 'Table' or 'Figure'
# TODO:
    # finding ORCID and CRediT sections if not automatically ID'd
########################################################################

########################################################################
# set filenames
########################################################################
parser = ArgumentParser()
parser.add_argument('--bibfile','-b',type=str,help='path to bibfile')
parser.add_argument('--ifile','-i',type=str,help='path to tex file from pandoc')
parser.add_argument('--ofile','-o',type=str,help='path to output tex file')
parser.add_argument('--parens','-p',type=str,help='() or [] for citations',default='()')
args = parser.parse_args()
bibtex = args.bibfile
assert os.path.isfile(bibtex),'bibfile does not exist'
tex_in = args.ifile
assert os.path.isfile(tex_in),'input tex file does not exist'
tex_out = args.ofile
if tex_out == None:
    tex_out = tex_in[:-4] + '_corr.tex'
    print('using %s for output file' % tex_out)
tex_premid = 'pandoc_cleaned.tex'
tex_mid = 'temp.tex'
junk_out = 'junk.tex'  # this is for table and figure info that can't be parsed automatically
review = False  # switch for line numbers (and single-column format) - always off for production
chars = args.parens

########################################################################
# set up some things:
# read bibtex, get list of keys for entries that we expect to find in the text
parser = bbl.Parser()
biblio = parser.parse(open(bibtex,'r'))
bibkeys = biblio.get_entries().keys()

# set up counters for figures, equations, and tables
nfig = 1; nequ = 1; ntab = 1
figcap = {}; tabcap = {}

# for sections that aren't numbered, lowercase and with spaces as -
special_section_names = ['acknowledgements','acknowledgments',\
                        'data-availability','data-and-code-availability',\
                        'competing-interests']
skip_sections = ['references','bibliography']  # when we get to this header, skip to the end

########################################################################
# start by cleaning some elements we don't want, scraping overall structure,
# and figuring out where the document starts after pandoc's added header

# clean initial pandoc file for hypertarget, texorpdfstring, misplaced enumeration
ut.first_pandoc_clean(tex_in,tex_premid)  # outputs "pandoc_cleaned.tex"

# open cleaned pandoc file ('premid') and output temp file ('mid')
ftex_in = open(tex_premid,'r')
ftex_out = open(tex_mid,'w')
fjunk = open(junk_out,'w')  # and junk file, where we will put things that aren't handled

# get structural cues/line numbers for seeking some sections later
_,struct = ut.document_structure(ftex_in)

# determine which sections are ORCIDs and CRediT, make sure those are there
orcid_key = -1; credit_key = -1; abs1_key = -1; manu_key = -1
for k in struct.keys():
    if struct[k]['sname'].lower().__contains__('orcid'):
        orcid_key = k
    if struct[k]['sname'].lower().__contains__('author contributions'):
        credit_key = k
    if struct[k]['sname'].lower() == 'abstract' and abs1_key < 0:  # specifically, first/English abstract
        abs1_key = k
    if struct[k]['sname'].lower().__contains__('manuscript type'):
        manu_key = k

assert orcid_key >= 0, 'Author ORCIDs section not found'
assert credit_key >= 0, 'Author contributions section not found'
assert abs1_key >= 0, 'Abstract not found'
if manu_key < 0:
    print('Manuscript type not found; defaulting to Article')
    print('Please check with HE to make sure this is not a report')
    type_of_paper = 'Article'

########################################################################
# deal with title and authors
# skip header stuff from pandoc that seismica.cls will replace, find manuscript title
ftex_in.seek(0)
for i in range(struct['b']['line']+1):
    line = ftex_in.readline()  # should read exactly to \begin{document}

# if title is in the document structure, we're done!
if 'ti' in struct.keys():
    article_title = struct['ti']['sname']
else:  # hopefully the title is the first line after begin{document} if not in \title{} format
    while True:
        line = ftex_in.readline()
        if line != '\n':
            break  # this should be the title, fingers crossed
    article_title = line.rstrip() # get the title text
# if entire article title is bolded or emph'd, get rid of that formatting
if re.match(r"\\textbf{(.*)}",article_title):  # need to match end bracket at end
    article_title = re.findall(r"\\textbf{(.*)}",article_title)[0]
if re.match(r"\\emph{(.*)}",article_title):
    article_title = re.findall(r"\\emph{(.*)}",article_title)[0]

# read in author info (names, affiliations, email for corresponding if applicable)
while True:  # read up to where authors start
    line = ftex_in.readline()
    if line != '\n' and not line.startswith(r'\maketitle'):
        break  # author names, prior to affiliations
authors = {}  # read author names and superscripts for affiliations, single line
for i,bit in enumerate(line.split('}')[:-1]):
    bit2 = bit.split(r'\textsuperscript{')
    nm = bit2[0].lstrip().rstrip()
    if nm.startswith(','):
        nm = nm[1:].lstrip().rstrip()
    if nm.startswith('&'):
        nm = nm[1:].lstrip()
    if nm.startswith('and'):
        nm = nm[3:].lstrip()
    sp = bit2[1]
    authors[i] = {'name':nm.lstrip().rstrip(),'supers':sp}

affils = {}  # read affiliations that go with those superscripts
while True:
    line = ftex_in.readline()
    if line.startswith(r'\textsuperscript'):  # is an affiliation
        groups = re.findall(r"\\textsuperscript{([1-9*]{1,2})}(.*)",line)
        sp = groups[0][0]
        pl = groups[0][1].strip()
        try:
            affils[int(sp)] = {'super':sp,'place':pl}
        except ValueError:  # probably a superscript asterisk
            if sp == '*':
                email = line.split(':')[-1].lstrip()
                for k in authors.keys():
                    if '*' in authors[k]['supers']:
                        authors[k]['corresp'] = email.rstrip()
            else:  # maybe some other symbol eg for changing affiliation
                print('unknown afflitiation superscript; moving to junk')
                fjunk.write(line)
                fjunk.write('\n')
    elif line.startswith('*'):  # corresponding author email address
        email = line.split(':')[-1].lstrip()
        for k in authors.keys():
            if '*' in authors[k]['supers']:
                authors[k]['corresp'] = email.rstrip()
    elif line.startswith(r'\hypertarget') or line.startswith(r'\section'):  # hopefully not \section
        break  # stop at the start of a section

# remove asterisk from superscripts once email address is found (if * is superscripted)
for a in authors.keys():
    if '*' in authors[a]['supers']:  # need to remove extra * because \thanks takes care of that
        star_ind = authors[a]['supers'].find('*')
        if star_ind == len(authors[a]['supers'])-1:
            authors[a]['supers'] = authors[a]['supers'][:-1]
        else:
            pre = authors[a]['supers'][:star_ind]
            post = authors[a]['supers'][star_ind+2:]
            authors[a]['supers'] = pre+post
    authors[a]['supers'] = authors[a]['supers'].rstrip(',')  # no trailing commas just in case

# parse orcids, add to author dict
ftex_in.seek(0)
for i in range(struct[orcid_key]['line']+1):
    line = ftex_in.readline()  # read up to ORCIDs section

# read from start of orcid section to start of subsequent section
for i in range(struct[orcid_key]['line']+1,struct[orcid_key+1]['line']):
    line = ftex_in.readline()
    if line != '\n':  # there is something to parse
        # figure out who the author is, locate in author dict
        orcid_claimed = False
        for k in authors.keys():
            if ut.author_aliases(line.split(':')[0],authors[k]['name']):
                authors[k]['orcid'] = line.split(':')[1].lstrip().rstrip()
                orcid_claimed = True
        if not orcid_claimed:
            print('orcid ',line.split(':'),' not matched to author list')

# parse CRediT section, make a dict for that
ftex_in.seek(0)
for i in range(struct[credit_key]['line']+1):
    line = ftex_in.readline()  # read up to CRediT section

# read from start of credit section to start of subsequent section
credit = {}
for i in range(struct[credit_key]['line']+1,struct[credit_key+1]['line']):
    line = ftex_in.readline()
    if line != '\n':
        key = line.split(':')[0]
        vals = line.split(':')[1].lstrip().rstrip().rstrip('.')
        credit[key] = vals

# if manuscript type is included (added circa March 2024), read that before dealing with abstract
if manu_key > 0:
    ftex_in.seek(0)
    for i in range(struct[manu_key]['line']+1):
        line = ftex_in.readline()  # read up to manuscript type "section"
    for i in range(struct[manu_key]['line']+1,struct[manu_key+1]['line']):
        line = ftex_in.readline()
        if line != '\n':
            type_of_paper = line.strip().strip(',')
            break

# go to the abstract and start reading that stuff
ftex_in.seek(0)
for i in range(struct[abs1_key]['line']+1):
    line = ftex_in.readline()

# read lines cautiously, find the (first/English-language) abstract text
summaries = {}; scount = 0
abst = ""
while True:
    line = ftex_in.readline()
    if not line.startswith(r'\section'):
        abst = abst + line.rstrip()  # this will probably be just one line(/one paragraph)
    else:                            # but there can be multi-paragraph abstracts
        break
summaries[scount] = {'text':abst,'name':'Abstract','language':'English'}
scount += 1

other_langs = []
# deal with the second-language abstract  if there is one
if line.lower().startswith(r'\section{second language abs'):
    abs2_dict = {}
    abs2 = ''
    hdr = line.split('{')[1].split('}')[0].split(':')[-1].lstrip()  # input line is section header
    abs2_dict['name'] = hdr.split('(')[0].rstrip()
    abs2_dict['language'] = hdr.split('(')[-1].split(')')[0].lower()
    while True:
        line = ftex_in.readline()
        if not line.startswith(r'\section'):  # until we hit the next section
            abs2 = abs2 + line.rstrip()
        else:
            break 
        #abs2 = check_non_ascii(abs2)  # try to convert any non-ascii characters
    abs2_dict['text'] = abs2
    other_langs.append(abs2_dict['language']) 
    summaries[scount] = abs2_dict
    scount += 1

# deal with the third-language abstract  if there is one
if line.lower().startswith(r'\section{third language abs'):
    abs3_dict = {}
    abs3 = ''
    hdr = line.split('{')[1].split('}')[0].split(':')[-1].lstrip()  # input line is section header
    abs3_dict['name'] = hdr.split('(')[0].rstrip()
    abs3_dict['language'] = hdr.split('(')[-1].split(')')[0].lower()
    while True:
        line = ftex_in.readline()
        if not line.startswith(r'\section'):  # until we hit the next section
            abs3 = abs3 + line.rstrip()
        else:
            break 
    abs3_dict['text'] = abs3
    other_langs.append(abs3_dict['language'])
    summaries[scount] = abs3_dict
    scount += 1

# parse (English-language) non-technical summary if present
if line.lower().startswith(r'\section{non-technical summary'):
    line = ftex_in.readline()  # get past \section
    nontech = ""
    while True:
        line = ftex_in.readline()
        if not line.startswith(r'\section'):
            nontech = nontech + line.rstrip()
        else:
            break
    summaries[scount] = {'text':nontech,'name':'Non-technical summary','language':'English'}
    scount += 1


# feed some info to the header setup code
ftex_out = tt.set_up_header(ftex_out,article_title,authors=authors,affils=affils,credits=credit,\
            other_langs=other_langs,manu=type_of_paper)

# add abstract(s) after header
ftex_out = tt.add_abstracts(ftex_out,summaries)

########################################################################
# go through the rest of the sections! and deal with citations, figures, and equations

goto_end = False   # flag to stop reading/writing at references section
first_line = True  # abstract reading stopped at a section header, so don't read past that
while not goto_end:
    if not first_line:  # for when we already read the \section to get to the end of the abs.
        line = ftex_in.readline()
    else:
        first_line = False
    if line.startswith(r'\end{document}'): # this is the end, stop reading
        break  # shouldn't hit this unless there is no reference section

    if re.match(r"\\(?:(sub){0,3})section",line):  # this is a section heading
        stype = line.split('{')[0]
        sname = line.split('{')[1].split('}')[0].strip()
        if sname.lower() in special_section_names:
            stype = stype + '*'
        elif sname.lower() in skip_sections:  # skip everything past "References"
            goto_end = True
        else:
            # check if there *is* a leading number
            lead_num = line.split('{')[1].split('}')[0].strip()[0]
            if lead_num.isdigit():
                sname = ' '.join(line.split('{')[1].split('}')[0].split(' ')[1:])  # strip leading number
        if sname != '' and not goto_end:
            ftex_out.write('%s{%s}\n' % (stype,sname))

    else:  # not a section header, so parse as a line and deal with citations or math or whatever
        if line.startswith(r'\(') or line.startswith(r'\['):  # possibly an equation
            print(line[:-1])
            iq = input('is this an equation? [y]/n: ') or 'y'
            sw = line[:2]
            if sw[1] == '(': ew = r'\)'
            if sw[1] == '[': ew = r'\]'
            if iq.lower() == 'y':
                # scrape off the \( and \) bits since we're putting this in an environment
                line = line.split(sw)[1].split(ew)[0]
                ftex_out.write(r'\begin{equation}')
                ftex_out.write('\n')
                ftex_out.write(line)
                ftex_out.write('\n')
                ftex_out.write(r'\label{eq%i}' % nequ)
                ftex_out.write('\n')
                ftex_out.write(r'\end{equation}')
                ftex_out.write('\n')
                nequ += 1
            else:
                print('ok, writing line plain, then')
                ftex_out.write(line)

        elif line.startswith('\\begin{'):  # some kind of environment?
            ftex_in, ftex_out, fjunk, nequ, nfig, ntab, itype = \
                    ut.parse_environment(line,ftex_in,ftex_out,fjunk,nequ,nfig,ntab)

        elif line.startswith(r'\includegraphics'):
            ftex_out.write(r'\begin{figure*}[ht!]')
            ftex_out.write('\n')
            ftex_out.write(r'\centering')
            ftex_out.write('\n')
            ftex_out.write(r'\includegraphics[width = \textwidth]{figure%i}' % nfig)
            ftex_out.write('\n')
            ftex_out.write(r'\caption{\textcolor{red}{placeholder caption}}')
            ftex_out.write('\n')
            ftex_out.write(r'\label{fig%i}' % nfig)
            ftex_out.write('\n')
            ftex_out.write(r'\end{figure*}')
            ftex_out.write('\n')
            print('figure found; moving original line to junk file')
            fjunk.write('Figure %i\n' % nfig)
            fjunk.write(line)
            fjunk.write('\n')  # saving for later
            nfig += 1

            # check if the caption of this figure was on the \includegraphics line
            maybe_caption = re.findall(r'\\textbf{Figure',line)
            if len(maybe_caption) == 1: # mess with line, try to grab caption
                line = ut.parse_parentheticals(line,bibkeys,chars=chars)
                line = ut.check_for_fig_tab_eqn_refs(line)
                line = ut.non_breaking_space(line)

                might_be_caption = '\\textbf{Figure' + line.split('\\textbf{Figure')[-1]
                print('\t'+might_be_caption[:40])
                iq = input('Is this a caption? [y]/n: ') or 'y'
                if iq.lower() == 'y':  # save in caption dict, don't write here
                    cap = r'\ref{'.join(line.split(r'\ref{')[1:]).rstrip()  # no trailing \n
                    tag = cap.split('}')[0]
                    #if to_write.startswith('\\textbf{Figure') or to_write.startswith('\\textbf{Table'):
                    splits = line.split(tag)
                    test = splits[1][2:].lstrip()
                    if test.startswith('}'):
                        test = test[1:].lstrip()
                    if len(splits) > 2:
                        fullcap = tag.join(np.append(test,splits[2:]))
                    else:
                        fullcap = test
                    fullcap = fullcap.lstrip('.').strip() # strip accidental leading . and/or spaces
                    figcap[tag] = fullcap

        else:
            # parse the line for parenthetical citations etc (there are some TODO s in this function)
            to_write = ut.parse_parentheticals(line,bibkeys,chars=chars)

            # rescan line and look for figure/equation references to link
            to_write = ut.check_for_fig_tab_eqn_refs(to_write)

            # rescan line and look for urls that need wrapping
            to_write = ut.check_href_make_url(to_write)

            # rescan again to replace spaces for reference links with ~ (non-breaking)
            to_write = ut.non_breaking_space(to_write)

            # a few last checks for special cases:  
            # try to match lines that are caption-ish with or without bold tags
            regex_figcap = bool(re.match(r'^Figure~\\ref{fig[0-9]{1,2}}[\.:]',to_write))
            regex_tabcap = bool(re.match(r'^Table~\\ref{tbl[0-9]{1,2}}[\.:]',to_write))
            start_figcap = to_write.lstrip().startswith(r'\textbf{Figure')
            start_tabcap = to_write.lstrip().startswith(r'\textbf{Table')
            if start_figcap or start_tabcap or regex_figcap or regex_tabcap: # likely a caption
                print('\t'+to_write[:40])
                iq = input('Is this a caption? [y]/n: ') or 'y'
                if iq.lower() == 'y':  # save in caption dict, don't write here
                    cap = r'\ref{'.join(to_write.split(r'\ref{')[1:]).rstrip()  # no trailing \n
                    tag = cap.split('}')[0]
                    #if to_write.startswith('\\textbf{Figure') or to_write.startswith('\\textbf{Table'):
                    splits = to_write.split(tag)
                    test = splits[1][2:].lstrip()
                    if test.startswith('}'):
                        test = test[1:].lstrip()
                    if len(splits) > 2:
                        fullcap = tag.join(np.append(test,splits[2:]))
                    else:
                        fullcap = test
                    fullcap = fullcap.lstrip('.').strip() # strip accidental leading . and/or spaces
                    if start_figcap or regex_figcap:
                        figcap[tag] = fullcap
                    elif start_tabcap or regex_tabcap:
                        tabcap[tag] = fullcap
                    to_write = ''

            elif to_write[0].islower():           # lines (paragraphs) that start with lowercase
                ftex_out.write('\\noindent \n')   # are probably continuing sentences after eqns

            ftex_out.write(to_write)    # finally, write the line

ftex_out.write(r'\bibliography{%s}' % bibtex.split('/')[-1].split('.')[0])
ftex_out.write('\n')
ftex_out.write(r'\end{document}')

ftex_in.close()
ftex_out.close()
fjunk.close()

########################################################################
# reread temp tex file ('mid') to put in figure captions and rewrite ('out')
ftex_in = open(tex_mid,'r')  # open intermediate file
ftex_out = open(tex_out,'w')

beg_doc = False
while True:
    line = ftex_in.readline()
    if line.startswith(r'\begin{document}'): beg_doc = True
    if line.startswith(r'\begin{figure'):
        temp = [line]
        while True:
            line = ftex_in.readline()
            temp.append(line)
            if line.startswith(r'\label'):
                tag = line.split(r'\label{')[1].split('}')[0]
            if line.startswith(r'\end{'):
                break

        for t in temp:
            #print(figcap)
            if t.startswith(r'\caption') and tag in figcap:
                ftex_out.write(r'\caption{%s}' % figcap[tag])
                ftex_out.write('\n')
            else:
                ftex_out.write(t)

    elif line.startswith(r'\begin{table'):
        temp = [line]
        while True:
            line = ftex_in.readline()
            temp.append(line)
            if line.startswith(r'\label'):
                tag = line.split(r'\label{')[1].split('}')[0]
            if line.startswith(r'\end{table'):  # can't be \end{tabular}
                break

        for t in temp:
            if t.startswith(r'\caption') and tag in tabcap:
                ftex_out.write(r'\caption{%s}' % tabcap[tag])
                ftex_out.write('\n')
            else:
                ftex_out.write(t)

    elif line.startswith(r'\end{document'):
        print(line)
        ftex_out.write(line)
        break
    else:
        ftex_out.write(line)
        
ftex_in.close()
ftex_out.close()

## clean up some intermediate files
os.remove(tex_premid)
os.remove(tex_mid)

ut.print_reminders(tex_out)
