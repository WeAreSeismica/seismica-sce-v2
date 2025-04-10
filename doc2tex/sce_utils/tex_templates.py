import os, sys, datetime, re

def set_up_header(fout,title,authors={},affils={},credits={},\
                  anon=False,langs=False,breakmath=False,preprint=False,\
                  other_langs=[],manu='article'):
    """
    write out the basic seismica latex header
    fout is an open file handler ready for writing this header
    """
    # set up general options for the template
    docops = 'proof,'  # start with this default for conversion, easy to remove
    if anon: docops += 'anonymous,'
    if langs: docops += 'languages,'
    if breakmath: docops += 'breakmath,'
    if preprint: docops += 'preprint,'

    if re.search('invited',manu.lower()):
        docops += 'invited,'
        manu = re.sub(r'Invited',r'',manu)  # remove "invited" cap or non-cap from string
        manu = re.sub(r'invited',r'',manu)  # bc it goes in docops
        manu = manu.strip().strip(',')

    # set up for report header if it's a report
    report_string = """% if a report, specify report type:
"""
    if re.search('report',manu.lower()):
        report_string += """\\reporttype{""" + manu + """}"""
        docops += 'report,'
    else:
        report_string += """%\\reporttype{Report Type Here}"""
    # opinion is its own thing and is only in docops, no such thing as a "Fast Report Opinion" atm
    if re.search('opinion',manu.lower()): docops += 'opinion,'

    docops = docops[:-1]  # remove trailing comma

    header1 = """% Seismica Publication Template
% LuaLatex

%! TEX TS-program = lualatex
%! TEX encoding = UTF-8 Unicode
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% options: report, breakmath, proof, onecolumn, invited, opinion
\\documentclass["""+docops+"""]{seismica} 
"""+report_string+"""
% SCE team metadata:
\\dois{10.26443/seismica.v0i0.N}
\\receiveddate{DATE HERE}
\\accepteddate{DATE HERE}
\\publisheddate{DATE HERE}
\\theyear{"""+str(datetime.datetime.now().year)+"""}
\\thevolume{0}
\\thenumber{0}
\\prodedname{the production editor}
\\handedname{the handling editor}
\\copyedname{the copy/layout editor}
%\\reviewername{signed reviewer(s)}
%\\translatorname{translator(s)}
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\\title{"""+title+"""}
\\shorttitle{"""+title+"""}

"""
    fout.write(header1)

    # parse authors and affiliations
    for ik,k in enumerate(authors.keys()):
        auth = authors[k]
        towrite = '\\author['+auth['supers']+']{'+auth['name']
        if ik > 0:
            towrite = towrite.replace(' ','~')
        if 'orcid' in auth.keys():
            towrite += '\n\\orcid{'+auth['orcid']+'}'
        if 'corresp' in auth.keys():
            towrite += '\n\\thanks{Corresponding author: '+auth['corresp']+'}'
        towrite += '}\n'
        fout.write(towrite)
    fout.write('\n')

    for k in affils.keys():
        aff = affils[k]
        fout.write('\\affil['+aff['super']+']{'+aff['place']+'}\n')
    fout.write('\n')

    for k in credits.keys():
        fout.write('\\credit{'+k+'}{'+credits[k]+'}\n')
    fout.write('\n')

    if len(other_langs) > 0:
        header2 = """\\setotherlanguages{"""
        for l in other_langs:
            header2 += '%s,' % l
        header2 = header2[:-1]
        header2 += """}\n
%% Do not put arabic in \\setotherlanguages{} as it is not supported by polyglossia
%% Instead, use these commands within the text:
%%\\begin{Arabic} and \\end{Arabic} around paragraphs in Arabic
%%\\n{} to wrap any digits within Arabic text that should read left-to-right
%%\\textarabic{} for Arabic text embedded in a left-to-right paragraph

"""
        fout.write(header2)

    fout.write('\\begin{document}')

    return fout

def add_abstracts(fout,summaries):
    """
    write abstract(s) and optional non-technical summary into file after header
    """
    towrite = """
\\makeseistitle{\n"""
    for k in summaries.keys():
        abst = summaries[k]
        toadd = ''
        if abst['language'] != 'English':
            toadd += "\\begin{%s}\n" % abst['language']
        toadd += "\\begin{summary}{%s}\n" % abst['name']
        toadd += "%s\n\\end{summary}\n" % abst['text']
        if abst['language'] != 'English':
            toadd += "\\end{%s}\n" % abst['language']
        towrite += toadd

    towrite += "}\n"
    fout.write(towrite)

    return fout
