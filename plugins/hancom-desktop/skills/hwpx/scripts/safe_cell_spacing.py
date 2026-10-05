"""Hash-bound cell spacing adapter. Content, styles and non-target XML are immutable."""
from pathlib import Path
import argparse,json,copy,math,hashlib,tempfile,os
from importlib.metadata import version
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
from safe_cell_layout import P,require,sha,parts,xml,locate
SCHEMA='hwpx.safe-cell-spacing.v1'
SIDES=('left','right','top','bottom')
def snapshot(n,cache=False):
 if cache and n.tag==P+'linesegarray':return None
 return n.tag,tuple(sorted(n.attrib.items())),n.text or '',n.tail or '',tuple(x for c in n for x in [snapshot(c,cache)] if x is not None)
def shape(t):
 rows=t.findall(P+'tr');require(2<=len(rows)<=100 and len(rows)==int(t.get('rowCnt','0')),'bounded table rows required');cols=int(t.get('colCnt','0'));require(1<=cols<=12,'bounded columns required');cells={};grid={}
 for y,row in enumerate(rows):
  for c in row.findall(P+'tc'):
   require(set(n.tag for n in c)=={P+x for x in ['subList','cellAddr','cellSpan','cellSz','cellMargin']} and len(c)==5,'unsupported cell shape')
   a=c.find(P+'cellAddr');sp=c.find(P+'cellSpan');sz=c.find(P+'cellSz');at=(int(a.get('rowAddr')),int(a.get('colAddr')));sy,sx=int(sp.get('rowSpan')),int(sp.get('colSpan'));require(at[0]==y and at not in cells and sy>=1 and sx>=1 and int(sz.get('width'))>0 and int(sz.get('height'))>0,'invalid geometry')
   sub=c.find(P+'subList');require(sub.get('textDirection')=='HORIZONTAL' and sub.get('lineWrap') in ['BREAK','SQUEEZE'] and sub.get('vertAlign') in ['TOP','CENTER','BOTTOM'],'unsupported text direction/layout');ps=sub.findall(P+'p');require(1<=len(ps)<=20 and len(sub)==len(ps),'1..20 plain paragraphs required')
   for p in ps:
    runs=p.findall(P+'run');require(1<=len(runs)<=20 and all(n.tag in [P+'run',P+'linesegarray'] for n in p),'plain paragraph required')
    for run in runs:
     require(len(run)<=4 and all(n.tag==P+'t' for n in run),'control-bearing/rich run unsupported')
     for text in run:
      require(not any(ch in (text.text or '') for ch in '\r\n\t') and all(n.tag==P+'lineBreak' and not len(n) and not n.attrib and not any(ch in (n.tail or '') for ch in '\r\n\t') for n in text),'only native lineBreak children supported')
   require(c.get('hasMargin') in ['0','1'],'unknown margin inheritance');cells[at]=c
   for yy in range(at[0],at[0]+sy):
    for xx in range(at[1],at[1]+sx):require((yy,xx) not in grid,'cell overlap');grid[yy,xx]=at
 require(set(grid)=={(y,x) for y in range(len(rows)) for x in range(cols)},'invalid table coverage');return cells,grid

def effective(c,t):
 margin=c.find(P+'cellMargin') if c.get('hasMargin')=='1' else t.find(P+'inMargin');require(margin is not None and set(margin.attrib)==set(SIDES),'four effective margins required');out={k:int(margin.get(k)) for k in SIDES};require(all(v>=0 for v in out.values()),'negative existing margin');return out

def inspect(source,table):
 _,part,_,t=locate(Path(source).read_bytes(),table);cs,grid=shape(t)
 return dict(schema=SCHEMA,source_sha256=sha(source),table=table,part=part,cells=[dict(row=a[0]+1,column=a[1]+1,span={k:int(c.find(P+'cellSpan').get(k)) for k in ['rowSpan','colSpan']},paragraphs=len(c.find(P+'subList')),runs=len(list(c.iter(P+'run'))),nativeLineBreaks=len(list(c.iter(P+'lineBreak'))),vertical_align=c.find(P+'subList').get('vertAlign'),line_wrap=c.find(P+'subList').get('lineWrap'),own_margins=c.get('hasMargin')=='1',effective_margins_mm={k:round(v*25.4/7200,3) for k,v in effective(c,t).items()},texts=[''.join(n.itertext()) for n in c.iter(P+'t')]) for a,c in cs.items()])

def edits(req,t):
 cs,grid=shape(t);require(set(req)=={'schema','source_sha256','table','edits'} and req.get('schema')==SCHEMA,'request schema/keys invalid');rows=req['edits'];require(isinstance(rows,list) and 1<=len(rows)<=50,'1..50 cell edits required');out={}
 for item in rows:
  require(isinstance(item,dict) and not(set(item)-{'row','column','vertical_align','margins_mm','line_wrap'}) and {'row','column'}<=set(item),'cell edit keys invalid');require(type(item['row']) is int and type(item['column']) is int,'integer 1-based address required');a=item['row']-1,item['column']-1;require(a in cs,'exact merged-cell anchor required');require(a not in out,'duplicate cell edit');c=cs[a];require(c.get('protect','0')=='0','protected target unsupported');spec={}
  if 'vertical_align' in item:require(item['vertical_align'] in ['TOP','CENTER','BOTTOM'],'invalid vertical alignment');spec['vertical_align']=item['vertical_align']
  if 'line_wrap' in item:require(item['line_wrap']=='BREAK','only explicit BREAK conversion supported');spec['line_wrap']='BREAK';require(t.get('noAdjust','0')=='0' and t.find(P+'sz').get('protect','0')=='0','fixed-size wrapping requires separate review')
  if 'margins_mm' in item:
   m=item['margins_mm'];require(isinstance(m,dict) and m and set(m)<=set(SIDES),'one or more explicit margin sides required');values=effective(c,t)
   for k,v in m.items():require(type(v) in [int,float] and math.isfinite(v) and 0<=v<=10,'finite 0..10mm margin required');values[k]=round(v*7200/25.4)
   require(int(c.find(P+'cellSz').get('width'))-values['left']-values['right']>=round(5*7200/25.4),'at least 5mm usable width required');spec['margins']=values
  require(spec,'empty cell edit');out[a]=spec
 return out

def expected_cell(c,spec):
 e=copy.deepcopy(c);sub=e.find(P+'subList')
 if 'vertical_align' in spec:sub.set('vertAlign',spec['vertical_align'])
 if 'line_wrap' in spec:sub.set('lineWrap',spec['line_wrap'])
 if 'margins' in spec:
  e.set('hasMargin','1');m=e.find(P+'cellMargin')
  for k,v in spec['margins'].items():m.set(k,str(v))
 return e

def verify(before,after,req):
 require(hashlib.sha256(before).hexdigest()==req.get('source_sha256'),'verifier source hash mismatch')
 bm,part,br,bt=locate(before,req['table']);am,ap,ar,at=locate(after,req['table']);require(part==ap and set(bm)==set(am),'package inventory changed');bc,bg=shape(bt);ac,ag=shape(at);changes=edits(req,bt);require(set(bc)==set(ac) and bg==ag,'cell geometry changed')
 def outside(n,t):
  if n is t:return ('selected-table',)
  return n.tag,tuple(sorted(n.attrib.items())),n.text or '',n.tail or '',tuple(outside(c,t) for c in n)
 require(outside(br,bt)==outside(ar,at),'non-target section changed');require(dict(bt.attrib)==dict(at.attrib),'table attributes changed');require([snapshot(n) for n in bt if n.tag!=P+'tr']==[snapshot(n) for n in at if n.tag!=P+'tr'],'table settings changed');require([dict(n.attrib) for n in bt.findall(P+'tr')]==[dict(n.attrib) for n in at.findall(P+'tr')],'row attributes changed')
 for a,c in bc.items():require(snapshot(expected_cell(c,changes[a]),True)==snapshot(ac[a],True) if a in changes else snapshot(c)==snapshot(ac[a]),'cell content/format changed beyond request: '+str(a))
 for n in bm:
  if n!=part:require(bm[n]==am[n],'non-target package payload changed: '+n)
 require([(n.text or '',n.tail or '') for n in br.iter() if n.tag in [P+'t',P+'lineBreak']]==[(n.text or '',n.tail or '') for n in ar.iter() if n.tag in [P+'t',P+'lineBreak']],'text or line-break tails changed')
 return dict(nonTargetXmlAndPackageEqual=True,paragraphsRunsAndNativeBreaksPreserved=True,allActiveStylesUnchanged=True,requestedSpacingExact=True,cellGeometryUnchanged=True)

def apply(source,output,req,dry_run=False):
 source=Path(source).resolve();output=Path(output).absolute();require(version('python-hwpx')=='6.3.0','unverified core version');require(source.suffix.lower()=='.hwpx' and output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and output.resolve()!=source,'new hwpx output required');require(req.get('source_sha256')==sha(source),'stale source hash');before=source.read_bytes();_,part,_,t=locate(before,req.get('table'));changes=edits(req,t)
 with HwpxDocument.open(source) as doc:
  tables=[x for s in doc.sections for p in s.paragraphs for x in p.tables];found=[x for x in tables if x.element.get('id')==t.get('id') and x.paragraph.section.part_name==part];require(len(found)==1,'ambiguous public table binding');table=found[0]
  for (y,x),spec in changes.items():
   cell=table.cell(y,x);require(cell.address==(y,x),'covered-cell binding refused');c=cell.element;sub=c.find(P+'subList')
   # Dedicated bounded OXML-property adapter, not a general XML fallback.
   if 'vertical_align' in spec:sub.set('vertAlign',spec['vertical_align'])
   if 'line_wrap' in spec:sub.set('lineWrap',spec['line_wrap'])
   if 'margins' in spec:
    c.set('hasMargin','1');m=c.find(P+'cellMargin')
    for k,v in spec['margins'].items():m.set(k,str(v))
   for p in cell.paragraphs:
    for cache in list(p.element.findall(P+'linesegarray')):p.element.remove(cache)
  table.mark_dirty();after=doc.to_bytes()
 checks=verify(before,after,req)
 with tempfile.TemporaryDirectory(prefix='cell-spacing-',dir=output.parent) as tmp:
  p=Path(tmp)/'candidate.hwpx';p.write_bytes(after);require(validate_editor_open_safety(p).ok,'open safety failed');require(sha(source)==req['source_sha256'],'source changed during edit')
  if not dry_run:os.link(p,output)
 return dict(schema='hwpx.safe-cell-spacing-receipt.v1',status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',native='pending',source_sha256=req['source_sha256'],candidate_sha256=hashlib.sha256(after).hexdigest(),published=not dry_run,request=req,checks=checks)
if __name__=='__main__':
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True);i=sub.add_parser('inspect');i.add_argument('source');i.add_argument('--table',type=int,required=True);i.add_argument('--output',required=True);a=sub.add_parser('apply');a.add_argument('source');a.add_argument('output');a.add_argument('--request',required=True);a.add_argument('--dry-run',action='store_true');v=p.parse_args()
 if v.cmd=='inspect':
  with open(v.output,'x',encoding='utf8') as f:json.dump(inspect(v.source,v.table),f,ensure_ascii=False,indent=2)
 else:print(json.dumps(apply(v.source,v.output,json.loads(Path(v.request).read_text(encoding='utf-8-sig')),v.dry_run),ensure_ascii=False,indent=2))
