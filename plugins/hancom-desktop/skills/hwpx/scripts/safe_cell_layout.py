from workspace_candidate_directory import workspace_candidate_directory
"""Bounded existing-cell geometry and horizontal alignment through 6.3.0 APIs."""
from pathlib import Path
import json,hashlib,zipfile,io,copy,os,tempfile,argparse
from importlib.metadata import version
from lxml import etree as E
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'
H='{http://www.hancom.co.kr/hwpml/2011/head}'
SCHEMA='hwpx.safe-cell-layout.v1'
def require(x,s):
 if not x:raise ValueError(s)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def parts(data):
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  require(len(z.namelist())==len(set(z.namelist())),'duplicate package member')
  return {n:z.read(n) for n in z.namelist()}
def xml(b):
 n=E.fromstring(b,E.XMLParser(resolve_entities=False,no_network=True,load_dtd=False));require(not n.getroottree().docinfo.doctype,'DTD unsupported');return n
def snap(n,drop_cache=False,drop_id=False):
 if drop_cache and n.tag==P+'linesegarray':return None
 at=dict(n.attrib)
 if drop_id and n.tag==P+'p':at.pop('id',None)
 return (n.tag,tuple(sorted(at.items())),n.text or '',tuple(x for c in n for x in [snap(c,drop_cache,drop_id)] if x is not None))
def locate(data,index):
 m=parts(data);found=[]
 for part in sorted(m):
  if part.startswith('Contents/section') and part.endswith('.xml'):
   r=xml(m[part]);found.extend((part,r,t) for t in r.iter(P+'tbl'))
 require(type(index) is int and 1<=index<=len(found),'table out of range')
 part,r,t=found[index-1];require(not any(a.tag==P+'tbl' for a in t.iterancestors()),'nested target unsupported');return m,part,r,t

def geometry(t):
 require(2<=int(t.get('rowCnt','0'))<=100 and 1<=int(t.get('colCnt','0'))<=12,'table bounds unsupported')
 rows=t.findall(P+'tr');require(len(rows)==int(t.get('rowCnt')),'row inventory invalid');cells={};grid={}
 for ri,row in enumerate(rows):
  for c in row.findall(P+'tc'):
   ad=c.find(P+'cellAddr');sp=c.find(P+'cellSpan');sz=c.find(P+'cellSz');require(all(v is not None for v in (ad,sp,sz)),'cell geometry missing')
   a=(int(ad.get('rowAddr')),int(ad.get('colAddr')));s=(int(sp.get('rowSpan')),int(sp.get('colSpan')))
   require(a[0]==ri and s[0]>=1 and s[1]>=1 and a not in cells,'invalid anchor');require(int(sz.get('width'))>0 and int(sz.get('height'))>0,'positive size required')
   for n in c.iter():require(n.tag not in [P+x for x in ['tbl','pic','ctrl','fieldBegin','fieldEnd','equation','rect']],'rich/nested cell unsupported')
   ps=c.findall('./'+P+'subList/'+P+'p');require(len(ps)==1,'one paragraph per cell required');runs=ps[0].findall(P+'run');require(len(runs)==1 and (len(runs[0])==0 or len(runs[0])==1 and runs[0][0].tag==P+'t' and not len(runs[0][0])),'one plain or native empty run required')
   cells[a]=c
   for y in range(a[0],a[0]+s[0]):
    for x in range(a[1],a[1]+s[1]):require((y,x) not in grid,'overlap');grid[y,x]=a
 require(set(grid)=={(y,x) for y in range(len(rows)) for x in range(int(t.get('colCnt')))},'invalid coverage');return cells,grid

def span(c):return tuple(int(c.find(P+'cellSpan').get(k)) for k in ['rowSpan','colSpan'])
def text(c):return ''.join(c.itertext())
def paragraph(c):return c.find('./'+P+'subList/'+P+'p')
def size(c):return tuple(int(c.find(P+'cellSz').get(k)) for k in ['height','width'])
def bounds(req,t):
 r=req.get('range');require(isinstance(r,list) and len(r)==4 and all(type(v) is int for v in r),'four 1-based integer coordinates required');r0,c0,r1,c1=[v-1 for v in r];require(0<=r0<=r1<int(t.get('rowCnt')) and 0<=c0<=c1<int(t.get('colCnt')),'range outside table');return r0,c0,r1,c1

def inspect(source,table):
 _,part,_,t=locate(Path(source).read_bytes(),table);cells,_=geometry(t)
 return dict(schema=SCHEMA,source_sha256=sha(source),table=table,part=part,cells=[dict(row=a[0]+1,column=a[1]+1,span=list(span(c)),text=text(c),size_hwpunit=list(size(c))) for a,c in cells.items()])

def verify(before,after,req):
 bm,part,br,bt=locate(before,req['table']);am,ap,ar,at=locate(after,req['table']);require(part==ap and set(bm)==set(am),'package inventory changed')
 bc,bg=geometry(bt);ac,ag=geometry(at);r0,c0,r1,c1=bounds(req,bt);op=req['operation'];anchor=(r0,c0)
 targets={(y,x) for y in range(r0,r1+1) for x in range(c0,c1+1)}
 require(dict(bt.attrib)==dict(at.attrib),'table attributes changed')
 def outside(n,t):
  if n is t:return ('target-table',)
  return (n.tag,tuple(sorted(n.attrib.items())),n.text or '',tuple(outside(c,t) for c in n))
 require(outside(br,bt)==outside(ar,at),'non-target section changed')
 require([snap(c) for c in bt if c.tag!=P+'tr']==[snap(c) for c in at if c.tag!=P+'tr'],'table properties changed')
 require([dict(r.attrib) for r in bt.findall(P+'tr')]==[dict(r.attrib) for r in at.findall(P+'tr')],'row attributes changed')
 for a,c in bc.items():
  if a not in targets:require(a in ac and snap(c)==snap(ac[a]),'non-target cell changed')
 expectedanchors=(set(bc)-targets|{anchor}) if op=='merge' else (set(bc)|targets) if op=='unmerge' else set(bc)
 require(set(ac)==expectedanchors,'unexpected physical cells')
 if op in ['merge','unmerge']:
  require(all((text(c)==text(bc[anchor]) if a==anchor else not text(c)) for a,c in ac.items() if a in targets),'target content loss/duplication')
  old=bc[anchor];h,w=size(old)
  if op=='merge':h=sum(size(bc[y,c0])[0] for y in range(r0,r1+1));w=sum(size(bc[r0,x])[1] for x in range(c0,c1+1))
  expected=copy.deepcopy(old);s=expected.find(P+'cellSpan');s.set('rowSpan',str(r1-r0+1 if op=='merge' else 1));s.set('colSpan',str(c1-c0+1 if op=='merge' else 1));z=expected.find(P+'cellSz');z.set('height',str(h if op=='merge' else h//(r1-r0+1)));z.set('width',str(w if op=='merge' else w//(c1-c0+1)))
  require(snap(expected,True)==snap(ac[anchor],True),'anchor formatting/geometry changed')
  if op=='unmerge':
   # Equal, exact subdivision only: no reconstructed unequal source grid promised.
   for a in targets-{anchor}:
    e=copy.deepcopy(ac[anchor]);addr=e.find(P+'cellAddr');addr.set('rowAddr',str(a[0]));addr.set('colAddr',str(a[1]));pp=paragraph(e)
    for run in pp.findall(P+'run'):
     for n in list(run):run.remove(n)
    # API creates an empty text leaf; the native renderer may later remove it.
    # Newly synthesized blank cell is serialized as the native childless run.
    require(snap(e,True,True)==snap(ac[a],True,True),'split cell format not preserved')
 elif op=='align':
  hb=xml(bm['Contents/header.xml']);ha=xml(am['Contents/header.xml']);bdefs={p.get('id'):p for p in hb.iter(H+'paraPr')};adefs={p.get('id'):p for p in ha.iter(H+'paraPr')}
  for a in targets:
   old,new=bc[a],ac[a];e=copy.deepcopy(old);ep=paragraph(e);bp=paragraph(old);np=paragraph(new);ep.set('paraPrIDRef',np.get('paraPrIDRef'))
   require(snap(e,True)==snap(new,True),'cell content or format changed beyond alignment')
   b=copy.deepcopy(bdefs[bp.get('paraPrIDRef')]);v=copy.deepcopy(adefs[np.get('paraPrIDRef')]);b.attrib.pop('id',None);v.attrib.pop('id',None);b.find(H+'align').set('horizontal',req['alignment']);require(snap(b)==snap(v),'paragraph style changed beyond alignment')
  # Only appended paraPr definitions and item count may change in header.
  bp=hb.find('.//'+H+'paraProperties');ap=ha.find('.//'+H+'paraProperties')
  require(all(i in adefs and snap(p)==snap(adefs[i]) for i,p in bdefs.items()),'existing style changed')
  added=set(adefs)-set(bdefs);used={paragraph(ac[a]).get('paraPrIDRef') for a in targets};require(added<=used,'unrelated added style')
  require(int(ap.get('itemCnt'))==len(adefs),'paraPr inventory mismatch')
  for p in list(ap):
   if p.tag==H+'paraPr' and p.get('id') in added:ap.remove(p)
  ap.set('itemCnt',bp.get('itemCnt'));require(snap(hb)==snap(ha),'non-target header changed')
 for n in bm:
  if n!=part and not(op=='align' and n=='Contents/header.xml'):require(bm[n]==am[n],'non-target package member changed: '+n)
 ids=[p.get('id') for p in ar.iter(P+'p')];require(len(ids)==len(set(ids)),'paragraph ID collision')
 return dict(nonTargetPackageAndXmlPreserved=True,targetContentPreserved=True,geometryExact=True,stylesPreserved=True,paragraphIdsUnique=True)

def apply(source,output,request,dry_run=False):
 source=Path(source).resolve();output=Path(output).absolute();req=dict(request);require(version('python-hwpx')=='6.3.0','unverified core version');require(source.suffix.lower()=='.hwpx' and output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and output.resolve()!=source,'new output required')
 allowed={'schema','source_sha256','table','operation','range','alignment'};require(not(set(req)-allowed) and req.get('schema')==SCHEMA and req.get('source_sha256')==sha(source),'invalid/stale request')
 data=source.read_bytes();_,part,root,t=locate(data,req['table']);cells,grid=geometry(t);r0,c0,r1,c1=bounds(req,t);anchors={(y,x) for y in range(r0,r1+1) for x in range(c0,c1+1)};op=req.get('operation')
 if op=='merge':
  require(r0==r1,'this release supports horizontal cell merges only')
  require(len(anchors)>1 and len(anchors)<=12 and all(a in cells and span(cells[a])==(1,1) for a in anchors),'only 2..12 unmerged cells supported')
  require(all(not text(cells[a]) for a in anchors-{(r0,c0)}),'merge would discard non-anchor content')
  # Empty cells must have the same formatting; different fills/margins are not silently discarded.
  def template(c):
   e=copy.deepcopy(c);e.find(P+'cellAddr').attrib.clear();e.find(P+'cellSz').attrib.clear();paragraph(e).attrib.pop('id',None)
   for n in list(e.iter(P+'run')):
    for ch in list(n):n.remove(ch)
   return snap(e,True)
  require(all(template(cells[a])==template(cells[r0,c0]) for a in anchors),'cell formats differ')
  require(len({size(cells[y,x])[1] for y in range(r0,r1+1) for x in [c0]})==1 and len({size(cells[y,x])[0] for x in range(c0,c1+1) for y in [r0]})==1,'nonuniform rectangle')
 elif op=='unmerge':
  require(r0==r1,'this release supports horizontal merge reversal only')
  require(grid[r0,c0]==(r0,c0) and span(cells[r0,c0])==(r1-r0+1,c1-c0+1) and len(anchors)>1 and len(anchors)<=12,'exact complete merged range required')
  h,w=size(cells[r0,c0]);require(h%(r1-r0+1)==0 and w%(c1-c0+1)==0,'exact equal split required')
 elif op=='align':require(req.get('alignment') in ['LEFT','CENTER','RIGHT'] and all(a in cells and span(cells[a])==(1,1) for a in anchors),'unmerged cells and supported horizontal alignment required')
 else:raise ValueError('unsupported operation')
 with HwpxDocument.open(source) as doc:
  tables=[x for sec in doc.sections for p in sec.paragraphs for x in p.tables];matches=[x for x in tables if x.element.get('id')==t.get('id') and x.paragraph.section.part_name==part];require(len(matches)==1,'public table binding missing/ambiguous');table=matches[0]
  if op=='merge':table.merge_cells(r0,c0,r1,c1)
  elif op=='unmerge':
   template=table.cell(r0,c0).paragraphs[0];base_para=template.para_pr_id_ref;base_style=template.style_id_ref
   base_vertical=cells[r0,c0].find(P+'subList').get('vertAlign')
   require(base_vertical in ['TOP','CENTER','BOTTOM'],'unsupported source vertical alignment')
   table.split_merged_cell(r0,c0)
   for y,x in sorted(anchors-{(r0,c0)}):
    p=table.cell(y,x).paragraphs[0];p.para_pr_id_ref=base_para;p.style_id_ref=base_style
    # The 6.3.0 split API defaults new cells to CENTER. Preserve the source
    # layout on only these new blank cells; the full independent verifier
    # still rejects every other unexpected property or existing-cell change.
    table.cell(y,x).element.find(P+'subList').set('vertAlign',base_vertical)
    # Only new API-created, blank cells: remove the empty t Hancom would remove.
    run=p.runs[0]
    require(len(run.element)==1 and run.element[0].tag==P+'t' and not (run.element[0].text or '') and not len(run.element[0]),'unexpected new blank cell')
    run.element.remove(run.element[0])
   table.mark_dirty()
  else:
   for y,x in sorted(anchors):
    p=table.cell(y,x).paragraphs[0];p.para_pr_id_ref=doc.parts.headers[0].ensure_paragraph_format(base_para_pr_id=p.para_pr_id_ref,alignment=req['alignment'])
   table.mark_dirty()
  result=doc.to_bytes()
 checks=verify(data,result,req)
 with workspace_candidate_directory(prefix='cell-edit-',dir=output.parent) as tmp:
  p=Path(tmp)/'candidate.hwpx';p.write_bytes(result);require(validate_editor_open_safety(p).ok,'open safety failed');require(sha(source)==req['source_sha256'],'source changed during edit')
  if not dry_run:os.link(p,output)
 return dict(schema='hwpx.safe-cell-layout-receipt.v1',status='PASS_STRUCTURE',native='not_checked',published=not dry_run,source_sha256=req['source_sha256'],candidate_sha256=hashlib.sha256(result).hexdigest(),request=req,checks=checks)
if __name__=='__main__':
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True);i=s.add_parser('inspect');i.add_argument('source');i.add_argument('--table',type=int,required=True);i.add_argument('--output',required=True);a=s.add_parser('apply');a.add_argument('source');a.add_argument('output');a.add_argument('--request',required=True);a.add_argument('--dry-run',action='store_true');v=p.parse_args()
 if v.command=='inspect':
  with open(v.output,'x',encoding='utf8') as f:json.dump(inspect(v.source,v.table),f,ensure_ascii=False,indent=2)
 else:print(json.dumps(apply(v.source,v.output,json.loads(Path(v.request).read_text(encoding='utf-8-sig')),v.dry_run),ensure_ascii=False,indent=2))




