"""Explicit native writing stage for selected table aggregate height only.

Hancom computes the height; we never synthesize its layout. Other active content,
styles, cell dimensions and positions must remain equal. Strict gate unchanged.
Actual all-page review is a hash-bound attestation, never inferred from COM.
"""
import argparse,copy,json,os
from pathlib import Path
import compare_active_semantics as sem
import hancom_completion_gate as gate
import run_native_job as runner
import compare_package_definitions as definitions
P=sem.P
S=Path(__file__).resolve().parent
def need(ok,message):
 if not ok:raise ValueError(message)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,v):gate.write_new(Path(p),v)
def targets(graph,ids):
 result={}
 def visit(n,nested=False):
  if not isinstance(n,list) or len(n)!=4:return
  tag,attrs,text,children=n
  if tag==P+'tbl':
   identity=attrs.get('id')
   if identity in ids:
    need(not nested and identity not in result,'unique unnested target table required')
    sizes=[c for c in children if c[0]==P+'sz'];need(len(sizes)==1,'one target table size required')
    size=sizes[0];h=size[1].get('height');need(isinstance(h,str) and h.isdigit() and 0<int(h)<100000000,'positive bounded absolute table height required')
    need(size[1].get('heightRelTo')=='ABSOLUTE','absolute table height required');result[identity]=size
   nested=True
  for c in children:visit(c,nested)
 for section in graph['sections']:visit(section)
 need(set(result)==set(ids),'all target IDs must exist exactly once');return result
def prove(source,final,ids):
 need(isinstance(ids,list) and 1<=len(ids)<=10 and all(isinstance(x,str) and x for x in ids) and len(ids)==len(set(ids)),'explicit unique target IDs required')
 base=sem.compare(source,final);a,b=sem.Package(source),sem.Package(final)
 av,bv=a.active(),b.active();allowed_before=targets(av,ids);allowed_after=targets(bv,ids);changes=[]
 for identity in ids:
  before,after=allowed_before[identity],allowed_after[identity]
  changes.append(dict(tableId=identity,beforeHeight=before[1]['height'],nativeHeight=after[1]['height']))
  # Oracle-only in-memory expected change; never serialized to an edited HWPX.
  before[1]['height']=after[1]['height']
 stable=all(base['checks'][k] for k in ['paragraphTextExact','countsExact','sectionSpineExact','binaryPayloadsExact'])
 package_audit=definitions.audit(source,final)
 checks=dict(contentCountsAndAssetsExact=stable,fullActiveTreeOutsideRequestedHeightExact=av==bv,fontInventoryExact=base['fontInventories']['before']==base['fontInventories']['after'],schemaVersionExact=base['headerVersions']['before']==base['headerVersions']['after'],noUnknownChangedMembers=not base['unknownChangedMembers'],allHeaderDefinitionsIncludingUnusedExact=package_audit['allHeaderDefinitionsExact'])
 gate.verify_ref(a.ref);gate.verify_ref(b.ref)
 return dict(status='PASS_REQUESTED_GEOMETRY' if all(checks.values()) else 'BLOCKED_OTHER_CHANGE',source=a.ref,final=b.ref,targetIds=ids,changes=changes,checks=checks,packageAudit=package_audit,unmaskedComparison=base,strictCompletion='NOT_GRANTED',limitations=['Only selected direct table aggregate height is intentional','Layout caches require current native PDF and all-page review','Preview/package metadata and other Hancom versions remain unverified; byte differences reported'])
def prepare(source,folder,ids,context):
 source=Path(source).resolve(strict=True);folder=Path(folder).absolute()
 need(not folder.exists() and folder.parent.is_dir(),'new work folder in existing parent required')
 need(context in ['ordinary-shell','host-approved'],'explicit user/host context required')
 graph=sem.Package(source).active();targets(graph,ids)
 folder.mkdir();plan=dict(schema='hwpx.native-write.v1',source=gate.ref(source),targetIds=ids,context=context,allowedChange='selected-table-direct-sz-height-only',tools={str(p):gate.ref(p) for p in [S/'native_write.py',S/'compare_package_definitions.py',S/'compare_active_semantics.py',S/'run_native_job.py',S/'hancom_completion_gate.py']})
 write(folder/'plan.json',plan);return plan
def plan_at(folder):
 folder=Path(folder).resolve(strict=True);plan=read(folder/'plan.json');need(plan['schema']=='hwpx.native-write.v1' and plan['allowedChange']=='selected-table-direct-sz-height-only','invalid plan')
 gate.verify_ref(plan['source'])
 for ref in plan['tools'].values():gate.verify_ref(ref)
 return folder,plan
def receipt_valid(folder,source,output,pdf=None):
 v=read(folder/'native/receipt.json');need(v['status']=='PASS_FULL' and v['comCreated'] is True and v['securityModuleRegistered'] is True and v['sourceUnchanged'] is True,'current native receipt required')
 need(v['sourceSha256Before'].lower()==runner.sha(source) and v['sourceSha256After'].lower()==runner.sha(source),'native source binding failed')
 artifacts={str(Path(a['path']).resolve()):a for a in v['artifacts']}
 for p in [output,pdf]:
  if p:need(str(Path(p).resolve()) in artifacts and artifacts[str(Path(p).resolve())]['sha256'].lower()==runner.sha(p),'native output binding failed')
 need(v['cleanup']['owned'] and v['cleanup']['quit'] and not v['cleanup']['remaining'] and not v['cleanup']['forced'],'normal owned cleanup required')
 return gate.ref(folder/'native/receipt.json')
def execute(folder,pdf_enabled=True):
 d,p=plan_at(folder);source=Path(p['source']['path']);trial=d/'trial.hwpx';context=p['context'];refs=[]
 if pdf_enabled:
  r=runner.run(source,'OpenOnly',None,d/'before.pdf',d/'before-job',context);need(r['status']=='PASS_NATIVE','before OpenOnly failed');refs.append(receipt_valid(d/'before-job',source,None,d/'before.pdf'))
 r=runner.run(source,'SaveAs',trial,d/'trial.pdf' if pdf_enabled else None,d/'write-job',context);need(r['status']=='PASS_NATIVE','native write failed')
 refs.append(receipt_valid(d/'write-job',source,trial,d/'trial.pdf' if pdf_enabled else None))
 proof=prove(source,trial,p['targetIds']);write(d/'write-proof.json',proof)
 if proof['status']!='PASS_REQUESTED_GEOMETRY':
  r=dict(status='BLOCKED_OTHER_CHANGE',source=p['source'],proof=gate.ref(d/'write-proof.json'),nativeReceipts=refs,publication=False);write(d/'result.json',r);return r
 if not pdf_enabled:
  r=dict(status='PENDING_REPEAT_AND_VISUAL',publication=False);write(d/'result.json',r);return r
 r=runner.run(trial,'SaveAs',d/'repeat.hwpx',d/'repeat.pdf',d/'repeat-job',context);need(r['status']=='PASS_NATIVE','repeat SaveAs failed')
 refs.append(receipt_valid(d/'repeat-job',trial,d/'repeat.hwpx',d/'repeat.pdf'))
 repeat=sem.compare(trial,d/'repeat.hwpx');write(d/'repeat-proof.json',repeat)
 need(repeat['status']=='PASS_ACTIVE_SEMANTICS','repeat active content changed')
 need(definitions.audit(trial,d/'repeat.hwpx')['allHeaderDefinitionsExact'],'repeat unused definitions changed')
 import pymupdf as pdf
 with pdf.open(d/'before.pdf') as a,pdf.open(d/'trial.pdf') as b,pdf.open(d/'repeat.pdf') as c:
  need(len(a)==len(b)==len(c),'page count changed during writing')
  equal=[a[i].get_pixmap().samples==b[i].get_pixmap().samples==c[i].get_pixmap().samples for i in range(len(a))];need(all(equal),'native writing changed rendered layout')
 r=dict(status='READY_FOR_ALL_PAGE_REVIEW',publication=False,plan=gate.ref(d/'plan.json'),source=p['source'],proof=gate.ref(d/'write-proof.json'),repeatProof=gate.ref(d/'repeat-proof.json'),nativeReceipts=refs,final=gate.ref(trial),pdf=gate.ref(d/'trial.pdf'),pages=len(equal),allBeforeTrialRepeatPagesPixelEqual=equal)
 write(d/'result.json',r);return r
def publish(folder,review_path,output,pdf_output):
 d,p=plan_at(folder);r=read(d/'result.json');need(r['status']=='READY_FOR_ALL_PAGE_REVIEW','native write not ready')
 for key in ['plan','source','proof','repeatProof','final','pdf']:gate.verify_ref(r[key])
 for ref in r['nativeReceipts']:gate.verify_ref(ref)
 need(prove(p['source']['path'],r['final']['path'],p['targetIds'])['status']=='PASS_REQUESTED_GEOMETRY','geometry proof invalidated')
 need(sem.compare(d/'trial.hwpx',d/'repeat.hwpx')['status']=='PASS_ACTIVE_SEMANTICS','repeat file invalidated')
 need(definitions.audit(d/'trial.hwpx',d/'repeat.hwpx')['allHeaderDefinitionsExact'],'repeat unused definitions invalidated')
 receipt_valid(d/'before-job',p['source']['path'],None,d/'before.pdf');receipt_valid(d/'write-job',p['source']['path'],d/'trial.hwpx',d/'trial.pdf');receipt_valid(d/'repeat-job',d/'trial.hwpx',d/'repeat.hwpx',d/'repeat.pdf')
 review=read(review_path);need(review.get('result')==gate.ref(d/'result.json') and review.get('pdf')==r['pdf'],'review not bound to current result/PDF')
 need(bool(review.get('reviewer')) and bool(review.get('reviewedAt')) and review.get('outcome')=='PASS','actual review required')
 need([x['page'] for x in review['pages']]==list(range(1,r['pages']+1)) and all(x['outcome']=='PASS' and len(x['observation'])>=12 for x in review['pages']),'all pages reviewed in order required')
 output,pdf_output=Path(output).absolute(),Path(pdf_output).absolute()
 need(output.suffix.lower()=='.hwpx' and pdf_output.suffix.lower()=='.pdf' and output!=pdf_output and all(not x.exists() and x.parent.is_dir() for x in [output,pdf_output]),'distinct new delivery artifacts required')
 os.link(d/'trial.hwpx',output)
 try:os.link(d/'trial.pdf',pdf_output)
 except BaseException:output.unlink();raise
 result=dict(status='PASS_NATIVE_WRITE_BOUNDED',output=gate.ref(output),pdf=gate.ref(pdf_output),review=gate.ref(review_path),strictCompletion='NOT_GRANTED',installedReplacement=False,settingsChanges=False)
 write(d/'publication.json',result);return result
if __name__=='__main__':
 a=argparse.ArgumentParser();s=a.add_subparsers(dest='action',required=True)
 p=s.add_parser('prepare');p.add_argument('source');p.add_argument('--work',required=True);p.add_argument('--table-id',action='append',required=True);p.add_argument('--context',choices=['ordinary-shell','host-approved'],required=True)
 e=s.add_parser('execute');e.add_argument('work');e.add_argument('--without-pdf',action='store_true')
 e=s.add_parser('publish');e.add_argument('work');e.add_argument('--review',required=True);e.add_argument('--output',required=True);e.add_argument('--pdf-output',required=True)
 v=a.parse_args()
 try:
  result=prepare(v.source,v.work,v.table_id,v.context) if v.action=='prepare' else execute(v.work,not v.without_pdf) if v.action=='execute' else publish(v.work,v.review,v.output,v.pdf_output)
  print(json.dumps(result,ensure_ascii=False));raise SystemExit(3 if result.get('status','').startswith('BLOCKED') else 0)
 except (ValueError,KeyError,gate.GateError) as e:print(json.dumps(dict(status='BLOCKED',error=str(e)),ensure_ascii=False));raise SystemExit(3)
