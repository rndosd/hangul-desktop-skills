"""Bounded clustered bar ChartML authoring, not arbitrary chart editing."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from lxml import etree as E
C='{http://schemas.openxmlformats.org/drawingml/2006/chart}'
A='{http://schemas.openxmlformats.org/drawingml/2006/main}'
def build(template, matrix, title):
    if not isinstance(matrix,list) or not 2<=len(matrix)<=41: raise ValueError('ROW_COUNT')
    if any(not isinstance(r,list) or len(r)!=3 for r in matrix): raise ValueError('EXACT_THREE_COLUMNS')
    if any(not isinstance(v,str) or not v.strip() for r in matrix for v in r): raise ValueError('NONEMPTY_STRINGS')
    categories=[r[0] for r in matrix[1:]]
    if len(set(categories))!=len(categories): raise ValueError('DUPLICATE_CATEGORY')
    if matrix[0][1]==matrix[0][2]: raise ValueError('DUPLICATE_SERIES')
    for r in matrix[1:]:
        for v in r[1:]:
            try: n=Decimal(v)
            except InvalidOperation: raise ValueError('NUMBER_REQUIRED')
            if not n.is_finite(): raise ValueError('FINITE_NUMBER_REQUIRED')
    if sha256(template).hexdigest() != 'ed56b229600ba0081034244fa65d88b5cb7f5b901343e9c1fc2eb61b935919ab': raise ValueError('UNREVIEWED_TEMPLATE')
    root=E.fromstring(template)
    if root.tag!=C+'chartSpace': raise ValueError('CHARTSPACE_REQUIRED')
    if root.find('.//'+C+'externalData') is not None: raise ValueError('EXTERNAL_DATA_UNSUPPORTED')
    plot=root.find('./'+C+'chart/'+C+'plotArea')
    types=[e for e in plot if E.QName(e).localname.endswith('Chart')]
    if len(types)!=1 or types[0].tag!=C+'barChart': raise ValueError('ONLY_BAR')
    bars=types[0]
    if bars.find(C+'barDir').get('val')!='col' or bars.find(C+'grouping').get('val')!='clustered': raise ValueError('ONLY_CLUSTERED_COLUMN')
    series=bars.findall(C+'ser')
    if len(series)!=2: raise ValueError('EXACT_TWO_SERIES')
    for i,s in enumerate(series):
        s.find(C+'idx').set('val',str(i));s.find(C+'order').set('val',str(i))
        for expr,values in [(C+'tx/'+C+'strRef/'+C+'strCache',[matrix[0][i+1]]),
                            (C+'cat/'+C+'strRef/'+C+'strCache',categories),
                            (C+'val/'+C+'numRef/'+C+'numCache',[r[i+1] for r in matrix[1:]])]:
            cache=s.find(expr)
            if cache is None: raise ValueError('TEMPLATE_CACHE_REQUIRED')
            for x in list(cache):
                if x.tag in (C+'ptCount',C+'pt'): cache.remove(x)
            E.SubElement(cache,C+'ptCount',val=str(len(values)))
            for k,v in enumerate(values): E.SubElement(E.SubElement(cache,C+'pt',idx=str(k)),C+'v').text=v
        old=s.find(C+'spPr')
        if old is not None:s.remove(old)
        shape=E.Element(C+'spPr');fill=E.SubElement(shape,A+'solidFill')
        E.SubElement(fill,A+'srgbClr',val=('4472C4','ED7D31')[i]);s.insert(3,shape)
    t=root.find('./'+C+'chart/'+C+'title')
    if t is None:raise ValueError('TITLE_REQUIRED')
    old=t.find(C+'tx')
    if old is not None:t.remove(old)
    tx=E.Element(C+'tx');rich=E.SubElement(tx,C+'rich');E.SubElement(rich,A+'bodyPr');E.SubElement(rich,A+'lstStyle')
    p=E.SubElement(rich,A+'p');r=E.SubElement(p,A+'r');E.SubElement(r,A+'rPr',lang='ko-KR',sz='1100',b='1');E.SubElement(r,A+'t').text=title
    t.insert(0,tx)
    return E.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)

if __name__ == '__main__':
    import argparse,json
    from pathlib import Path
    p=argparse.ArgumentParser(description='Experimental fixed-design ChartML generator; no COM/UI')
    p.add_argument('--data',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();out=Path(a.output)
    if out.exists():raise FileExistsError('NEW_OUTPUT_REQUIRED')
    template=Path(__file__).resolve().parents[1]/'assets/chart-rebuild/clustered-column.xml'
    req=json.loads(Path(a.data).read_text(encoding='utf-8-sig'))
    data=build(template.read_bytes(),req['matrix'],req['title'])
    with out.open('xb') as dest:dest.write(data)
    print(out)
