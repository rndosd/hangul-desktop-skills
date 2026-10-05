"""Replace an explicitly editable, blank, unmerged repeat area; preserve its template."""
from pathlib import Path
import argparse,copy,json,hashlib,os,tempfile
from importlib.metadata import version
from hwpx import HwpxDocument
from hwpx.table_patch import apply_table_ops
from hwpx.tools.package_validator import validate_editor_open_safety
from safe_cell_layout import P,require,sha,locate
from safe_cell_spacing import shape,snapshot
from safe_edit import single_line
from namespace_literal_guard import preserve_namespace_literals
SCHEMA='hwpx.blank-repeat-rows.v1'

def text(c):return ''.join(c.find(P+'subList')[0].itertext())

def checked(data,req):
 require(isinstance(req,dict) and set(req)=={'schema','source_sha256','table','editable_reason','expected_headers','template_row','values'},'invalid repeat request keys')
 require(req['schema']==SCHEMA and req['source_sha256']==hashlib.sha256(data).hexdigest(),'invalid schema/stale source')
 require(type(req['table']) is int and req['table']>=1,'integer table required');single_line(req['editable_reason'],search=True)
 m,part,root,t=locate(data,req['table']);cs,grid=shape(t);rows=t.findall(P+'tr');cols=int(t.get('colCnt'))
 require(t.get('lock','0')=='0' and t.get('noAdjust','0')=='0' and t.find(P+'sz') is not None and t.find(P+'sz').get('protect','0')=='0','locked/fixed table unsupported')
 pos=t.find(P+'pos');require(pos is not None and pos.get('treatAsChar')=='0' and t.get('pageBreak')=='TABLE','floating whole-row table required')
 require(t.get('textWrap')=='TOP_AND_BOTTOM' and pos.get('flowWithText')=='1' and pos.get('allowOverlap')=='0','normal flow required')
 host=t.getparent().getparent();require(host.tag==P+'p' and host.getparent() is root and len(list(host.iter(P+'tbl')))==1,'single direct-body table required')
 for a,c in cs.items():
  span=c.find(P+'cellSpan');require(span.get('rowSpan')==span.get('colSpan')=='1','merged repeat area unsupported');require(c.get('protect','0')=='0','protected repeat cell')
  ps=c.find(P+'subList').findall(P+'p');require(len(ps)==1,'one plain paragraph per repeat cell');runs=ps[0].findall(P+'run');require(len(runs)==1 and len(runs[0])<=1 and (not len(runs[0]) or runs[0][0].tag==P+'t' and not len(runs[0][0])),'one plain styled run required')
  require(c.get('header')=='0' or a[0]==0,'only first header row supported')
  if a[0]>0:require(text(c)=='','repeat source must be entirely blank; no populated/whitespace data rows may be removed')
 headers=[text(cs[0,x]) for x in range(cols)];require(isinstance(req['expected_headers'],list) and all(isinstance(x,str) and x for x in req['expected_headers']) and req['expected_headers']==headers,'exact complete headers required')
 require(type(req['template_row']) is int and 2<=req['template_row']<=len(rows),'explicit existing body template row required')
 values=req['values'];require(isinstance(values,list) and 1<=len(values)<=40,'1..40 explicit data rows required')
 for row in values:
  require(isinstance(row,list) and len(row)==cols,'one value per column required')
  for value in row:require(isinstance(value,str) and len(value)<=3000,'bounded string required');single_line(value)
  require(any(row),'each new row needs content')
 return m,part,root,t,cs,rows,cols

def mapping(rows,req):
 result=[(i,False) for i in range(len(rows))];goal=len(req['values'])+1
 if goal<len(result):return result[:goal]
 at=req['template_row']-1
 while len(result)<goal:result.insert(at+1,(result[at][0],True));at+=1
 return result

def expected_cell(c,row,new,value):
 e=copy.deepcopy(c);e.find(P+'cellAddr').set('rowAddr',str(row));p=e.find(P+'subList')[0]
 if new:p.attrib.pop('id',None)
 run=p.find(P+'run')
 if value:
  node=run.find(P+'t')
  if node is None:node=run.makeelement(P+'t',{});run.append(node)
  node.text=value
 for cache in list(p.findall(P+'linesegarray')):p.remove(cache)
 return e

def verify(before,after,req):
 bm,part,br,bt,bc,rows,cols=checked(before,req);am,ap,ar,at=locate(after,req['table']);ac,grid=shape(at);model=mapping(rows,req);require(set(bm)==set(am) and ap==part and int(at.get('rowCnt'))==len(model) and int(at.get('colCnt'))==cols,'package/shape mismatch')
 def outside(n,t):return ('selected-repeat-table',) if n is t else (n.tag,tuple(sorted(n.attrib.items())),n.text or '',n.tail or '',tuple(outside(c,t) for c in n))
 require(outside(br,bt)==outside(ar,at),'non-target XML changed')
 attrs=dict(bt.attrib);attrs['rowCnt']=str(len(model));require(attrs==dict(at.attrib),'table attrs changed');require([snapshot(n) for n in bt if n.tag!=P+'tr']==[snapshot(n) for n in at if n.tag!=P+'tr'],'table settings changed')
 ars=at.findall(P+'tr');require(len(ac)==len(model)*cols,'cell count mismatch')
 for y,(old,new) in enumerate(model):
  require(dict(rows[old].attrib)==dict(ars[y].attrib),'row attributes changed')
  for x in range(cols):
   if y==0:require(snapshot(bc[0,x])==snapshot(ac[0,x]),'header changed');continue
   actual=copy.deepcopy(ac[y,x]);p=actual.find(P+'subList')[0]
   if new:p.attrib.pop('id',None)
   for cache in list(p.findall(P+'linesegarray')):p.remove(cache)
   require(snapshot(expected_cell(bc[old,x],y,new,req['values'][y-1][x]))==snapshot(actual),'cell text/style/geometry changed beyond exact repeat request '+str((y,x)))
 ids=[n.get('id') for member in am if member.startswith('Contents/section') and member.endswith('.xml') for n in __import__('safe_cell_layout').xml(am[member]).iter(P+'p')];require(None not in ids and len(ids)==len(set(ids)),'paragraph ID collision')
 for name in bm:
  if name!=part:require(bm[name]==am[name],'non-target package payload changed '+name)
 return dict(requestedRowsAndValuesExact=True,onlyBlankSourceRowsRemoved=True,existingHeaderAndStylesPreserved=True,allOtherTablesAndBodyPreserved=True,paragraphIdsUnique=True)

@preserve_namespace_literals
def apply(source,output,req,dry_run=False):
 source=Path(source).resolve();output=Path(output).absolute();require(version('python-hwpx')=='6.3.0','unverified core');require(source.suffix.lower()==output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and not output.is_symlink() and output.resolve()!=source,'new hwpx output required');require(validate_editor_open_safety(source).ok,'source open safety failed');before=source.read_bytes();_,part,root,t,_,rows,_=checked(before,req);data=before;goal=len(req['values'])+1;n=len(rows);at=req['template_row']-1;ops=[];tableIndex=list(root.iter(P+'tbl')).index(t)
 while n!=goal:
  op=dict(section_path=part,table_index=tableIndex)
  if n<goal:op.update(op='insert_row_by_clone',ref_row=at,count=1);at+=1;n+=1
  else:op.update(op='delete_row',row=n-1);n-=1
  result=apply_table_ops(data,[op]);require(result.ok,'public row operation failed');data=result.data;ops.append(op)
 with tempfile.TemporaryDirectory(prefix='repeat-form-',dir=output.parent) as tmp:
  structure=Path(tmp)/'structure.hwpx';structure.write_bytes(data)
  with HwpxDocument.open(structure) as doc:
   found=[x for s in doc.sections for p in s.paragraphs for x in p.tables if x.element.get('id')==t.get('id') and x.paragraph.section.part_name==part];require(len(found)==1,'ambiguous public table binding');table=found[0]
   for y,values in enumerate(req['values'],1):
    for x,value in enumerate(values):
     if value:table.cell(y,x).paragraphs[0].runs[0].text=value
   table.mark_dirty();after=doc.to_bytes()
  checks=verify(before,after,req);path=Path(tmp)/'candidate.hwpx';path.write_bytes(after);require(validate_editor_open_safety(path).ok,'candidate open safety failed');require(sha(source)==req['source_sha256'],'source changed')
  if not dry_run:os.link(path,output)
 return dict(schema='hwpx.blank-repeat-rows-receipt.v1',status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',native='pending',source_sha256=req['source_sha256'],candidate_sha256=hashlib.sha256(after).hexdigest(),published=not dry_run,sourceDataRows=len(rows)-1,resultDataRows=len(req['values']),templateRow=req['template_row'],publicRowOps=ops,checks=checks)

def inspect(source,table):
 _,part,_,t=locate(Path(source).read_bytes(),table);cs,_=shape(t)
 return dict(schema=SCHEMA,source_sha256=sha(source),table=table,part=part,rows=[[text(cs[y,x]) for x in range(int(t.get('colCnt')))] for y in range(int(t.get('rowCnt')))],emptyStyledRuns=sum(not len(c.find(P+'subList')[0].find(P+'run')) for c in cs.values()))
if __name__=='__main__':
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True);i=sub.add_parser('inspect');i.add_argument('source');i.add_argument('--table',type=int,required=True);i.add_argument('--output',required=True);a=sub.add_parser('apply');a.add_argument('source');a.add_argument('output');a.add_argument('--request',required=True);a.add_argument('--dry-run',action='store_true');v=p.parse_args()
 if v.command=='inspect':
  with open(v.output,'x',encoding='utf8') as f:json.dump(inspect(v.source,v.table),f,ensure_ascii=False,indent=2)
 else:print(json.dumps(apply(v.source,v.output,json.loads(Path(v.request).read_text(encoding='utf-8-sig')),v.dry_run),ensure_ascii=False,indent=2))
