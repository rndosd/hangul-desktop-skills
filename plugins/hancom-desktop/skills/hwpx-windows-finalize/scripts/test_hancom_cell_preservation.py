from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
import pymupdf as F
import json, argparse
parser=argparse.ArgumentParser(description='E01/E02 labelled fixture semantic and native-PDF regression; not a general document validator.')
parser.add_argument('--results', required=True)
parser.add_argument('--source', required=True)
args=parser.parse_args()
o=Path(args.results)
def read(p):
 with ZipFile(p) as z:return E.fromstring(z.read('Contents/section0.xml')),E.fromstring(z.read('Contents/header.xml'))
def flat(r):
 out={}
 def walk(e,p):
  if E.QName(e).localname=='linesegarray':return
  out[p]=dict(attributes=dict(e.attrib),text=e.text);counts={}
  for c in e:
   name=E.QName(c).localname;counts[name]=counts.get(name,0)+1;walk(c,p+'/'+name+str(counts[name]))
 walk(r,'root');return out
src,_=read(Path(args.source));a,ha=read(o/'baseline.hwpx');b,hb=read(o/'right.hwpx')
fa,fb=flat(a),flat(b)
diff=[dict(path=k,A=fa.get(k),B=fb.get(k)) for k in sorted(fa.keys()|fb.keys()) if fa.get(k)!=fb.get(k)]
assert len(diff)==1 and diff[0]['A']['attributes']['id']=='1453915368'
aa=diff[0]['A']['attributes'];bb=diff[0]['B']['attributes'];assert {k for k in aa.keys()|bb.keys() if aa.get(k)!=bb.get(k)}=={'paraPrIDRef'}
pa=ha.xpath('//*[local-name()="paraPr"][@id="'+aa['paraPrIDRef']+'"]')[0]
pb=hb.xpath('//*[local-name()="paraPr"][@id="'+bb['paraPrIDRef']+'"]')[0]
fpa,fpb=flat(pa),flat(pb)
ppdiff=[dict(path=k,A=fpa.get(k),B=fpb.get(k)) for k in sorted(fpa.keys()|fpb.keys()) if fpa.get(k)!=fpb.get(k)]
assert len(ppdiff)==2
assert pa.find('{*}align').get('horizontal')=='JUSTIFY' and pb.find('{*}align').get('horizontal')=='RIGHT'
for kind in ['paraPr','charPr','borderFill','style','font']:
 left=ha.xpath('//*[local-name()="'+kind+'"]');right=hb.xpath('//*[local-name()="'+kind+'"]')
 assert len(right)==len(left)+(1 if kind=='paraPr' else 0)
 for x,y in zip(left,right):assert flat(x)==flat(y)
labels=['OUTER_R1C1_HOST','OUTER_R1C2_STABLE','OUTER_R2C1_STABLE','OUTER_R2C2_STABLE','INNER_R1C1','INNER_R1C2','INNER_R2C1','INNER_R2C2']
for r in [src,a,b]:
 texts=r.xpath('//*[local-name()="t"]/text()');assert all(texts.count(x)==1 for x in labels)
 assert len(r.findall('.//{*}tbl'))==2
assert src.xpath('//*[local-name()="t"]/text()')==a.xpath('//*[local-name()="t"]/text()')==b.xpath('//*[local-name()="t"]/text()')
docs=[F.open(o/f'{n}.pdf') for n in ['baseline','right']];assert all(len(d)==1 for d in docs)
def chars(p):return [c for block in p.get_text('rawdict')['blocks'] if 'lines' in block for line in block['lines'] for span in line['spans'] for c in span['chars']]
rawa,rawb=[chars(d[0]) for d in docs]
target=lambda c:63<c['origin'][0]<86 and 180<c['origin'][1]<261
assert [c for c in rawa if not target(c)]==[c for c in rawb if not target(c)]
ca,cb=[[c for c in cs if not c['c'].isspace()] for cs in [rawa,rawb]]
assert [c['c'] for c in ca]==[c['c'] for c in cb]
changed=[]
for x,y in zip(ca,cb):
 if x['origin']!=y['origin']:
  assert 63<x['origin'][0]<86 and 180<x['origin'][1]<261
  assert abs(x['origin'][1]-y['origin'][1])<0.001
  changed.append(dict(char=x['c'],A=x['origin'],B=y['origin'],dx=y['origin'][0]-x['origin'][0]))
assert changed
def drawings(p):return [(str(x['items']),x['width'],x['color'],x['fill'],str(x['rect'])) for x in p.get_drawings()]
assert drawings(docs[0][0])==drawings(docs[1][0])
result=dict(status='PASS_BOUNDED_NESTED_PARAGRAPH_EDIT',sourceAllTextsPreserved=True,allEightLabelsOnce=True,tableCount=2,sectionDifference=diff,paragraphDefinitionDifference=ppdiff,pdfPages=[1,1],pdfNonWhitespaceCharacterSequencePreserved=True,pdfTargetExtractedText=[''.join(c['c'] for c in cs if target(c)) for cs in [rawa,rawb]],whitespacePolicy='Target JUSTIFY spacing can extract as synthetic spaces; all non-target raw characters, all non-whitespace characters, and native HWPX texts are separately verified.',changedCharacters=changed,allOtherCharacterCoordinatesUnchanged=True,allDrawingGeometryUnchanged=True)
(o/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(status=result['status'],targetParaPr=[aa['paraPrIDRef'],bb['paraPrIDRef']],changedCharacters=changed),ensure_ascii=False,indent=2))
