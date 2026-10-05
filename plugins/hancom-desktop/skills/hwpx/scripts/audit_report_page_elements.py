"""Read-only checks for the measured Hancom 13 page-elements path; not completion attestation."""
from pathlib import Path
import copy,json,re,argparse,zipfile
from lxml import etree as E
import pymupdf as pdf
NS={'hp':'http://www.hancom.co.kr/hwpml/2011/paragraph','hh':'http://www.hancom.co.kr/hwpml/2011/head'}
P='{'+NS['hp']+'}'
def require(v,m):
 if not v:raise ValueError(m)
def norm(n):
 attrs=dict(n.attrib);children=list(n)
 if n.tag.endswith('lineSpacing') and attrs.get('type')=='PERCENT':attrs.pop('unit',None)
 if n.tag.endswith('switch') and any(c.tag.endswith('case') and c.get(P+'required-namespace')=='http://www.hancom.co.kr/hwpml/2016/HwpUnitChar' for c in children):children=[c for c in children if not c.tag.endswith('default')]
 if n.tag.endswith('charPr'):
  children=[c for c in children if not(c.tag.endswith('strikeout') and c.get('shape')=='NONE')];children.sort(key=lambda c:c.tag)
 return n.tag,tuple(sorted(attrs.items())),n.text or '',tuple(norm(c) for c in children)
def resolved_formats(path):
 with zipfile.ZipFile(path) as z:h=E.fromstring(z.read('Contents/header.xml'));s=E.fromstring(z.read('Contents/section0.xml'))
 ps={n.get('id'):n for n in h.findall('.//hh:paraPr',NS)};cs={n.get('id'):n for n in h.findall('.//hh:charPr',NS)};fonts={n.get('lang'):{f.get('id'):f.get('face') for f in n} for n in h.findall('.//hh:fontface',NS)};out=[]
 for p in s.findall('.//hp:p',NS):
  pp=copy.deepcopy(ps[p.get('paraPrIDRef')]);pp.attrib.pop('id',None);runs=[]
  for r in p.findall('hp:run',NS):
   t=r.find('hp:t',NS)
   # Only inactive control-bearing runs: native consolidates the control into
   # adjacent runs. Every visible-text and ordinary blank-cell run is checked.
   if p.findall('hp:run/hp:ctrl',NS) and (t is None or not ''.join(t.itertext())):continue
   c=copy.deepcopy(cs[r.get('charPrIDRef')]);c.attrib.pop('id',None);f=c.find('hh:fontRef',NS)
   if f is not None:
    for k,v in list(f.attrib.items()):f.set(k,fonts[k.upper()].get(v,'UNKNOWN'))
   runs.append((norm(c),t is not None))
  out.append((norm(pp),runs))
 return out

def audit(source,saved,pdf_path,options):
 require(resolved_formats(source)==resolved_formats(saved),'resolved active paragraph/character formatting changed')
 with zipfile.ZipFile(source) as z:s=E.fromstring(z.read('Contents/section0.xml'))
 require(len(list(s.iter(P+'pageNum')))==1,'page control inventory invalid');cover=options.get('cover',False);require(len(list(s.iter(P+'newNum')))==(1 if cover else 0),'restart inventory invalid')
 margin=s.find('.//'+P+'pagePr/'+P+'margin');top=(int(margin.get('top'))+int(margin.get('header')))/100;bottom=(int(margin.get('bottom'))+int(margin.get('footer')))/100
 doc=pdf.open(pdf_path);require(len(doc)>=2 if cover else len(doc)>=1,'page count invalid');observed=[];all_text=''.join(p.get_text(sort=True) for p in doc);compact=lambda x:re.sub(r'\s+','',x)
 for t in s.iter(P+'t'):
  if t.text:require(compact(t.text) in compact(all_text),'source text absent from native PDF: '+t.text[:40])
 for index,p in enumerate(doc):
  blocks=p.get_text('blocks');head=[b for b in blocks if b[1]<top];foot=[b for b in blocks if b[1]>p.rect.height-bottom];body=[b for b in blocks if b not in head+foot]
  if cover and index==0:require(not head and not foot,'cover page elements were not hidden');continue
  number=index if cover else index+1
  for key,zone in [('header_text',head),('footer_text',foot)]:
   if options.get(key):require(any(compact(options[key]) in compact(b[4]) for b in zone),'missing '+key)
  require(any(re.search(r'(?m)^-\s*'+str(number)+r'\s*-\s*$',b[4]) for b in foot),'wrong automatic page number');observed.append(number)
  if head and body:require(max(b[3] for b in head)<min(b[1] for b in body),'header overlaps body')
  if foot and body:require(max(b[3] for b in body)<min(b[1] for b in foot),'footer overlaps body')
  spans=[sp for b in p.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for sp in l['spans'] if sp['bbox'][1]>p.rect.height-bottom]
  nums=[sp for sp in spans if re.fullmatch(r'-\s*'+str(number)+r'\s*-',sp['text'].strip())]
  labels=[sp for sp in spans if options.get('footer_text') and compact(options['footer_text']) in compact(sp['text'])]
  if labels:require(nums and max(sp['bbox'][2] for sp in nums)+6<min(sp['bbox'][0] for sp in labels),'footer label overlaps centered number')
 return dict(status='checked_read_only',native='not_attested_by_this_audit',pages=len(doc),bodyNumberSequence=observed,coverElementsHidden=cover,headerFooterNoOverlap=True,allSourceFragmentsPresent=True,resolvedActiveFormattingEqual=True,limitation='Measured Hancom 13 active HwpUnitChar branch; strict control/preservation gate and actual all-page review remain required.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('saved');p.add_argument('pdf');p.add_argument('--options',required=True);p.add_argument('--output',required=True);a=p.parse_args();r=audit(a.source,a.saved,a.pdf,json.loads(Path(a.options).read_text(encoding='utf-8-sig')))
 with open(a.output,'x',encoding='utf8') as f:json.dump(r,f,ensure_ascii=False,indent=2)
 print(json.dumps(r,ensure_ascii=False))

