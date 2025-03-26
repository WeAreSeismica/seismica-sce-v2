import numpy as np
from re import finditer, findall
import dateutil.parser as dp
import re
import os, sys

####
# functions for text processing of pandoc outputs
####

def clean_enumerates(ifile_name):
    """
    read an entire pandoc file and clean out excess enumerates, mark them so we can find them
    as section headings later
    """
    ftex_in = open(ifile_name,'r')
    ftext = np.array(ftex_in.read().split('\n'))  # all lines all at once
    ftex_in.close()

    # get starting indices for enumerate environments
    i_enu = np.where([l.startswith(r'\begin{enumerate}') for l in ftext])[0] 
    enums_to_clean = []  # to save info on things that we will clean out later
    # list things that would indicate "bad" enumerate environments
    bad_starts = [r'\begin{',r'\setcounter',r'\def',r'\end{']
    for i in range(len(i_enu)):  # loop enums and see if they are likely headers, extract headers if so
        item_inds = []
        j = i_enu[i]
        while True:
            if ftext[j].startswith(r'\end{enumerate}'):
                break
            if ftext[j].strip().startswith(r'\item'):
                item_inds.append(j)
            j += 1
        if len(item_inds) == 1:  # likely a mis-enumerated heading if only one item in list
            tc_dict = {'row_low':i_enu[i],'row_high':j}  # bounds on enumrated environment
            # case 1: \item line has the item actually on that line
            if ftext[item_inds[0]].strip() != r'\item':  # more than just the tag
                tc_dict['irow_keep'] = item_inds[0]  # this is the row we care about
            # case 2: \item line is just \item, actual item is some unknown distance after that line
            elif ftext[item_inds[0]].strip() == r'\item':
                for k in range(item_inds[0]+1,j):  # loop the rows starting right after item
                    if np.any([ftext[k].strip().startswith(l) for l in bad_starts]):  # prob not item
                        pass
                    else:  # hopefully item?
                        tc_dict['irow_keep'] = k
            enums_to_clean.append(tc_dict)

    # actually clean out all these enumerate things by first cleaning up the "keep" rows,
    # and then deleting the unneccessary rows
    good_enum_rows = np.array([a['irow_keep'] for a in enums_to_clean])
    for i in good_enum_rows:
        if ftext[i].strip().startswith(r'\item'):  # clean off item tag if present
            ftext[i] = ftext[i].split(r'\item')[-1]
        if ftext[i].strip().startswith(r'\textbf{'):   # clean off bold formatting
            pass  # TODO TODO TODO stopped here

    # also clean out texorpdfstring, why not

    # rewrite! overwrite!!
    return

def first_pandoc_clean(ifile,ofile):
    """ clean some specific things out of pandoc file before looking for structure:
    -> no more hypertargets, get rid of those lines
    -> no more texorpdfstring, regex those out
    write to an output file that will also be temp I suppose
    """
    ftex_in = open(ifile,'r')
    ftext = np.array(ftex_in.read().split('\n'))  # all lines all at once
    ftex_in.close()

    ftex_out = open(ofile,'w')
    for i in range(len(ftext)):  # loop lines, check, write if ok
        line = ftext[i]
        skipline = 0  # we intend to write this line
        if line.startswith(r'\hypertarget'):
            l1 = ftext[i+1]
            if re.match(r'\\(?:(sub){0,3})section',l1):  # next line starts with section
                skipline = 1  # we now intend to skip this line in favor of the next
            elif re.findall(r'\\(?:(sub){0,3})section',line):  # section is in this line
                q = list(re.finditer(r'\\(?:(sub){0,3})section',line))
                line = line[q[0].start():]  # slice to where the section tag starts
        if re.findall(r'texorpdfstring',line) and not skipline:  # has a texorpdfstring thingy, not skipped
            line = re.sub(r"\\texorpdfstring{(.*?)}",r"",line)  # get rid of that tag TODO does not work always

        # if a (sub)section line, check for ending labels and strip them off
        if re.match(r'\\(?:(sub){0,3})section',line) and re.findall(r"\\label{(.*?)}",line):
            q = list(re.finditer(r'\\label{(.*?)}',line))
            line = line[:q[0].start()]

        # check for excess brackets
        if re.match(r"\\(?:(sub){0,3})section",line):
            line = re.sub(r"{{",r"{",line)
            line = re.sub(r"}}",r"}",line)

        # check if line is bold-formatted but not a fiture or table caption
        # (which probably means it was a poorly formatted section header)
        if re.match(r'^\\textbf\{[^{]*\}$',line.strip()):
            isfig = bool(re.match(r'^\\textbf\{Figure',line.strip()))
            istab = bool(re.match(r'^\\textbf\{Table',line.strip()))
            if not isfig and not istab:  # capture content of the tag and reformat
                newline = re.findall(r'^\\textbf\{([^{]*)\}$',line.strip())[0]
                newline = '[SECTION HEADER level unknown] {' + newline + '}'
                line = newline

        if not skipline:
            ftex_out.write(line)
            ftex_out.write('\n')

    ftex_out.close()

    return

def document_structure(ftex_in):
    """
    read through entire pandoc'd file and extract outline, with line numbers for
    where each section heading is
    this prepares us to get article metadata (author orcids, credit) with fewer assumptions
    about how those sections are ordered (still need authors and title first, though)
    and if we want it could let us check that all necessary sections are in fact present?
    """
    struct = {}
    ftex_in.seek(0)
    nln = sum(1 for line in ftex_in)
    ftex_in.seek(0)
    i = 0  # line counter
    j = 0  # section heading counter
    while i < nln:
        line = ftex_in.readline()
        if re.match(r'\\(?:(sub){0,3})section',line):  # section header
            if line.split('{')[1].strip()[0].isdigit():  # try to remove numbering
                sname = ' '.join(line.split('{')[1].split('}')[0].split(' ')[1:])
            else:
                sname = line.split('{')[1].split('}')[0]
            sect = {'sname': sname,\
                    'level': line.split('{')[0][1:],\
                    'line':i}
            struct[j] = sect
            j += 1
        elif line.startswith(r'\begin{document}'):
            sect = {'sname':'begin_doc',\
                    'level': 0,\
                    'line': i}
            struct['b'] = sect
        elif line.startswith(r'\title{'):
            sect = {'sname':line.split(r'\title{')[-1].rstrip('}\n'),\
                    'level':-1,\
                    'line':i}
            struct['ti'] = sect
        i += 1
    return ftex_in, struct

def parse_environment(line,ftex_in,ftex_out,fjunk,nequ,nfig,ntab):
    """
    read and deal with an environment (equation, figure, table)
    """
    print('environment detected')  # notify the user that we found something
    temp = [line]
    while True:
        line = ftex_in.readline()
        temp.append(line)
        if line.startswith(r'\end{'):
            break

    # check for some particular cases: if begin{equation} or {itemize}, assume it's probably ok
    # and don't ask for user input
    if re.match(r"\\begin{equation",temp[0]):
        print("\tit's an equation, acting accordingly")
        temp = temp[1:-1]  # skip the begin/end lines, will be re-added (bc of brackets case)
        ieq = 'e'
    elif re.match(r"\\begin{itemize",temp[0]):
        print("\tit's an itemized list, acting accordingly")
        ieq = 'm'
    else:  # if not obvious, ask for user input
        if len(temp) < 10:
            for e in temp: print('\t',e[:-1])  # skip newlines with [:-1]
        else:
            for e in temp[:9]: print('\t',e[:-1])
        ieq = input('is this an [e]quation, [f]igure, [t]able, ite[m]ized list, or [n]one of the above?') or 'n' # ask what it looks like
        print('\n')

    # write to file(s) accordingly
    if ieq.lower() == 'e':  # if it does, parse it like one
        ftex_out.write(r'\begin{equation}')
        ftex_out.write('\n')
        for k in range(0,len(temp)):  # this only matters if someone puts their equations in tables
            if temp[k].startswith(r'\toprule') or temp[k].startswith(r'\endhead')\
                or temp[k].startswith(r'\bottomrule') or temp[k].startswith(r'\end{')\
                or temp[k].startswith(r'\begin{longtable'):
                pass
            elif temp[k].startswith(r'\('):  # probably the start of the equation
                if '&' in temp[k]:
                    goodpart = temp[k].split('&')[0].rstrip()  # get rid of 2nd column (if table)
                    ftex_out.write(goodpart[2:-2]+'\n')
                else:
                    ftex_out.write(temp[k][2:-2]+'\n') # strip the \( part?
            else:
                ftex_out.write(temp[k])  # split lines? who knows?
        ftex_out.write(r'\label{eq%i}' % nequ)  # label the equation for tex reference
        ftex_out.write('\n')
        ftex_out.write(r'\end{equation}')
        ftex_out.write('\n')
        nequ += 1  # increment the equation counter

    elif ieq.lower() == 'f':
        ftex_out.write(r'\begin{figure*}[ht!]')
        ftex_out.write('\n')
        ftex_out.write(r'\centering')
        ftex_out.write('\n')
        ftex_out.write(r'\includegraphics[width = \textwidth]{figure%i}' % nfig)
        ftex_out.write('\n')
        ftex_out.write(r'\caption{placeholder caption}')
        ftex_out.write('\n')
        ftex_out.write(r'\label{fig%i}' % nfig)
        ftex_out.write('\n')
        ftex_out.write(r'\end{figure*}')
        ftex_out.write('\n')
        print('moving this environment to junk file; sort it out manually\n')
        fjunk.write('Figure %i\n' % nfig)
        for k in temp:
            fjunk.write(k)
        fjunk.write('\n')  # saving for later
        nfig += 1

    elif ieq.lower() == 't':
        new_temp = reformat_table(temp,ntab)
        for k in new_temp:
            ftex_out.write(k)
        print('tried to fix table; a copy is in junk if needed\n')
        fjunk.write('Table %i\n' % ntab)
        for k in temp:
            fjunk.write(k)
        fjunk.write('\n')  # saving for later
        ntab += 1

    elif ieq.lower() == 'm':
        for k in temp:
            ftex_out.write(k)

    else:
        print('moving this environment to junk file; sort it out manually\n')
        fjunk.write('Unspecified thing:\n')
        for k in temp:
            fjunk.write(k)
        fjunk.write('\n')

    return ftex_in, ftex_out, fjunk, nequ, nfig, ntab, ieq

def reformat_table(temp,ntab):
    """
    take one of pandoc's messy table or longtable environments and rework as something
    nicer that we can actually use
    includes pre-formatting commands for table style
    """

    # set up styling and outer table environment
    pretab = """\\rowcolors{2}{gray!0}{gray!10}
\\renewcommand{\\arraystretch}{1.2}
\\begin{table*}[ht]
\\begin{center}
\\sflight\\small
\\arrayrulecolor{gray}\n"""

    good_rows = []  # find the rows that actually have our data in them
    for line in temp:
        if '&' in line:    
            good_rows.append(line)

    ncols = len(good_rows[0].split('&'))  # figure out how many columns we need
    mspace = 7/ncols  # even spacing, adjust to taste later

    tabstart = '\\begin{tabular}{'
    for i in range(ncols):
        tabstart += 'm{%.2fin} ' % mspace
    tabstart = tabstart[:-1] + '}\n'

    out_tab = pretab + tabstart
    for l in good_rows:
        out_tab += l
    out_tab += r"""\end{tabular}
\end{center}
\caption{placeholder caption}
\label{tbl%i}
\end{table*}""" % ntab
    out_tab += "\n"

    return out_tab


def check_href_make_url(to_write):
    """
    check a line for href{} (and also un-wrapped URLS?) and try to fix them
    """
    out_write = ""
    # check for href and fix if present
    matches = re.finditer(r'\\href\{(.*?)\}\{(.*?)\}',to_write)
    info = [(m.start(),m.end(),m.groups()) for m in matches]
    if len(info) > 0:
        for i in range(len(info)):
            if i == 0:
                out_write += to_write[:info[0][0]]
            urlwrap = '\\url{' + info[i][2][1] + '}'
            out_write += urlwrap
            if i < len(info)-1:
                out_write += to_write[info[i][1]:info[i+1][0]]
        out_write += to_write[info[i][1]:]
    else:
        out_write = to_write

    # try to find un-wrapped URLs (ie not \url and not \href) and wrap those too
    matches = re.finditer(r'[^\{]http(.*?)[\) ]',out_write)
    info = [(m.start(),m.end(),m.groups()) for m in matches]
    new_write = ""
    if len(info) > 0:
        for i in range(len(info)):
            if i == 0:
                new_write += out_write[:info[0][0]+1]
            urlwrap = '\\url{http' + info[i][2][0] + '}'
            new_write += urlwrap
            if i < len(info)-1:
                new_write += out_write[info[i][1]-1:info[i+1][0]+1]
        new_write += out_write[info[i][1]-1:]
    else:
        new_write = out_write

    return new_write
        


def check_for_fig_tab_eqn_refs(to_write):
    """
    check a line for 'Figure 1' or 'Equation 9' or whatever, replace those with linked refs
    """
    capital_names = ['Figure ','Equation ','Table ','Fig. ','Eq. ','Figures ','Tables ','Figs. ']
    plurals = ['Figures ','Tables ','Figs. ']
    ref_names = ['fig','eq','tbl','fig','eq','fig','tbl','fig']

    for iw, word in enumerate(capital_names):
        if word in to_write:
            nrefs = len([m.start() for m in finditer(word,to_write)])
            # for each such index, look for the number
            for ireplace in range(nrefs):
                inds = np.array([m.start() for m in finditer(word,to_write)])
                ifig = inds[ireplace]
                shift = len(word) # + 1  # added space to keys to avoid "Figured"
                try:
                    fig_num = int(to_write[ifig+shift])
                except ValueError:  # this isn't an int
                    if to_write[ifig+shift] == 'S':  # a supplemental item? skip it
                        fig_num = 999
                    else:
                        try:
                            shift = len(word) + 1 # + 2
                            fig_num = int(to_write[ifig+shift])  # maybe the number was in parens?
                        except ValueError:
                            fig_num = 999

                if fig_num != 999: # check again for double-digit numbers
                    try:           # (if anyone has >99 figures we are in trouble)
                        second_digit = int(to_write[ifig+shift+1])
                        fig_num = int(to_write[ifig+shift:ifig+shift+2])
                    except ValueError:
                        pass  # we were fine to start with

                if fig_num != 999:
                    # replace the word and number with an inline reference 
                    line_start = to_write[:ifig]
                    if fig_num > 9:
                        line_end = to_write[ifig+shift+2:]
                    else:
                        line_end = to_write[ifig+shift+1:]
                    if word in plurals:   # mark plurals because we won't have caught the second number
                        word_out = '\\textcolor{red}{%s}' % word
                    else:
                        word_out = word
                    to_write = line_start + word_out + '\\ref{%s%i}' % (ref_names[iw],fig_num) + \
                                line_end  # replace space with non-breaking space ~

    return to_write


def non_breaking_space(to_write):
    """
    look for places where we have a figure/table/equation ref, and try to replace leading space
    with ~ so it's non-breaking
    """

    word = '\\ref{'
    if word in to_write:
        nrefs = len([m.start() for m in finditer(re.escape(word),to_write)]) # find indices for \ref{
        # for each such index, look get the start and look before it
        for ireplace in range(nrefs):
            inds = np.array([m.start() for m in finditer(re.escape(word),to_write)])
            iref = inds[ireplace]
            if to_write[iref-1] == ' ':  # split here and replace
                iref = iref - 1
            elif to_write[iref-1] == '}':  # might be one of those plurals
                if to_write[iref-2] == ' ':
                    # split at iref-1
                    iref = iref - 2
            else:
                iref = -999  # who knows what's going on here

            if iref != -999:
                line_start = to_write[:iref]
                line_end = to_write[iref+1:]
                to_write = line_start + '~' + line_end  # easy peasy

    return to_write


def author_aliases(orcid_name,author_name):
    """
    check if a name listed for an orcid is the same as a name from the author list
    if the orcid name is initials and the author name is not, reduce author name to initials
    we are implicitly assuming that authors will not fill in orcids using initials if there
        are co-authors with identical initials
    """
    ismatch = False  # assume the names do not match to start with

    # pre-emptively replace all hyphens with spaces (I don't think this will be a bad thing?)
    author_name = re.sub(r'-',' ',author_name)
    orcid_name = re.sub(r'-',' ',orcid_name)

    # naive check if the two match
    if author_name == orcid_name:
        ismatch = True

    # if they don't, check if orcid_name is abbreviated at all
    else:
        orcid_given = orcid_name.split(' ')[0]
        orcid_last = ' '.join(orcid_name.split(' ')[1:])
        if re.match(r'[A-Z]\.',orcid_given):  # given name is abbreviated, at least
            # check if abbreviated first name plus orcid last name matches
            auth_given = author_name.split(' ')[0]
            auth_last = ' '.join(author_name.split(' ')[1:])
            auth_first_abbrev = auth_given[0] + '. ' + auth_last
            if auth_first_abbrev == orcid_name:
                ismatch = True  # this case should catch some van den Ende-like names

            # get initials from author_name and compare sans .s
            orcid_init = ''.join(c for c in orcid_name if c.isupper())
            author_bits = author_name.split(' ')
            author_init = ''.join(c[0] for c in author_bits)  # hopefully this works even for
                                    # names like McDonald etc
            if orcid_init == author_init:
                ismatch = True
    return ismatch


nonasc = {'−':r'\textendash','≤':r'$\leq$','≥':r'$\geq$','μ':r'$\mu$','°':r'$^\circ$',\
            'ö':'ö','é':'é','é':'é','ć':'ć'}

def check_non_ascii(line):
    """
    go through a line and either highlight non-ascii characters in red or replace them from 
    a pre-set list

    not currently used, since we are compiling lualatex with UTF-8 encoding :)
    """
    ibad = []
    what = []
    for i,s in enumerate(line):
        try:
            s.encode('ascii')
        except:
            ibad.append(i)
            what.append(s)

    if len(ibad) == 0:
        return line

    oline = ''
    for j, i in enumerate(ibad):
        if j == 0:  # first in the list
            pre = line[:i]
        else:
            pre = line[ibad[j-1]+1:i]
        oline += pre
        if what[j] in nonasc.keys():
            oline += nonasc[what[j]]
        else:
            oline += '\\textcolor{red}{nasc}'
    oline += line[ibad[j]+1:]

    return oline

def print_reminders(ofile_tex):
    print('An output tex file has been written at: %s' % ofile_tex)
    print('Unparsable table/figure info is in junk.tex')
    print('Remember to check authors/affils for non-ascii characters')
#    print('Remember to update metadata in header: editor, volume #, DOI, dates, etc')
    return

########################################################################
# citations
########################################################################

def parse_parentheticals(line,bibkeys,chars='()'):
    """
    for a line of text, parse parentheticals for citations and replace with appropriate cite calls
    """
    to_write = ''  # for appending pieces of text as they're checked
    copen = chars[0]; cclose = chars[1]
    if copen in line:  # check for parentheticals
        # find indices of open/close parens
        open_par = [pos for pos, char in enumerate(line) if char == copen]
        clse_par = [pos for pos, char in enumerate(line) if char == cclose]
        if len(open_par) != len(clse_par):
            # if there are excess ), check if they are for in-paragraph numbering/lists
            # make paired list of indices and types
            ipar = np.hstack((np.array(open_par),np.array(clse_par)))
            ioc = np.hstack((np.zeros(len(open_par)),np.ones(len(clse_par))))
            order = np.argsort(ipar)  # sort
            ioc = ioc[order]; ipar = ipar[order]

            # find any ) that are not preceded by (
            notclse = []
            for i,ii in enumerate(ioc):
                if ii == 1 and ioc[i-1] != 0:  # don't need to worry about 0th index being )
                                               # because we start with 'if ( in line'
                    iq = input('is this in-line numbering? [y]/n \n \t%s' \
                                % line[ipar[i]-5:ipar[i]+5]) or 'y'
                    if iq.lower() != 'y':
                        print('mismatched parentheticals :(')
                        print(line)
                        sys.exit()
                    else:
                        notclse.append(ipar[i])

            if len(notclse) > 0:  # now take the ok extra close parens out of clse_par
                clse_clean = []
                for c in clse_par:
                    if c not in notclse:
                        clse_clean.append(c)
                clse_par = clse_clean
                print('fixed?')

            #assert len(open_par) == len(clse_par), 'tried to match ( and ) but it failed'
            if len(open_par) != len(clse_par):
                pre = '\\textcolor{red}{mismatched parens, citations not parsed in this paragraph}'
                return pre + line

    else:  # no parentheticals in this line of text:
        return line

    # if there are parentheticals, move on to process them
    # first check for parens in parens and try to fix them
    open_del = []; clse_del = []
    for k in range(1,len(open_par)):
        if open_par[k] < clse_par[k-1]:
            open_del.append(k)
            clse_del.append(k-1)
    open_par = np.delete(open_par,open_del)
    clse_par = np.delete(clse_par,clse_del)

    # process what's left ->
    for k in range(len(open_par)):
        # separate out the parenthetical and the text between this and the previous parenthetical
        paren = line[open_par[k]+1:clse_par[k]]
        if k == 0:
            pretext = line[:open_par[k]]
        else:
            pretext = line[clse_par[k-1]+1:open_par[k]]  # the last bit of text before this parenthetical

        # check if this is inline math
        if pretext != '' and pretext[-1] == '\\':
        #if pretext[-1] == '\\':
            to_write += pretext
            to_write += line[open_par[k]:clse_par[k]+1]
            #break

        else:
            # if not math, continue to parse:
            parsed, pretext = _parse_paren(paren,pretext,bibkeys)

            # add the parsed stuff (pre-paren text may be altered for (YYYY) citations)
            to_write += pretext
            to_write += parsed

        if k == len(open_par) - 1:
            to_write += line[clse_par[-1]+1:]

    return to_write


def _parse_paren(paren, pretext, bibkeys):
    """
    parse whatever's in one set of parens
    """

    is_preamble = False  # non-citation text in the parenthetical before the first citation
    is_badref = False    # unparseable for some unknown reason
    is_abamb = False     # more than one paper by this author set for this year; resolve manually
    citations = []       # to hold list of bibkeys
    badtext = ''         # for text if only *some* refs are bad

    # check real quick if this is a single number
    if paren.isdigit() and len(paren) != 4:  # and isn't possibly a year
        return '('+paren+')', pretext

    # quick cleaning for \emph{et al.} in case someone used an unauthorized ref format
    paren = re.sub(r'\\emph{et al.}','et al.',paren)

    # split up the parenthetical by spaces -> this will have all punctuation preserved
    paren = paren.split(' ')

    # find years
    yr_inds = np.where([e[:4].isdigit() for e in paren])[0]

    # CASE: if all the contents are years, figure out citation from pre-paren text
    if len(yr_inds) == len(paren):
        # focus on the first year, then deal with any others
        prev = pretext.split(' ')[-2]
        if prev.startswith('al'):  # Alpha et al. (YYYY)
            prevprev = pretext.split(' ')[-4]
            test_cite = ''.join([prevprev,'EA',paren[0][:4]])

            is_badref,is_abamb = _test_test_cite(test_cite,bibkeys)
            if not is_badref and not is_abamb:
                citations.append(test_cite + 'a')
                pretext = ' '.join(pretext.split(' ')[:-4]) + ' ' # remove authors from line

        else:  # Alpha (YYYY) or Alpha and Beta (YYYY)
            test_cite = ''.join([prev,paren[0][:4]])  # try just one name first
            is_badref,is_abamb = _test_test_cite(test_cite, bibkeys)
            if not is_badref and not is_abamb:
                citations.append(test_cite + 'a')
                pretext = ' '.join(pretext.split(' ')[:-2]) + ' '
            elif is_badref:
                try:
                    prevprev = pretext.split(' ')[-4]  # skip backwards over expected "and"
                    test_cite = ''.join([prevprev,prev,paren[0][:4]])
                    is_badref,is_abamb = _test_test_cite(test_cite,bibkeys)
                    if not is_badref and not is_abamb:
                        citations.append(test_cite + 'a')
                        pretext = ' '.join(pretext.split(' ')[:-4]) + ' '
                except:  # something is not as expected, give up and highlight for later
                    is_badref = True
                    is_abamb = False
    

        # if we couldn't parse this thing, return something to write to mark it
        if is_badref:
            parsed = '\\textcolor{red}{bad ref skipped: %s}' % ' '.join(paren)
            return parsed, pretext
        if is_abamb:
            parsed = '\\textcolor{red}{a/b ambiguity: %s}' % ' '.join(paren)
            return parsed, pretext

        if len(yr_inds) > 1:  # ie more than one year, same authors - Alpha et al. (2010, 2011)
            for i in range(1,len(yr_inds)):
                initial_cite = test_cite[:-4]
                test_cite = ''.join([initial_cite,paren[i][:4]])
                is_badref,is_abamb = _test_test_cite(test_cite,bibkeys)
                if is_badref:
                    parsed = '\\textcolor{red}{bad ref skipped: %s}' % ' '.join(paren) 
                    return parsed, pretext
                if is_abamb:
                    parsed = '\\textcolor{red}{a/b ambiguity: %s}' % ' '.join(paren)
                    return parsed, pretext 
                if not is_badref and not is_abamb:
                    citations.append(test_cite + 'a')

        # having read through all possible years in this year-only parenthetical, 
        # compile citation and return
        parsed = r'\citet{'
        parsed += ', '.join(citations)  # add on citations and separators
        parsed += '}'  # remove trailing comma and space, close the bracket

        return parsed, pretext

    # CASE: not only years, so all citation info should be within the parens
    yr_inds = yr_inds + 1   # for easier looping/selecting the text bits
    yr_inds = np.append(0, yr_inds)

    # loop those year-index places
    for l in range(len(yr_inds) - 1):
        # choose bits corresponding to one particular year index
        bits = paren[yr_inds[l]:yr_inds[l+1]]
        # remove punctuation from these text pieces
        bits = [word.translate({ord(k): None for k in ['.',',','&','\\',';']}) \
                for word in bits]

        # check if this piece of the parenthetical is just a year (Alpha, 2010; 2011)
        if len(bits) == 1 and bits[0][:4].isdigit():
            # if we have a citation in the list already, try using that one
            if len(citations) == 0:  # nothing to work with here, not sure why
                badtext += 'bad ref: %s ' % bits[0]
            else:
                test_cite = citations[-1][:-5] + bits[0][:4]  # new citation to test
                is_badref,is_abamb = _test_test_cite(test_cite,bibkeys)
                if is_badref:
                    badtext += 'bad ref: %s ' % test_cite
                if is_abamb:
                    badtext += 'a/b: %s' % test_cite
                if not is_badref and not is_abamb:
                    citations.append(test_cite+'a')

        else:  # set of bits has more than just a year
            # replace et al. with EA, remove 'and' if present
            bits = _etal_and(bits)

            # make a test citation and see if it works
            test_cite = ''.join(bits)
            is_badref,is_abamb = _test_test_cite(test_cite,bibkeys)
            if is_abamb:
                badtext += 'a/b: %s ' % test_cite
            if is_badref and l == 0:
                for j in range(yr_inds[l]+1,yr_inds[l+1]):
                    bits = paren[j:yr_inds[l+1]]  # scrape off first word and try again
                    bits = [word.translate({ord(k): None for k in ['.',',','&','\\',';']}) \
                            for word in bits]
                    bits = _etal_and(bits)
                    test_cite = ''.join(bits)
                    is_badref,is_abamb = _test_test_cite(test_cite,bibkeys)
                    if not is_badref and is_abamb:
                        badtext += 'a/b AND preamble: %s ' % test_cite
                        break
                    if not is_badref and not is_abamb:
                        is_preamble = True
                        preamble_text = escape_latex(' '.join(paren[:j]))
                        break
                if is_badref: # we couldn't parse this one, even with scraping
                    bits = paren[yr_inds[l]:yr_inds[l+1]]
                    badtext += 'bad ref: %s' % ' '.join(bits)
            if is_badref and l != 0:  # can't read reference and it's not the first citation here
                badtext += 'bad ref: %s' % test_cite
            if not is_badref and not is_abamb:  # we parsed it! yay!
                citations.append(test_cite+'a')

    if len(badtext) != 0:
        badtext = r' \textcolor{red}{NOTE ' + badtext + '}'
    # combine citations into \citep, including preamble if there is one
    if len(citations) == 0:  # we failed to parse anything here :(
        if len(badtext) != 0 and is_abamb: 
            parsed = '(' + badtext + ')'  # might be an a/b that's the only one in the paren
        else:
            parsed = '(' + ' '.join(paren) + ')'  # put it back in parentheses and hope its ok
    else:
        if is_preamble:
            parsed = r'\citep[%s][]{' % preamble_text
        else:
            parsed = r'\citep{'
        parsed += ', '.join(citations)
        parsed += '}'

        if len(badtext) != 0:
            parsed += badtext

    return parsed, pretext


def _test_test_cite(test_cite,bibkeys):
    """
    take a citation tag and test it against bibkeys; return if no match or if a/b ambiguous
    """
    is_badref = False
    is_abamb = False

    if test_cite + 'a' not in bibkeys:  # used to be test_cite.lower() for both but biblib preserves case now
        is_badref = True
    else:
        if test_cite + 'b' in bibkeys:
            is_abamb = True

    return is_badref, is_abamb


def _etal_and(bits):
    """
    replace 'et al' with EA; remove 'and' from list of pieces
    """
    et_ind = [e == 'et' for e in bits]
    if sum(et_ind) > 0:
        et_ind = np.where(et_ind)[0][0]
        bits[et_ind] = 'E'
        bits[et_ind+1] = 'A'
    and_ind = [e == 'and' for e in bits]
    if sum(and_ind) > 0:
        and_ind = np.where(and_ind)[0][0]
        bits = np.delete(bits,and_ind)
    return bits

########################################################################
# bibtex and crossref stuff
########################################################################

def format_crossref_query(q,ret=['authors','title','doi','score','type','subtype','pdate'],i=0):
    """ Format information (keys in ret) from a dict (q)
    that is returned from a crossref query via habanero
    """
    out = {}
    qi = q['message']['items'][i]
    if 'title' in ret and 'title' in qi.keys():
        out['title'] = qi['title'][0]
    if 'doi' in ret and 'DOI' in qi.keys():
        out['doi'] = qi['DOI']
    if 'score' in ret and 'score' in qi.keys():
        out['score'] = qi['score']
    if 'type' in ret and 'type' in qi.keys():
        out['type'] = qi['type']
    if 'subtype' in ret and 'subtype' in qi.keys():
        out['subtype'] = qi['subtype']
    if 'pdate' in ret and 'published' in qi.keys():
        if 'date-parts' in qi['published'].keys():
            out['pdate'] = dp.parse('-'.join([str(e) for e in qi['published']['date-parts'][0]]))
    if 'authors' in ret and 'author' in qi.keys():
        auths = ''
        for a in qi['author']:
            if 'family' in a.keys() and 'given' in a.keys():
                auths = auths + a['given'] + ' ' + a['family'] + ', '
            elif 'name' in a.keys():
                auths = auths + a['name'] + ', '
        auths = auths[:-2]
        out['auths'] = auths
    return out

def print_query_options(q0,i=0):
    """ Take reformatted dict of query outputs and print relevant info,
    ask for user input to decide whether the query returned a good match
    Note: we're assuming title, authors, doi, and score will be in the output dict
        (type not assumed)
        this should usually be a good assumption? but could make more robust to keys
        if it turns out to be an issue
    """
    print('received:\n\ttitle: %s\n\tby: %s\n\tdoi: %s\n\tscore: %.2f' % (q0['title'],\
            q0['auths'], q0['doi'], q0['score']))
    if 'pdate' in q0.keys():
        print('\tyear: %i' % q0['pdate'].year)
    if 'type' in q0.keys():
        print('\ttype: %s' % q0['type'])
    if 'subtype' in q0.keys():
        print('\tsubtype: %s' % q0['subtype'])
    if i == 0:
        iok = input('accept this [y], reject query (n), or see next match (p): ') or 'y'
    else:
        iok = input('accept this [y], reject query (n), or use previous match (p): ') or 'y'
    return iok

def make_doi_url(doi,root='https://dx.doi.org/'):
    """ Construct url for requesting bibtex based on doi
    The only cleaning we do is to check if it ends with '. ' which I guess
        would indicate poor scraping from a sentence termination
    Some previous versions escaped certain characters (parens?) but that didn't
        seem to be necessary
    """
    if doi.lstrip().lower().startswith('doi:'):
        doi = doi.lstrip()[4:].lstrip()  # get rid of any doi: 10.etc syntax (old style)
    if '. ' in doi:
        ourl = "https://dx.doi.org/"+doi[0:doi.find('. ')]
    else:
        ourl = "https://dx.doi.org/"+doi
    return ourl


########################################################################
# tex escaping for python
########################################################################

_latex_special_chars = {
    '&': r'\&',
    '%': r'\%',
    '$': r'\$',
    '#': r'\#',
    '_': r'\_',
    '{': r'\{',
    '}': r'\}',
    '~': r'\textasciitilde{}',
    '^': r'\^{}',
    '\\': r'\textbackslash{}',
    '\n': '\\newline%\n',
    '-': r'{-}',
    '\xA0': '~',  # Non-breaking space
    '[': r'{[}',
    ']': r'{]}',
}

class NoEscape(str):
    """
    A simple string class that is not escaped.
    When a `.NoEscape` string is added to another `.NoEscape` string it will
    produce a `.NoEscape` string. If it is added to normal string it will
    produce a normal string.
    Args
    ----
    string: str
        The content of the `NoEscape` string.
    """

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self)

    def __add__(self, right):
        s = super().__add__(right)
        if isinstance(right, NoEscape):
            return NoEscape(s)
        return s

def escape_latex(s):
    r"""Escape characters that are special in latex.
    Args
    ----
    s : `str`, `NoEscape` or anything that can be converted to string
        The string to be escaped. If this is not a string, it will be converted
        to a string using `str`. If it is a `NoEscape` string, it will pass
        through unchanged.
    Returns
    -------
    NoEscape
        The string, with special characters in latex escaped.
    Examples
    --------
    >>> escape_latex("Total cost: $30,000")
    'Total cost: \$30,000'
    >>> escape_latex("Issue #5 occurs in 30% of all cases")
    'Issue \#5 occurs in 30\% of all cases'
    >>> print(escape_latex("Total cost: $30,000"))
    References
    ----------
        * http://tex.stackexchange.com/a/34586/43228
        * http://stackoverflow.com/a/16264094/2570866
    """

    if isinstance(s, NoEscape):
        return s

    return NoEscape(''.join(_latex_special_chars.get(c, c) for c in str(s)))

