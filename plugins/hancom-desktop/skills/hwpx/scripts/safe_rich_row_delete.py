"""Experimental filled rectangular table row deletion, no clone/fill fallback.
Supports bounded plain multi-paragraph/run cells. Every unselected subtree
and non-target package member is checked; only rowCnt/rowAddr may change.
"""
from pathlib import Path
import argparse,json,hashlib,os
from hwpx.table_patch import apply_table_ops
from hwpx.tools.package_validator import validate_editor_open_safety
from safe_cell_layout import parts,xml,P,snap,require,locate
from workspace_candidate_directory import workspace_candidate_directory

SCHEMA='hwpx.rich-row-delete.v1'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def check_table(t):
 rows=t.findall(P+'tr');cols=int(t.get('colCnt','0'))
 require(2<=len(rows)<=100 and len(rows)==int(t.get('rowCnt')) and 1<=cols<=12,'bounded rectangular table required')
 for y,tr in enumerate(rows):
  cells=tr.findall(P+'tc');require(len(cells)==cols,'merged or incomplete row')
  for x,c in enumerate(cells):
   require(dict(c.find(P+'cellSpan').attrib)==dict(colSpan='1',rowSpan='1'),'merged cell unsupported')
   require(dict(c.find(P+'cellAddr').attrib)==dict(colAddr=str(x),rowAddr=str(y)),'cell grid mismatch')
   sub=c.find(P+'subList');ps=sub.findall(P+'p')
   require(len(ps)==len(sub) and 1<=len(ps)<=5,'one to five plain paragraphs required')
   for p in ps:
    require(all(n.tag in (P+'run',P+'linesegarray') for n in p),'controlled paragraph unsupported')
    runs=p.findall(P+'run');require(1<=len(runs)<=20,'one to twenty styled runs required')
    for r in runs:
     require(set(r.attrib)=={'charPrIDRef'} and (len(r)==0 or len(r)==1 and r[0].tag==P+'t' and not len(r[0])),'plain styled run or childless native empty run only')
 return rows
def inspect(source,table):
 m,part,root,t=locate(Path(source).read_bytes(),table);rows=check_table(t)
 return dict(schema=SCHEMA,source_sha256=sha(source),table=table,table_sha256=hashlib.sha256(json.dumps(snap(t),ensure_ascii=False).encode()).hexdigest(),rows=[[''.join(c.itertext()) for c in tr.findall(P+'tc')] for tr in rows])
def validate_request(source,req):
 require(set(req)=={'schema','source_sha256','table','table_sha256','delete_row','editable_reason'},'exact request keys required')
 v=inspect(source,req['table']);require(req['schema']==SCHEMA and req['source_sha256']==v['source_sha256'] and req['table_sha256']==v['table_sha256'],'stale source/table binding')
 require(len(v['rows'])>=3,'at least one data row must remain')
 require(type(req['delete_row']) is int and 2<=req['delete_row']<=len(v['rows']),'data row only')
 require(isinstance(req['editable_reason'],str) and len(req['editable_reason'].strip())>=8,'authorized deletion reason required')
 return v
def verify(before,after,req):
 bm,part,br,bt=locate(before,req['table']);am,ap,ar,at=locate(after,req['table']);require(part==ap and set(bm)==set(am),'package inventory changed')
 for n in bm:
  if n!=part:require(bm[n]==am[n],'non-target package member changed: '+n)
 def outside(n,target):
  return ['SELECTED_TABLE'] if n is target else [n.tag,sorted(n.attrib.items()),n.text or '',n.tail or '',[outside(c,target) for c in n]]
 require(outside(br,bt)==outside(ar,at),'non-target section subtree changed')
 brow=check_table(bt);arow=check_table(at)
 require(len(arow)==len(brow)-1,'one row deletion required')
 require({k:v for k,v in bt.attrib.items() if k!='rowCnt'}=={k:v for k,v in at.attrib.items() if k!='rowCnt'},'table properties changed')
 require([snap(n) for n in bt if n.tag!=P+'tr']==[snap(n) for n in at if n.tag!=P+'tr'],'table geometry/border/position changed')
 # Read-only normalized expectation: existing paragraph/cache/style IDs stay exact.
 expected=[r for i,r in enumerate(brow) if i!=req['delete_row']-1]
 for y,(b,a) in enumerate(zip(expected,arow)):
  value=snap(b)
  def adjust(n):
   tag,attrs,txt,children=n
   if tag==P+'cellAddr':attrs=tuple((k,str(y) if k=='rowAddr' else v) for k,v in attrs)
   return (tag,attrs,txt,tuple(adjust(c) for c in children))
  require(adjust(value)==snap(a),'retained row content/style/cache changed')
 return dict(nonTargetPackageByteExact=True,allOtherTablesPicturesBodyExact=True,retainedRowsStylesAndParagraphsExact=True,deletedDataRowOnly=True)
def apply(source,output,req,dry_run=False):
 source=Path(source).resolve(strict=True);output=Path(output).absolute()
 require(output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and output!=source,'new output path required')
 validate_request(source,req);before=source.read_bytes();m,part,r,t=locate(before,req['table'])
 result=apply_table_ops(before,[dict(op='delete_row',section_path=part,table_index=list(r.iter(P+'tbl')).index(t),row=req['delete_row']-1)])
 require(result.ok,'public row deletion failed: '+str(result.to_dict()));checks=verify(before,result.data,req)
 with workspace_candidate_directory(prefix='rich-row-delete-',dir=output.parent) as temp:
  p=Path(temp)/'candidate.hwpx';p.write_bytes(result.data)
  require(validate_editor_open_safety(p).ok,'candidate editor safety failed')
  require(sha(source)==req['source_sha256'],'source changed')
  if not dry_run:os.link(p,output)
 return dict(status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',native='NOT_CHECKED',source_sha256=sha(source),candidate_sha256=hashlib.sha256(result.data).hexdigest(),checks=checks)
if __name__=='__main__':
 a=argparse.ArgumentParser();sub=a.add_subparsers(dest='cmd',required=True)
 i=sub.add_parser('inspect');i.add_argument('source');i.add_argument('--table',required=True,type=int);i.add_argument('--output',required=True)
 x=sub.add_parser('apply');x.add_argument('source');x.add_argument('output');x.add_argument('--request',required=True);x.add_argument('--dry-run',action='store_true')
 v=a.parse_args()
 if v.cmd=='inspect':
  result=inspect(v.source,v.table)
  with Path(v.output).open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
 else:result=apply(v.source,v.output,json.loads(Path(v.request).read_text(encoding='utf-8-sig')),v.dry_run)
 print(json.dumps(result,ensure_ascii=False))
