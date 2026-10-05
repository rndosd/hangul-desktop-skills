"""Bounded 1-3 top header rows. Existing merge geometry/content are immutable."""
from pathlib import Path
import argparse,copy,hashlib,json,math,os,tempfile
from importlib.metadata import version
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
from safe_cell_layout import P,H,require,sha,xml,locate
from safe_cell_spacing import shape,snapshot,effective
SCHEMA='hwpx.safe-table-header.v1'
KEYS={'schema','source_sha256','table','header_rows','repeat_header','alignment','vertical_align','margins_mm','row_heights_mm'}
def number(v,lo,hi):return type(v) in [int,float] and math.isfinite(v) and lo<=v<=hi

def plan(data,req):
 require(isinstance(req,dict) and {'schema','source_sha256','table','header_rows'}<=set(req) and set(req)<=KEYS,'invalid request keys')
 require(req['schema']==SCHEMA and req['source_sha256']==hashlib.sha256(data).hexdigest(),'invalid schema/stale hash')
 require(type(req['table']) is int and req['table']>=1,'integer table required')
 hs=req['header_rows'];require(isinstance(hs,list) and 1<=len(hs)<=3 and all(type(x) is int for x in hs) and hs==list(range(1,len(hs)+1)),'contiguous top 1..3 header rows required')
 require(len(req)>4,'explicit changes required');m,part,r,t=locate(data,req['table']);cs,grid=shape(t);n=len(hs)
 require(n<int(t.get('rowCnt')),'body rows required')
 require(t.get('lock','0')=='0' and t.get('noAdjust','0')=='0' and t.find(P+'sz') is not None and t.find(P+'sz').get('protect','0')=='0','protected/fixed table unsupported')
 pos=t.find(P+'pos');require(pos is not None and pos.get('treatAsChar')=='0' and t.get('pageBreak')=='TABLE','normal floating whole-row table required')
 require(t.get('textWrap')=='TOP_AND_BOTTOM' and pos.get('vertRelTo')=='PARA' and pos.get('horzRelTo')=='COLUMN' and pos.get('flowWithText')=='1' and pos.get('allowOverlap')=='0','normal paragraph-relative flow required')
 host=t.getparent().getparent();require(host.tag==P+'p' and host.getparent() is r and len(list(host.iter(P+'tbl')))==1,'single direct-body table required')
 require(t.get('repeatHeader') in ['0','1'],'unknown repeat setting');targets={}
 for a,c in cs.items():
  span=c.find(P+'cellSpan');sy=int(span.get('rowSpan'));sx=int(span.get('colSpan'))
  require(c.get('header') in ['0','1'],'unknown cell header marker')
  if a[0]>=n:
   require(sy==sx==1,'merged body is outside verified scope');require(c.get('header')=='0','declared header prefix excludes an existing header cell');continue
  require(a[0]+sy<=n,'header merge crosses into body');require(c.get('protect','0')=='0','protected header cell')
  targets[a]={}
 if 'repeat_header' in req:require(type(req['repeat_header']) is bool,'repeat boolean required')
 if 'alignment' in req:require(req['alignment'] in ['LEFT','CENTER','RIGHT'],'invalid alignment')
 if 'vertical_align' in req:require(req['vertical_align'] in ['TOP','CENTER','BOTTOM'],'invalid vertical alignment')
 if 'margins_mm' in req:
  v=req['margins_mm'];require(isinstance(v,dict) and v and set(v)<={'left','right','top','bottom'} and all(number(x,0,10) for x in v.values()),'explicit finite 0..10mm margins required')
 if 'row_heights_mm' in req:
  v=req['row_heights_mm'];require(isinstance(v,list) and len(v)==n and all(number(x,5,30) for x in v),'one finite 5..30mm height per header row required')
 for a,spec in targets.items():
  c=cs[a];margins=effective(c,t)
  if 'margins_mm' in req:
   for k,v in req['margins_mm'].items():margins[k]=round(v*7200/25.4)
   spec['margins']=margins
  require(int(c.find(P+'cellSz').get('width'))-margins['left']-margins['right']>=round(5*7200/25.4),'header usable width below 5mm')
  if 'row_heights_mm' in req:
   sy=int(c.find(P+'cellSpan').get('rowSpan'));spec['height']=sum(round(v*7200/25.4) for v in req['row_heights_mm'][a[0]:a[0]+sy]);require(spec['height']-margins['top']-margins['bottom']>=round(3*7200/25.4),'header usable height below 3mm')
 return m,part,r,t,cs,grid,targets

def modify(c,spec,req):
 if 'repeat_header' in req:c.set('header',str(int(req['repeat_header'])))
 if 'vertical_align' in req:c.find(P+'subList').set('vertAlign',req['vertical_align'])
 if 'margins' in spec:
  c.set('hasMargin','1')
  for k,v in spec['margins'].items():c.find(P+'cellMargin').set(k,str(v))
 if 'height' in spec:c.find(P+'cellSz').set('height',str(spec['height']))

def verify(before,after,req):
 bm,part,br,bt,bc,bg,edits=plan(before,req);am,ap,ar,at=locate(after,req['table']);ac,ag=shape(at)
 require(set(bm)==set(am) and ap==part and set(bc)==set(ac) and bg==ag,'package/grid changed')
 expected=copy.deepcopy(br);et=list(expected.iter(P+'tbl'))[list(br.iter(P+'tbl')).index(bt)];ec,_=shape(et)
 if 'repeat_header' in req:et.set('repeatHeader',str(int(req['repeat_header'])))
 hb=xml(bm['Contents/header.xml']);ha=xml(am['Contents/header.xml']);bd={n.get('id'):n for n in hb.iter(H+'paraPr')};ad={n.get('id'):n for n in ha.iter(H+'paraPr')};used=set()
 require(all(k in ad and snapshot(v)==snapshot(ad[k]) for k,v in bd.items()),'old shared paragraph definition changed')
 for a,spec in edits.items():
  modify(ec[a],spec,req)
  if 'alignment' in req:
   eps=ec[a].find(P+'subList').findall(P+'p');aps=ac[a].find(P+'subList').findall(P+'p');require(len(eps)==len(aps),'header paragraph count changed')
   for ep,apara in zip(eps,aps):
    old=ep.get('paraPrIDRef');new=apara.get('paraPrIDRef');require(old in bd and new in ad,'unbound paragraph style');want=copy.deepcopy(bd[old]);got=copy.deepcopy(ad[new]);want.attrib.pop('id');got.attrib.pop('id');align=want.find(H+'align');require(align is not None,'paragraph alignment missing');align.set('horizontal',req['alignment']);require(snapshot(want)==snapshot(got),'header style changed beyond horizontal alignment');ep.set('paraPrIDRef',new);used.add(new)
 # Only line-layout caches may be invalidated in selected header paragraphs.
 actual=copy.deepcopy(ar);actual_table=list(actual.iter(P+'tbl'))[list(ar.iter(P+'tbl')).index(at)];actual_cells,_=shape(actual_table)
 for a in edits:
  for cell in [ec[a],actual_cells[a]]:
   for paragraph in cell.find(P+'subList').findall(P+'p'):
    for cache in list(paragraph.findall(P+'linesegarray')):paragraph.remove(cache)
 require(snapshot(expected)==snapshot(actual),'section changed beyond exact header request')
 # Body caches and all other section caches must remain exact during candidate editing.
 for a,c in bc.items():
  if a not in edits:require(snapshot(c)==snapshot(ac[a]),'body cell changed')
 added=set(ad)-set(bd);require(added<=used,'unrelated paragraph style added');ba=hb.find('.//'+H+'paraProperties');aa=ha.find('.//'+H+'paraProperties');require(int(aa.get('itemCnt'))==len(ad),'style count mismatch')
 for n in list(aa):
  if n.get('id') in added:aa.remove(n)
 aa.set('itemCnt',ba.get('itemCnt'));require(snapshot(hb)==snapshot(ha),'header changed beyond exact cloned paragraph styles')
 for name in bm:
  if name not in {part,'Contents/header.xml'}:require(bm[name]==am[name],'non-target package changed '+name)
 return dict(mergeGridAndWidthsPreserved=True,bodyCellsExact=True,allTextRunsBreakTailsAndControlsPreserved=True,borderFillsAndOldStylesUnchanged=True,exactRequestedHeaderProperties=True,nonTargetPayloadPreserved=True)

def inspect(source,table):
 data=Path(source).read_bytes();_,part,_,t=locate(data,table);cs,g=shape(t)
 return dict(schema=SCHEMA,source_sha256=sha(source),table=table,part=part,page_break=t.get('pageBreak'),repeat_header=t.get('repeatHeader'),cells=[dict(row=a[0]+1,column=a[1]+1,span=dict(c.find(P+'cellSpan').attrib),header=c.get('header'),size=dict(c.find(P+'cellSz').attrib),texts=[''.join(n.itertext()) for n in c.iter(P+'t')]) for a,c in cs.items()])

def apply(source,output,req,dry_run=False):
 source=Path(source).resolve();output=Path(output).absolute();require(version('python-hwpx')=='6.3.0','unverified core version');require(source.suffix.lower()=='.hwpx' and output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and source!=output.resolve(),'new hwpx output required');before=source.read_bytes();_,part,_,t,_,_,edits=plan(before,req)
 with HwpxDocument.open(source) as doc:
  found=[x for s in doc.sections for p in s.paragraphs for x in p.tables if x.element.get('id')==t.get('id') and x.paragraph.section.part_name==part];require(len(found)==1,'ambiguous public table binding');table=found[0]
  if 'repeat_header' in req:table.element.set('repeatHeader',str(int(req['repeat_header'])))
  for a,spec in edits.items():
   cell=table.cell(*a);require(cell.address==a,'covered cell binding refused');modify(cell.element,{k:v for k,v in spec.items() if k!='height'},req)
   if 'height' in spec:cell.set_size(height=spec['height'])
   for p in cell.paragraphs:
    if 'alignment' in req:p.para_pr_id_ref=doc.parts.headers[0].ensure_paragraph_format(base_para_pr_id=p.para_pr_id_ref,alignment=req['alignment'])
    for cache in list(p.element.findall(P+'linesegarray')):p.element.remove(cache)
  table.mark_dirty();after=doc.to_bytes()
 checks=verify(before,after,req)
 with tempfile.TemporaryDirectory(prefix='table-header-',dir=output.parent) as tmp:
  p=Path(tmp)/'candidate.hwpx';p.write_bytes(after);require(validate_editor_open_safety(p).ok,'open safety failed');require(sha(source)==req['source_sha256'],'source changed during edit')
  if not dry_run:os.link(p,output)
 return dict(schema='hwpx.safe-table-header-receipt.v1',status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',native='pending',source_sha256=req['source_sha256'],candidate_sha256=hashlib.sha256(after).hexdigest(),published=not dry_run,request=req,checks=checks)
if __name__=='__main__':
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True);i=sub.add_parser('inspect');i.add_argument('source');i.add_argument('--table',type=int,required=True);i.add_argument('--output',required=True);a=sub.add_parser('apply');a.add_argument('source');a.add_argument('output');a.add_argument('--request',required=True);a.add_argument('--dry-run',action='store_true');v=p.parse_args()
 if v.command=='inspect':
  with open(v.output,'x',encoding='utf8') as file:json.dump(inspect(v.source,v.table),file,ensure_ascii=False,indent=2)
 else:print(json.dumps(apply(v.source,v.output,json.loads(Path(v.request).read_text(encoding='utf-8-sig')),v.dry_run),ensure_ascii=False,indent=2))

