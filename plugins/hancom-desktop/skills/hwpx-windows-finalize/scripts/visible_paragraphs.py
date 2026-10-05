"""Strict paragraph visibility across page chrome; never edits a document.

Full text remains the first check. Alternative streams may exclude only exact
known header/footer/one-line footnote text in its declared page region, or an
explicit DIGIT/BOTTOM_CENTER page number outside the printable body.
"""
import re
import pymupdf as pdf
P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'
def norm(text):return ''.join(text.split())
def chrome(root,char_heights=None):
 char_heights=char_heights or {}
 page=root.find('.//'+P+'pagePr');m=page.find(P+'margin')
 top=int(m.get('top'))/100;bottom=int(page.get('height'))/100-int(m.get('bottom'))/100
 known=[]
 for kind in ['header','footer','footNote']:
  for n in root.iter(P+kind):
   # Do not remove compound or tabular stories as if they were one-line text.
   if any(c.tag==P+'tbl' for c in n.iter()):continue
   paragraphs=list(n.iter(P+'p'))
   if len(paragraphs)!=1:continue
   text=norm(''.join(c.text or '' for c in paragraphs[0].iter(P+'t')))
   if text:known.append(dict(kind=kind,text=text,fontHeight=max([char_heights.get(c.get('charPrIDRef'),10) for c in n.iter(P+'run')]+[10])))
 number_height=max([char_heights.get(run.get('charPrIDRef'),10) for run in root.iter(P+'run') if any(True for _ in run.iter(P+'pageNum'))]+[10])
 digits=any(n.get('pos')=='BOTTOM_CENTER' and n.get('formatType')=='DIGIT' and n.get('sideChar')=='-' for n in root.iter(P+'pageNum'))
 return dict(top=top,bottom=bottom,known=known,digits=digits,pageNumberHeight=number_height)
def lines(page):
 result=[]
 for b in page.get_text('dict')['blocks']:
  if b.get('type')!=0:continue
  for line in b['lines']:
   result.append(dict(text=''.join(s['text'] for s in line['spans']),box=line['bbox']))
 return result
def assess(path,expected,contract):
 streams={'drawing':[],'coordinate':[],'bodyDrawing':[],'bodyCoordinate':[]};excluded=[]
 with pdf.open(path) as doc:
  for number,page in enumerate(doc):
   streams['drawing'].append(page.get_text());streams['coordinate'].append(page.get_text(sort=True))
   retained=[]
   for line in lines(page):
    text=norm(line['text']);x0,y0,x1,y1=line['box'];matched=None
    for known in contract['known']:
     valid=(known['kind']=='header' and y1<=contract['top']+known.get('fontHeight',10)+2 or known['kind']=='footer' and y0>=contract['bottom']-known.get('fontHeight',10)-2 or known['kind']=='footNote' and y0>=page.rect.height*.75)
     note_prefix=text[:-len(known['text'])] if text.endswith(known['text']) else None
     exact=text==known['text'] or known['kind']=='footNote' and note_prefix is not None and re.fullmatch(r'\d+\)',note_prefix) is not None
     if valid and exact:matched=known['kind'];break
    if matched is None and contract['digits'] and y0>=contract['bottom']-contract.get('pageNumberHeight',10)-2 and page.rect.width*.35<=x0<x1<=page.rect.width*.65 and re.fullmatch(r'-\d+-',text):matched='pageNum'
    if matched:excluded.append(dict(page=number+1,kind=matched,text=line['text'],bbox=line['box']))
    else:retained.append(line)
   streams['bodyDrawing'].append(''.join(x['text'] for x in retained))
   streams['bodyCoordinate'].append(''.join(x['text'] for x in sorted(retained,key=lambda v:(round(v['box'][1],1),v['box'][0]))))
  page_count=len(doc)
 normalized={k:norm(''.join(v)) for k,v in streams.items()}
 matches=[dict(expected=e,streams=[k for k,v in normalized.items() if norm(e) in v]) for e in expected]
 missing=[x['expected'] for x in matches if not x['streams']]
 return dict(status='PASS_VISIBLE_TEXT' if not missing else 'FAIL_VISIBLE_TEXT',pages=page_count,missing=missing,matches=matches,excludedKnownChrome=excluded,contract=contract,limitation='Text visibility only; not pixel identity, paragraph order, style, native-file preservation or independent visual acceptance')
