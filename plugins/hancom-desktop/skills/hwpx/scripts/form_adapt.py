"""Atomic composition of existing form fill, blank-repeat, size and flow contracts."""
from pathlib import Path
import argparse,json,hashlib,os,tempfile
from safe_cell_layout import P,require,sha,parts,xml
from safe_cell_spacing import snapshot
import form_fill as fill
import safe_repeat_rows as repeats
import safe_table_layout as sizes
import safe_table_flow as flow
from safe_edit import single_line
SCHEMA='hwpx.form-adaptation.v1'

def tables(data):
 m=parts(data);return [t for name in sorted(m) if name.startswith('Contents/section') and name.endswith('.xml') for t in xml(m[name]).iter(P+'tbl')]
def labels(data,expected):
 out={s:0 for s in expected}
 for table in tables(data):
  for cell in table.iter(P+'tc'):
   text=''.join(''.join(p.itertext()) for p in cell.find(P+'subList').findall(P+'p'))
   if text in out:out[text]+=1
 return out

def validate(data,req):
 required={'schema','source_sha256','editable_reason','preserve_tables','required_labels','fields','repeat'};allowed=required|{'geometry','flow'}
 require(isinstance(req,dict) and required<=set(req) and set(req)<=allowed and req['schema']==SCHEMA,'invalid adaptation keys/schema');require(req['source_sha256']==hashlib.sha256(data).hexdigest(),'stale adaptation source');single_line(req['editable_reason'],search=True)
 ts=tables(data);protected=req['preserve_tables'];require(isinstance(protected,list) and protected and all(type(v) is int and 1<=v<=len(ts) for v in protected) and len(set(protected))==len(protected),'explicit unique protected tables required')
 need=req['required_labels'];require(isinstance(need,list) and need and all(isinstance(s,str) and s for s in need) and len(set(need))==len(need),'explicit unique required labels');counts=labels(data,need);require(all(counts.values()),'required label missing from source')
 require(isinstance(req['fields'],list),'fields list required');editable=[]
 if req['fields']:
  fill.validate_request(dict(schema=fill.REQUEST,fields=req['fields']))
  for field in req['fields']:require(type(field.get('table')) is int and field['table'] not in protected,'each field needs explicit unprotected table');editable.append(field['table'])
 repeat=req['repeat']
 if repeat is not None:
  require(isinstance(repeat,dict) and set(repeat)=={'table','expected_headers','template_row','values'},'invalid repeat specification');require(type(repeat['table']) is int and repeat['table'] not in protected and repeat['table'] not in editable,'repeat must be separate explicit unprotected table')
  repeats.checked(data,dict(schema=repeats.SCHEMA,source_sha256=req['source_sha256'],editable_reason=req['editable_reason'],**repeat))
 require(req['fields'] or repeat is not None,'explicit edits required')
 for key in ['geometry','flow']:
  seq=req.get(key,[]);require(isinstance(seq,list) and len(seq)<=4,'bounded optional operation list required')
  for op in seq:
   require(isinstance(op,dict) and type(op.get('table')) is int and op['table'] not in protected and 1<=op['table']<=len(ts),'protected/missing geometry or flow table')
   if key=='geometry':require(set(op)<= {'table','widths_mm','heights_mm'} and 'widths_mm' in op,'only explicit resize geometry allowed')
   else:require('schema' not in op and 'source_sha256' not in op,'stage schema/hash generated from actual stage')
 return ts,counts

def apply(source,output,req,dry_run=False):
 source=Path(source).resolve();output=Path(output).absolute();require(source.suffix.lower()==output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and not output.is_symlink() and output.resolve()!=source,'new HWPX output required');before=source.read_bytes();old,counts=validate(before,req);chain=[];field_results=[]
 with tempfile.TemporaryDirectory(prefix='adapt-form-',dir=output.parent) as tmp:
  current=source
  def step(kind,call):
   nonlocal current
   result_path=Path(tmp)/f'{len(chain)+1:02d}.hwpx';previous_sha=sha(current);receipt=call(current,result_path);require(sha(current)==previous_sha and receipt.get('published') is True,'stage source changed or output missing');chain.append(dict(kind=kind,input_sha256=previous_sha,output_sha256=sha(result_path),receipt=receipt,publication='private_temporary_stage'));current=result_path
  if req['fields']:
   field_request=dict(schema=fill.REQUEST,fields=req['fields']);inspection=fill.inspect_form(current,field_request);plan=fill.make_form_plan(inspection)
   step('fill_existing_fields',lambda s,o:fill.apply_form(s,o,plan));field_results=chain[-1]['receipt']['field_results']
  if req['repeat'] is not None:
   q=dict(schema=repeats.SCHEMA,source_sha256=sha(current),editable_reason=req['editable_reason'],**req['repeat']);step('adapt_blank_repeat_area',lambda s,o:repeats.apply(s,o,q))
  for specification in req.get('geometry',[]):
   q=dict(schema=sizes.SCHEMA,source_sha256=sha(current),operation='resize',**specification);step('explicit_sizes',lambda s,o:sizes.apply(s,o,q))
  for specification in req.get('flow',[]):
   q=dict(schema=flow.SCHEMA,source_sha256=sha(current),**specification);step('explicit_table_flow',lambda s,o:flow.apply(s,o,q))
  after=current.read_bytes();new=tables(after);require(len(old)==len(new) and [t.get('id') for t in old]==[t.get('id') for t in new],'table inventory changed')
  for number in req['preserve_tables']:require(snapshot(old[number-1])==snapshot(new[number-1]),'protected table changed')
  require(labels(after,req['required_labels'])==counts,'required labels changed')
  # Independent final readback of every selected field and every repeated value.
  for field in field_results:
   cell=new[field['scope']['table']-1];matches=[c for c in cell.findall('./'+P+'tr/'+P+'tc') if c.find(P+'cellAddr').get('rowAddr')==str(field['scope']['row']-1) and c.find(P+'cellAddr').get('colAddr')==str(field['scope']['column']-1)];require(len(matches)==1,'field owner missing');p=matches[0].find(P+'subList').findall(P+'p')[field['paragraph']-1];require(''.join(p.itertext())==field['after'],'final field text mismatch')
  if req['repeat'] is not None:
   table=new[req['repeat']['table']-1];cs,_=repeats.shape(table);want=[req['repeat']['expected_headers'],*req['repeat']['values']];require(len(table.findall(P+'tr'))==len(want),'final repeated row count mismatch')
   for y,row in enumerate(want):
    for x,value in enumerate(row):require(repeats.text(cs[y,x])==value,'final repeated value mismatch')
  require(sha(source)==req['source_sha256'],'source changed during adaptation');candidate_sha=sha(current)
  if not dry_run:os.link(current,output)
 return dict(schema='hwpx.form-adaptation-receipt.v1',status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',native='pending',source_sha256=req['source_sha256'],candidate_sha256=candidate_sha,published=not dry_run,request=req,steps=chain,checks=dict(allStagesVerified=True,protectedTablesExact=True,requiredLabelsExact=True,allRequestedFieldsAndRepeatValuesReadBack=True,finalPublicationAtomic=True),completion='adapted_candidate_native_pending')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output');p.add_argument('--request',required=True);p.add_argument('--dry-run',action='store_true');v=p.parse_args();print(json.dumps(apply(v.source,v.output,json.loads(Path(v.request).read_text(encoding='utf-8-sig')),v.dry_run),ensure_ascii=False,indent=2))
