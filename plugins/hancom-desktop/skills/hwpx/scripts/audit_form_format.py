# SPDX-License-Identifier: Apache-2.0
"""Read exact layout settings; never interprets caches as native rendering."""
from zipfile import ZipFile
from safe_edit import digest,local,parse,sections


def details(node):
    return {'tag':local(node),'attributes':dict(node.attrib),'text':node.text or '',
            'children':[details(c) for c in node]}


def audit_format(source):
    with ZipFile(source) as z:
        header=parse(z.read('Contents/header.xml'))
        paras={n.get('id'):n for n in header.iter() if local(n)=='paraPr'}
        chars={n.get('id'):n for n in header.iter() if local(n)=='charPr'}
        font_defs=[details(n) for n in header.iter() if local(n)=='fontface']
        numbering=[details(n) for n in header.iter() if local(n) in ('numbering','bullet')]
    pages=[];paragraphs=[];tables=[];number=0
    for part,root in sections(source):
        for n in root.iter():
            if local(n)=='pagePr':pages.append(details(n))
        def walk(node,path):
            nonlocal number
            if local(node)=='p':
                style=paras.get(node.get('paraPrIDRef'))
                paragraphs.append({'part':part,'path':path,'attributes':dict(node.attrib),
                                   'paragraph_format':details(style) if style is not None else None,
                                   'runs':[{'index':i,'attributes':dict(r.attrib),
                                            'character_format':details(chars[r.get('charPrIDRef')]) if r.get('charPrIDRef') in chars else None}
                                           for i,r in enumerate(node) if local(r)=='run']})
            if local(node)=='tbl':
                number+=1;cells=[]
                for row in node:
                    if local(row)!='tr':continue
                    for cell in row:
                        if local(cell)!='tc':continue
                        cells.append({'attributes':dict(cell.attrib),
                                      'geometry_margins_alignment':[details(c) for c in cell if local(c) in ('cellAddr','cellSpan','cellSz','cellMargin')],
                                      'sublist_attributes':[dict(c.attrib) for c in cell if local(c)=='subList']})
                tables.append({'number':number,'attributes':dict(node.attrib),
                               'size_and_margins':[details(c) for c in node if local(c) in ('sz','inMargin','outMargin','pos')],
                               'cells':cells})
            for i,c in enumerate(node):walk(c,path+[i])
        walk(root,[])
    return {'schema':'hwpx.existing-form-format-audit.v1','sha256':digest(source),
            'page_settings':pages,'font_definitions':font_defs,'numbering_definitions':numbering,
            'paragraphs':paragraphs,'tables':tables,'scope':'XML settings only; no text/body export',
            'checks':['horizontal/vertical paragraph alignment','page margins','font height/ratio/spacing by language',
                      'line and paragraph spacing','indent/hanging indent','cell padding/vertical alignment',
                      'row/column owner sizes','merged cells','heading/numbering references','word/line/page/column breaks'],
            'native_page_count':'not_checked','actual_linebreaks_clipping_and_pagination':'UNVERIFIED'}
