"""Bounded existing plain-table page flow and adjacent caption binding, core 6.3.0."""
from pathlib import Path
import argparse,json,copy,hashlib,math,tempfile,os
from importlib.metadata import version
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
from safe_cell_layout import P,H,require,sha,parts,xml,locate
from safe_cell_spacing import shape,snapshot
SCHEMA='hwpx.safe-table-flow.v1'

def plan(data,req):
 require(isinstance(req,dict) and {'schema','source_sha256','table'}<=set(req) and set(req)<={'schema','source_sha256','table','page_break','repeat_header','header_rows','outer_spacing_pt','caption','anchor_same_page'},'invalid request keys')
 require(req['schema']==SCHEMA and req['source_sha256']==hashlib.sha256(data).hexdigest(),'invalid schema/stale hash');require(len(req)>3,'explicit changes required')
 m,part,section,t=locate(data,req['table']);cs,grid=shape(t);require(all(all(c.find(P+'cellSpan').get(k)=='1' for k in ['rowSpan','colSpan']) for c in cs.values()),'merged table flow needs separate validation')
 require(t.get('lock','0')=='0' and t.get('noAdjust','0')=='0' and t.find(P+'sz') is not None and t.find(P+'sz').get('protect','0')=='0','fixed/protected table unsupported')
 require(t.find(P+'pos') is not None and t.find(P+'pos').get('treatAsChar')=='0','inline table unsupported; do not silently change its anchoring')
 require(t.get('pageBreak') in ['CELL','TABLE'] and t.get('repeatHeader') in ['0','1'],'unsupported existing table flow');require(len(t.findall(P+'outMargin'))==1,'one outside margin required')
 host=t.getparent().getparent();require(host.tag==P+'p' and host.getparent() is section,'direct body table required');require(len(list(host.iter(P+'tbl')))==1,'one table per host required')
 if 'page_break' in req:require(req['page_break'] in ['CELL','TABLE'],'only CELL/TABLE supported')
 if 'anchor_same_page' in req:
  require(req['anchor_same_page'] is True,'only explicit anchor binding true supported');pos=t.find(P+'pos');require(t.get('textWrap')=='TOP_AND_BOTTOM' and pos.get('vertRelTo')=='PARA' and pos.get('horzRelTo')=='COLUMN' and pos.get('flowWithText')=='1' and pos.get('allowOverlap')=='0','normal paragraph-relative flow required for anchor binding')
 if 'repeat_header' in req:require(type(req['repeat_header']) is bool,'repeat boolean required')
 if req.get('repeat_header') is True:require(req.get('header_rows')==[1] and type(req['header_rows'][0]) is int,'explicit first header row required')
 elif 'header_rows' in req:require(False,'header_rows only with explicit repeat true')
 if 'header_rows' in req:require(all(c.get('protect','0')=='0' for a,c in cs.items() if a[0]==0),'protected header cell')
 if 'outer_spacing_pt' in req:
  v=req['outer_spacing_pt'];require(isinstance(v,dict) and v and set(v)<={'before','after'},'explicit outer margin sides required')
  for number in v.values():require(type(number) in [int,float] and math.isfinite(number) and 0<=number<=36,'finite 0..36pt spacing required')
 cap=None
 if 'caption' in req:
  v=req['caption'];require(isinstance(v,dict) and {'expected_text','keep_with_next'}<=set(v) and set(v)<={'expected_text','keep_with_next','page_break_before'} and type(v['keep_with_next']) is bool and isinstance(v['expected_text'],str) and 1<=len(v['expected_text'])<=200,'caption text and boolean required')
  if 'page_break_before' in v:require(type(v['page_break_before']) is bool,'caption page-break boolean required')
  cap=host.getprevious();require(cap is not None and cap.tag==P+'p' and all(n.tag in [P+'run',P+'linesegarray'] for n in cap),'adjacent plain caption required')
  runs=cap.findall(P+'run');require(1<=len(runs)<=20 and all(len(run)<=1 and all(n.tag==P+'t' and not len(n) for n in run) for run in runs),'plain caption runs required')
  require(''.join(n.text or '' for n in cap.iter(P+'t'))==v['expected_text'],'adjacent caption text mismatch')
  h=xml(m['Contents/header.xml']);defs=[n for n in h.iter(H+'paraPr') if n.get('id')==cap.get('paraPrIDRef')];require(len(defs)==1 and len(defs[0].findall(H+'breakSetting'))==1,'caption style binding unsupported')
 return m,part,section,t,cs,host,cap

def modify_table(t,req):
 if 'anchor_same_page' in req:t.find(P+'pos').set('holdAnchorAndSO','1')
 if 'page_break' in req:t.set('pageBreak',req['page_break'])
 if 'repeat_header' in req:t.set('repeatHeader',str(int(req['repeat_header'])))
 if 'header_rows' in req:
  for c in t.findall(P+'tr')[0].findall(P+'tc'):c.set('header','1')
 for key,value in req.get('outer_spacing_pt',{}).items():t.find(P+'outMargin').set('top' if key=='before' else 'bottom',str(round(value*100)))

def verify(before,after,req):
 bm,part,br,bt,bc,host,cap=plan(before,req);am,ap,ar,at=locate(after,req['table']);require(set(bm)==set(am) and ap==part,'package inventory changed');expected=copy.deepcopy(br);et=list(expected.iter(P+'tbl'))[list(br.iter(P+'tbl')).index(bt)];modify_table(et,req)
 if cap is not None:
  ec=et.getparent().getparent().getprevious();ac=at.getparent().getparent().getprevious();require(ac is not None,'caption missing');ec.set('paraPrIDRef',ac.get('paraPrIDRef'))
  hb=xml(bm['Contents/header.xml']);ha=xml(am['Contents/header.xml']);bd={n.get('id'):n for n in hb.iter(H+'paraPr')};ad={n.get('id'):n for n in ha.iter(H+'paraPr')};require(all(k in ad and snapshot(n)==snapshot(ad[k]) for k,n in bd.items()),'old paragraph definition changed')
  want=copy.deepcopy(bd[cap.get('paraPrIDRef')]);got=copy.deepcopy(ad[ac.get('paraPrIDRef')]);want.attrib.pop('id');got.attrib.pop('id');want.find(H+'breakSetting').set('keepWithNext',str(int(req['caption']['keep_with_next'])));
  if 'page_break_before' in req['caption']:want.find(H+'breakSetting').set('pageBreakBefore',str(int(req['caption']['page_break_before'])))
  require(snapshot(want)==snapshot(got),'caption style changed beyond keep flag')
  added=set(ad)-set(bd);require(added<={ac.get('paraPrIDRef')},'unrelated added paragraph definitions');ba=hb.find('.//'+H+'paraProperties');aa=ha.find('.//'+H+'paraProperties');require(int(aa.get('itemCnt'))==len(ad),'paragraph count mismatch')
  for n in list(aa):
   if n.get('id') in added:aa.remove(n)
  aa.set('itemCnt',ba.get('itemCnt'));require(snapshot(hb)==snapshot(ha),'non-target header changed')
 else:require(bm['Contents/header.xml']==am['Contents/header.xml'],'header changed without caption edit')
 require(snapshot(expected)==snapshot(ar),'section changed beyond exact table/caption request')
 for name in bm:
  if name not in {part,'Contents/header.xml'}:require(bm[name]==am[name],'non-target payload changed '+name)
 return dict(exactRequestedProperties=True,oldSharedStylesUnchanged=True,allTextRunsNativeBreakTailsAndControlsPreserved=True,cellGeometryAndFormattingPreserved=True,nonTargetPackagePreserved=True)

def inspect(source,table):
 data=Path(source).read_bytes();m,part,r,t=locate(data,table);cs,g=shape(t);host=t.getparent().getparent();cap=host.getprevious()
 return dict(schema=SCHEMA,source_sha256=sha(source),table=table,page_break=t.get('pageBreak'),repeat_header=t.get('repeatHeader'),inline=t.find(P+'pos').get('treatAsChar'),anchor_same_page=t.find(P+'pos').get('holdAnchorAndSO'),outside_spacing_hwpunit=dict(t.find(P+'outMargin').attrib),header_cells=[list(a) for a,c in cs.items() if c.get('header')=='1'],adjacent_preceding_text=''.join(n.text or '' for n in cap.iter(P+'t')) if cap is not None else None,cells=len(cs))

def apply(source,output,req,dry_run=False):
 source=Path(source).resolve();output=Path(output).absolute();require(version('python-hwpx')=='6.3.0','unverified core version');require(source.suffix.lower()=='.hwpx' and output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and source!=output.resolve(),'new hwpx output required');before=source.read_bytes();m,part,r,t,cs,host,cap=plan(before,req)
 with HwpxDocument.open(source) as doc:
  ts=[x for s in doc.sections for p in s.paragraphs for x in p.tables];found=[x for x in ts if x.element.get('id')==t.get('id') and x.paragraph.section.part_name==part];require(len(found)==1,'ambiguous public table binding');table=found[0]
  # Dedicated bounded attribute adapter, not an XML fallback. All cells/content
  # remain untouched except explicitly enabling first-row header markers.
  modify_table(table.element,req);table.mark_dirty()
  if cap is not None:
   matches=[p for p in table.paragraph.section.paragraphs if p.element.get('id')==cap.get('id')];require(len(matches)==1,'ambiguous public caption binding');p=matches[0];p.para_pr_id_ref=doc.parts.headers[0].ensure_paragraph_format(base_para_pr_id=p.para_pr_id_ref,break_setting={k:req['caption'][k] for k in ['keep_with_next','page_break_before'] if k in req['caption']})
  after=doc.to_bytes()
 checks=verify(before,after,req)
 with tempfile.TemporaryDirectory(prefix='table-flow-',dir=output.parent) as tmp:
  p=Path(tmp)/'candidate.hwpx';p.write_bytes(after);require(validate_editor_open_safety(p).ok,'open safety failed');require(sha(source)==req['source_sha256'],'source changed during edit')
  if not dry_run:os.link(p,output)
 return dict(schema='hwpx.safe-table-flow-receipt.v1',status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',native='pending',source_sha256=req['source_sha256'],candidate_sha256=hashlib.sha256(after).hexdigest(),published=not dry_run,request=req,checks=checks)

if __name__=='__main__':
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True);i=sub.add_parser('inspect');i.add_argument('source');i.add_argument('--table',type=int,required=True);i.add_argument('--output',required=True);a=sub.add_parser('apply');a.add_argument('source');a.add_argument('output');a.add_argument('--request',required=True);a.add_argument('--dry-run',action='store_true');v=p.parse_args()
 if v.command=='inspect':
  with open(v.output,'x',encoding='utf8') as file:json.dump(inspect(v.source,v.table),file,ensure_ascii=False,indent=2)
 else:print(json.dumps(apply(v.source,v.output,json.loads(Path(v.request).read_text(encoding='utf-8-sig')),v.dry_run),ensure_ascii=False,indent=2))
