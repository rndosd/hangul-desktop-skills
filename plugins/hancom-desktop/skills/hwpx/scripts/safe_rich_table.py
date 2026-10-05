"""Bounded rich row clone and horizontal merge using public 6.3.0 APIs.
New row text is explicitly mapped to each existing paragraph/run. Merge retains
both cells' paragraph/run content, rather than the library's left-cell-only text.
Never handles nested/controlled cells. Independently verifies before publishing.
"""
import argparse,copy,hashlib,io,json,os
from pathlib import Path
from importlib.metadata import version
from hwpx import HwpxDocument
from hwpx.table_patch import apply_table_ops
from hwpx.tools.package_validator import validate_editor_open_safety
from hwpx.tools.toc_author import ensure_paragraph_anchor_id
from safe_rich_row_delete import check_table
from safe_cell_layout import locate,P,snap,require,xml
from workspace_candidate_directory import workspace_candidate_directory
SCHEMA='hwpx.rich-table.v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def fingerprint(t):return hashlib.sha256(json.dumps(snap(t),ensure_ascii=False).encode()).hexdigest()
def inspect(source,table):
 m,part,r,t=locate(Path(source).read_bytes(),table);rows=check_table(t)
 return dict(schema=SCHEMA,source_sha256=sha(source),table=table,table_sha256=fingerprint(t),rows=[[[[(x.text or '') for x in run.findall(P+'t')] or [''] for run in p.findall(P+'run')] for c in tr.findall(P+'tc') for p in c.findall('./'+P+'subList/'+P+'p')] for tr in rows],native='NOT_CHECKED')
def cell_model(c):
 return [dict(attrs=dict(p.attrib),runs=[dict(attrs=dict(r.attrib),text=''.join(x.text or '' for x in r.findall(P+'t'))) for r in p.findall(P+'run')]) for p in c.findall('./'+P+'subList/'+P+'p')]
def api_table(doc,expected):
 # Library traversal order differs from the package inspector in real reports.
 matches=[t for t in doc.tables.all if t.element.get('id')==expected.get('id') and snap(t.element)==snap(expected)]
 require(len(matches)==1,'exact API table identity/structure required');return matches[0]
def comparable(n,row=None,clone=False,texts=None,dirty=False):
 tag,attrs,text,children=snap(n)
 def walk(v,y=None,paragraph=-1,run=-1):
  tag,attrs,text,children=v;attrs=dict(attrs)
  if tag==P+'cellAddr' and row is not None:attrs['rowAddr']=str(row)
  if clone and tag==P+'p':attrs.pop('id',None)
  if dirty and tag==P+'tc':attrs.pop('dirty',None)
  if clone and tag==P+'linesegarray':return None
  return tag,tuple(sorted(attrs.items())),text,tuple(w for c in children if (w:=walk(c)) is not None)
 return walk((tag,attrs,text,children))
def verify(before,after,req):
 bm,part,br,bt=locate(before,req['table']);am,ap,ar,at=locate(after,req['table']);require(part==ap and set(bm)==set(am),'package inventory changed')
 for n in bm:
  if n!=part and not n.startswith('Preview/'):require(bm[n]==am[n],'non-target member changed: '+n)
 def outside(n,t):return ('TARGET',) if n is t else (n.tag,tuple(sorted(n.attrib.items())),n.text or '',n.tail or '',tuple(outside(c,t) for c in n))
 require(outside(br,bt)==outside(ar,at),'non-target section changed')
 rows=check_table(bt);new=at.findall(P+'tr');idx=req['row']-1
 allowed={'rowCnt'} if req['operation']=='clone_after' else set()
 require({k:v for k,v in bt.attrib.items() if k not in allowed}=={k:v for k,v in at.attrib.items() if k not in allowed},'table attrs changed')
 require([snap(n) for n in bt if n.tag!=P+'tr']==[snap(n) for n in at if n.tag!=P+'tr'],'table geometry/position changed')
 if req['operation']=='clone_after':
  require(len(new)==len(rows)+1 and int(at.get('rowCnt'))==len(new),'one added row required');check_table(at)
  for y,n in enumerate(new):
   if y==idx+1:continue
   old=rows[y if y<=idx else y-1]
   require(comparable(old,row=y)==comparable(n),'retained row changed')
  oldcells=rows[idx].findall(P+'tc');newcells=new[idx+1].findall(P+'tc')
  for c,(x,y) in enumerate(zip(oldcells,newcells)):
   expected=copy.deepcopy(x)
   for p,values in zip(expected.findall('./'+P+'subList/'+P+'p'),req['cells'][c]):
    for r,value in zip(p.findall(P+'run'),values):
     # Oracle copy only, never serialized into an edited document.
     ts=r.findall(P+'t');require(len(ts)==1 or value=='','cannot add text to a childless styled run')
     if ts:ts[0].text=value
   require(comparable(expected,row=idx+1,clone=True,dirty=True)==comparable(y,clone=True,dirty=True),'clone text/style/geometry mismatch')
  oldids={p.get('id') for name,data in bm.items() if name.startswith('Contents/section') and name.endswith('.xml') for p in xml(data).iter(P+'p')};ids=[p.get('id') for p in new[idx+1].iter(P+'p')]
  require(len(ids)==len(set(ids)) and not oldids.intersection(ids),'new paragraph IDs collide')
 else:
  require(len(new)==len(rows) and int(at.get('rowCnt'))==len(rows),'merge changed row count')
  for i,(x,y) in enumerate(zip(rows,new)):
   if i!=idx:require(snap(x)==snap(y),'unselected row changed')
  cells=rows[idx].findall(P+'tc');aftercells=new[idx].findall(P+'tc');lo,hi=req['columns'];lo-=1;hi-=1
  require(len(aftercells)==len(cells)-1,'two adjacent cells must become one')
  for i,c in enumerate(cells):
   if i in [lo,hi]:continue
   j=i if i<lo else i-1;require(snap(c)==snap(aftercells[j]),'unselected cell changed')
  merged=aftercells[lo];left,right=cells[lo],cells[hi]
  expected=copy.deepcopy(left);expected.find(P+'cellSpan').set('colSpan','2');expected.find(P+'cellSz').set('width',str(sum(int(x.find(P+'cellSz').get('width')) for x in [left,right])))
  expected.find(P+'cellSz').set('height',str(max(int(x.find(P+'cellSz').get('height')) for x in [left,right])))
  sub=expected.find(P+'subList')
  for p in right.findall('./'+P+'subList/'+P+'p'):sub.append(copy.deepcopy(p))
  require(comparable(expected,clone=True,dirty=True)==comparable(merged,clone=True,dirty=True),'merged content/style/border/geometry mismatch')
  retained=list(left.iter(P+'p'));actual=list(merged.iter(P+'p'))
  require([p.get('id') for p in retained]==[p.get('id') for p in actual[:len(retained)]],'retained paragraph IDs changed')
  oldids={p.get('id') for name,data in bm.items() if name.startswith('Contents/section') and name.endswith('.xml') for p in xml(data).iter(P+'p')};newids=[p.get('id') for p in actual[len(retained):]]
  require(len(newids)==len(set(newids)) and not oldids.intersection(newids),'appended paragraph IDs collide')
  # No overlaps/holes in the resulting horizontal grid.
  require([(int(c.find(P+'cellAddr').get('colAddr')),int(c.find(P+'cellSpan').get('colSpan'))) for c in aftercells]==[(i,2 if i==lo else 1) for i in range(len(cells)) if i!=hi],'merged grid mismatch')
 return dict(nonTargetPackageExact=True,nonTargetSectionExact=True,retainedRowsExact=True,requestedTextAndStylesExact=True,geometryExact=True)
def apply(source,output,request,dry_run=False):
 require(version('python-hwpx')=='6.3.0','unverified API version');source=Path(source).resolve(strict=True);output=Path(output).absolute();req=dict(request)
 require(output.suffix.lower()=='.hwpx' and not output.exists() and output.parent.is_dir() and output.resolve()!=source,'new output required')
 v=inspect(source,req['table']);base={'schema','source_sha256','table','table_sha256','operation','row','editable_reason'}
 keys=base|({'cells'} if req['operation']=='clone_after' else {'columns'} if req['operation']=='merge_horizontal' else set())
 require(set(req)==keys and req['schema']==SCHEMA and req['source_sha256']==v['source_sha256'] and req['table_sha256']==v['table_sha256'],'invalid/stale request')
 require(isinstance(req['editable_reason'],str) and len(req['editable_reason'].strip())>=8,'explicit reason required')
 before=source.read_bytes();m,part,root,t=locate(before,req['table']);rows=check_table(t);require(type(req['row']) is int and 2<=req['row']<=len(rows),'data row only');idx=req['row']-1
 with workspace_candidate_directory(prefix='rich-table-',dir=output.parent) as folder:
  work=Path(folder);candidate=work/'candidate.hwpx'
  if req['operation']=='clone_after':
   cells=rows[idx].findall(P+'tc');require(len(rows)<100 and isinstance(req['cells'],list) and len(req['cells'])==len(cells),'bounded complete cell map required')
   for cell,paras in zip(cells,req['cells']):
    model=cell_model(cell);require(isinstance(paras,list) and len(paras)==len(model),'paragraph map mismatch')
    for p,values in zip(model,paras):
     require(isinstance(values,list) and len(values)==len(p['runs']) and all(isinstance(v,str) and not any(c in v for c in '\r\n\t') for v in values),'plain explicit run map required')
   result=apply_table_ops(before,[dict(op='insert_row_by_clone',section_path=part,table_index=list(root.iter(P+'tbl')).index(t),ref_row=idx,count=1)]);require(result.ok,'clone API failed')
   intermediate=work/'intermediate.hwpx';intermediate.write_bytes(result.data)
   try:
    with HwpxDocument.open(intermediate) as doc:
     table=api_table(doc,locate(result.data,req['table'])[3])
     for c,paras in enumerate(req['cells']):
      for p,values in zip(table.cell(idx+1,c).paragraphs,paras):
       ensure_paragraph_anchor_id(doc,p)
       for run,value in zip(p.runs,values):
        if run.text!=value:run.text=value
     doc.save_to_path(candidate)
   finally:intermediate.unlink(missing_ok=True)
  elif req['operation']=='merge_horizontal':
   cols=req['columns'];require(isinstance(cols,list) and len(cols)==2 and all(type(c) is int for c in cols) and 1<=cols[0]<cols[1]<=int(t.get('colCnt')) and cols[1]==cols[0]+1,'two adjacent columns required')
   models=cell_model(rows[idx].findall(P+'tc')[cols[1]-1]);require(all(all(p['attrs'].get(k,'0')=='0' for k in ['pageBreak','columnBreak','merged']) for p in models),'controlled paragraph flags unsupported')
   with HwpxDocument.open(source) as doc:
    table=api_table(doc,t);left=table.merge_cells(idx,cols[0]-1,idx,cols[1]-1)
    for model in models:
     rs=model['runs'];p=left.add_paragraph(rs[0]['text'],para_pr_id_ref=model['attrs']['paraPrIDRef'],style_id_ref=model['attrs']['styleIDRef'],char_pr_id_ref=rs[0]['attrs']['charPrIDRef'])
     for run in rs[1:]:p.add_run(run['text'],char_pr_id_ref=run['attrs']['charPrIDRef'])
     ensure_paragraph_anchor_id(doc,p)
    doc.save_to_path(candidate)
  else:raise ValueError('unsupported operation')
  checks=verify(before,candidate.read_bytes(),req);require(validate_editor_open_safety(candidate).ok,'open safety failed');require(sha(source)==req['source_sha256'],'source changed')
  result=dict(status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',source_sha256=sha(source),candidate_sha256=sha(candidate),checks=checks,native='NOT_CHECKED')
  if not dry_run:os.link(candidate,output)
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True);i=s.add_parser('inspect');i.add_argument('source');i.add_argument('--table',type=int,required=True);i.add_argument('--output',required=True)
 a=s.add_parser('apply');a.add_argument('source');a.add_argument('output');a.add_argument('--request',required=True);a.add_argument('--dry-run',action='store_true');v=p.parse_args()
 if v.command=='inspect':
  result=inspect(v.source,v.table)
  with Path(v.output).open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
 else:result=apply(v.source,v.output,json.loads(Path(v.request).read_text(encoding='utf-8-sig')),v.dry_run)
 print(json.dumps(result,ensure_ascii=False))
