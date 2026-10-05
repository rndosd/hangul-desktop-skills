"""Explicit existing-cell emphasis, alignment and value-preserving numeric display."""
from pathlib import Path
import argparse,copy,json,hashlib,os,tempfile,re
from decimal import Decimal,localcontext
from importlib.metadata import version
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
from safe_cell_layout import P,H,require,sha,xml,locate
from safe_cell_spacing import shape,snapshot
from namespace_literal_guard import preserve_namespace_literals
SCHEMA='hwpx.summary-cell-format.v1'
EDIT_KEYS={'row','column','expected_texts','bold','alignment','keep_with_next','number_format'}

def texts(cell):return [''.join(n.itertext()) for n in cell.find(P+'subList').findall(P+'p')]

def normalized(n):
 n=copy.deepcopy(n);n.attrib.pop('id',None);return snapshot(n)

def bold_only(n,value):
 # Hancom's published CharShapeType model and native saved documents place
 # bold after italic/offset and before underline. Appending after shadow
 # creates a duplicate style which the engine canonicalizes during SaveAs.
 bold=list(n.findall(H+'bold'));require(len(bold)<=1,'duplicate bold child')
 if not value:
  for child in bold:n.remove(child)
  return
 if bold:return
 order=['fontRef','ratio','spacing','relSz','offset','italic','bold','underline','strikeout','outline','shadow','emboss','engrave','supscript','subscript']
 tags=[child.tag for child in n];known=[H+tag for tag in order]
 require(all(tag in known for tag in tags),'unsupported character style child order')
 ranks=[known.index(tag) for tag in tags]
 require(ranks==sorted(ranks) and len(tags)==len(set(tags)),'noncanonical character style child order')
 index=next((i for i,rank in enumerate(ranks) if rank>order.index('bold')),len(tags))
 n.insert(index,n.makeelement(H+'bold',{}))

def formatted_number(text,spec):
 require(isinstance(spec,dict) and set(spec)=={'decimal_places','grouping'},'explicit decimals/grouping required')
 d=spec['decimal_places'];g=spec['grouping'];require(type(d) is int and 0<=d<=4 and type(g) is bool,'invalid numeric display options')
 require(isinstance(text,str) and len(text)<=32 and re.fullmatch(r'[+-]?(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\.[0-9]+)?',text),'plain numeric value required; no units, fields, percent conversion or guessed separators')
 with localcontext() as ctx:
  ctx.prec=50;v=Decimal(text.replace(',',''));q=v.quantize(Decimal(1).scaleb(-d));require(q==v,'rounding/value changes are not supported')
  return format(q,(',' if g else '')+f'.{d}f')

def plan(data,req):
 require(isinstance(req,dict) and set(req)=={'schema','source_sha256','table','edits'},'invalid request keys')
 require(req['schema']==SCHEMA and req['source_sha256']==hashlib.sha256(data).hexdigest(),'invalid schema/stale hash')
 require(type(req['table']) is int and req['table']>=1,'integer table required')
 m,part,root,t=locate(data,req['table']);cs,grid=shape(t)
 require(t.get('lock','0')=='0' and t.get('noAdjust','0')=='0' and t.find(P+'sz').get('protect','0')=='0','protected/fixed table unsupported')
 host=t.getparent().getparent();require(host.tag==P+'p' and host.getparent() is root and len(list(host.iter(P+'tbl')))==1,'single direct-body table required')
 require(isinstance(req['edits'],list) and 1<=len(req['edits'])<=100,'1..100 explicit cell edits required');out={}
 for e in req['edits']:
  require(isinstance(e,dict) and {'row','column','expected_texts'}<=set(e) and set(e)<=EDIT_KEYS and len(e)>3,'invalid cell edit keys')
  require(type(e['row']) is int and type(e['column']) is int,'integer 1-based address required');a=(e['row']-1,e['column']-1)
  require(a in cs and a not in out,'missing/covered/duplicate cell');c=cs[a];require(c.get('protect','0')=='0','protected cell')
  v=e['expected_texts'];require(isinstance(v,list) and all(isinstance(s,str) for s in v) and v==texts(c),'exact complete paragraph texts required')
  if 'bold' in e:require(type(e['bold']) is bool,'bold boolean required')
  if 'alignment' in e:require(e['alignment'] in ['LEFT','CENTER','RIGHT'],'invalid alignment')
  if 'keep_with_next' in e:require(type(e['keep_with_next']) is bool,'keep boolean required')
  if 'number_format' in e:
   require(len(v)==1 and len(c.find(P+'subList')[0].findall(P+'run'))==1,'numeric display requires one plain run/paragraph')
   run=c.find(P+'subList')[0].find(P+'run');require(len(run)==1 and run[0].tag==P+'t' and not len(run[0]),'numeric fields/breaks/rich runs unsupported')
   formatted_number(v[0],e['number_format'])
  out[a]=e
 return m,part,root,t,cs,grid,out

def verify(before,after,req):
 bm,part,br,bt,bc,bg,edits=plan(before,req);am,ap,ar,at=locate(after,req['table']);ac,ag=shape(at)
 require(set(bm)==set(am) and ap==part and bg==ag and set(bc)==set(ac),'package/grid changed')
 eh=xml(bm['Contents/header.xml']);ah=xml(am['Contents/header.xml']);expected=copy.deepcopy(br);et=list(expected.iter(P+'tbl'))[list(br.iter(P+'tbl')).index(bt)];ec,_=shape(et)
 bd={tag:{n.get('id'):n for n in eh.iter(H+tag)} for tag in ['paraPr','charPr']};ad={tag:{n.get('id'):n for n in ah.iter(H+tag)} for tag in bd};used={tag:set() for tag in bd};new={tag:{} for tag in bd}
 for tag in bd:
  require(all(k in ad[tag] and snapshot(n)==snapshot(ad[tag][k]) for k,n in bd[tag].items()),'old shared style changed')
 for a,e in edits.items():
  eps=ec[a].find(P+'subList').findall(P+'p');aps=ac[a].find(P+'subList').findall(P+'p');require(len(eps)==len(aps),'paragraph count changed')
  for ep,pp in zip(eps,aps):
   if any(k in e for k in ['alignment','keep_with_next']):
    old=ep.get('paraPrIDRef');nid=pp.get('paraPrIDRef');require(old in bd['paraPr'] and nid in ad['paraPr'],'unbound paragraph style');want=copy.deepcopy(bd['paraPr'][old])
    if 'alignment' in e:want.find(H+'align').set('horizontal',e['alignment'])
    if 'keep_with_next' in e:want.find(H+'breakSetting').set('keepWithNext',str(int(e['keep_with_next'])))
    require(normalized(want)==normalized(ad['paraPr'][nid]),'paragraph style changed beyond explicit request');ep.set('paraPrIDRef',nid);used['paraPr'].add(nid);new['paraPr'][nid]=ad['paraPr'][nid]
   ers=ep.findall(P+'run');ars=pp.findall(P+'run');require(len(ers)==len(ars),'run count changed')
   for er,rr in zip(ers,ars):
    if 'bold' in e:
     old=er.get('charPrIDRef');nid=rr.get('charPrIDRef');require(old in bd['charPr'] and nid in ad['charPr'],'unbound character style');want=copy.deepcopy(bd['charPr'][old]);bold_only(want,e['bold']);require(normalized(want)==normalized(ad['charPr'][nid]),'character style changed beyond bold');er.set('charPrIDRef',nid);used['charPr'].add(nid);new['charPr'][nid]=ad['charPr'][nid]
   if 'number_format' in e:ep.find(P+'run').find(P+'t').text=formatted_number(e['expected_texts'][0],e['number_format'])
   for p in [ep,pp]:
    # Actual root is a read-only parsed candidate; remove only selected caches.
    for cache in list(p.findall(P+'linesegarray')):p.remove(cache)
 require(snapshot(expected)==snapshot(ar),'section/text/non-target content changed')
 for tag in bd:
  added=set(ad[tag])-set(bd[tag]);require(added<=used[tag],'unrelated style added');container=eh.find('.//'+H+('paraProperties' if tag=='paraPr' else 'charProperties'));actual=ah.find('.//'+H+('paraProperties' if tag=='paraPr' else 'charProperties'));require(int(actual.get('itemCnt'))==len(ad[tag]),'style count mismatch')
  for n in actual:
   if n.get('id') in added:container.append(copy.deepcopy(n))
  container.set('itemCnt',str(len(bd[tag])+len(added)))
 require(snapshot(eh)==snapshot(ah),'header changed beyond allowed style clones')
 for name in bm:
  if name not in {part,'Contents/header.xml'}:require(bm[name]==am[name],'non-target payload changed '+name)
 return dict(exactRequestedStylesAndNumericDisplay=True,numericValuesPreserved=True,oldStylesAndUnselectedCellsPreserved=True,allGeometryBordersUnitsAndControlsPreserved=True)

@preserve_namespace_literals
def apply(source,output,req,dry_run=False):
 source=Path(source).resolve();output=Path(output).absolute();require(version('python-hwpx')=='6.3.0','unverified core version');require(source.suffix.lower()==output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and not output.is_symlink() and output.resolve()!=source,'new hwpx output required');require(validate_editor_open_safety(source).ok,'source open safety failed');before=source.read_bytes();_,part,_,t,_,_,edits=plan(before,req)
 with HwpxDocument.open(source) as doc:
  found=[x for s in doc.sections for p in s.paragraphs for x in p.tables if x.element.get('id')==t.get('id') and x.paragraph.section.part_name==part];require(len(found)==1,'ambiguous public table binding');table=found[0];header=doc.parts.headers[0]
  for a,e in edits.items():
   cell=table.cell(*a);require(cell.address==a,'covered cell binding refused')
   for p in cell.paragraphs:
    if any(k in e for k in ['alignment','keep_with_next']):p.para_pr_id_ref=header.ensure_paragraph_format(base_para_pr_id=p.para_pr_id_ref,alignment=e.get('alignment'),break_setting={'keep_with_next':e['keep_with_next']} if 'keep_with_next' in e else None)
    for run in p.runs:
     if 'bold' in e:
      old=header.element.find('.//'+H+'charPr[@id="'+str(run.char_pr_id_ref)+'"]');require(old is not None,'missing source char style');want=copy.deepcopy(old);bold_only(want,e['bold']);new=header.ensure_char_property(base_char_pr_id=run.char_pr_id_ref,predicate=lambda n,w=want:normalized(n)==normalized(w),modifier=lambda n,v=e['bold']:bold_only(n,v));run.char_pr_id_ref=new.get('id')
    if 'number_format' in e:
     run=p.runs[0];old=e['expected_texts'][0];new=formatted_number(old,e['number_format'])
     if new!=old:require(run.replace_text(old,new,count=1)==1,'numeric exact replacement failed')
    for cache in list(p.element.findall(P+'linesegarray')):p.element.remove(cache)
  table.mark_dirty();after=doc.to_bytes()
 checks=verify(before,after,req)
 with tempfile.TemporaryDirectory(prefix='summary-style-',dir=output.parent) as tmp:
  path=Path(tmp)/'candidate.hwpx';path.write_bytes(after);require(validate_editor_open_safety(path).ok,'candidate open safety failed');require(sha(source)==req['source_sha256'],'source changed during edit')
  if not dry_run:os.link(path,output)
 return dict(schema='hwpx.summary-cell-format-receipt.v1',status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',native='pending',source_sha256=req['source_sha256'],candidate_sha256=hashlib.sha256(after).hexdigest(),published=not dry_run,request=req,checks=checks)

def inspect(source,table):
 _,part,_,t=locate(Path(source).read_bytes(),table);cs,_=shape(t)
 return dict(schema=SCHEMA,source_sha256=sha(source),table=table,part=part,cells=[dict(row=a[0]+1,column=a[1]+1,expected_texts=texts(c),span=dict(c.find(P+'cellSpan').attrib)) for a,c in cs.items()])
if __name__=='__main__':
 parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True);p=sub.add_parser('inspect');p.add_argument('source');p.add_argument('--table',type=int,required=True);p.add_argument('--output',required=True);p=sub.add_parser('apply');p.add_argument('source');p.add_argument('output');p.add_argument('--request',required=True);p.add_argument('--dry-run',action='store_true');a=parser.parse_args()
 if a.command=='inspect':
  with open(a.output,'x',encoding='utf8') as f:json.dump(inspect(a.source,a.table),f,ensure_ascii=False,indent=2)
 else:print(json.dumps(apply(a.source,a.output,json.loads(Path(a.request).read_text(encoding='utf-8-sig')),a.dry_run),ensure_ascii=False,indent=2))
