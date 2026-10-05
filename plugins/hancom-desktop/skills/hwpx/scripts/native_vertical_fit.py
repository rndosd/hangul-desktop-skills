"""Opt-in native-existing vertical margin grid, keeping saved file structure."""
from pathlib import Path
import sys,json
import safe_native_vertical_margins as editor
import auto_margin_fit as measurement
import run_native_job as runner
import native_write as evidence
import compare_active_semantics as sem
import compare_package_definitions as definitions
import pymupdf
SCHEMA='hwpx.native-vertical-fit.v1'

def write(p,v):
    with Path(p).open('x',encoding='utf8') as f:json.dump(v,f,ensure_ascii=False,indent=2)

def policy(source,q):
    editor.require(isinstance(q,dict) and set(q)=={'schema','sourceSha256','minimumHwpunit','stepMilliMm','maxAttempts','maxOverflowLines','editableReason'} and q['schema']==SCHEMA,'exact existing-fit policy required')
    editor.require(q['sourceSha256']==editor.sha(source),'stale fit source')
    editor.require(type(q['minimumHwpunit']) is int and 2835<=q['minimumHwpunit']<=7200,'10mm or larger minimum required')
    editor.require(type(q['stepMilliMm']) is int and 250<=q['stepMilliMm']<=1000,'bounded grid step required')
    editor.require(type(q['maxAttempts']) is int and 1<=q['maxAttempts']<=20,'bounded attempts required')
    editor.require(type(q['maxOverflowLines']) is int and 1<=q['maxOverflowLines']<=3,'small overflow only')
    editor.oracle.single_line(q['editableReason'],search=True);editor.require(len(q['editableReason'])>=8,'specific reason required')
    return editor.inspect(source)

def grid(b,q):
    old={k:int(b['marginAttrs'][k]) for k in ['top','bottom']}
    for i in range(1,q['maxAttempts']+1):
        delta=round(i*q['stepMilliMm']*7200/25400)
        margins={k:v-delta for k,v in old.items()}
        if min(margins.values())<q['minimumHwpunit']:break
        yield dict(index=i,deltaPerSideHwpunit=delta,totalReductionHwpunit=2*delta,**margins)

def proof(a,b):
    active=sem.compare(a,b);defs=definitions.audit(a,b)
    return dict(status='PASS' if active['status']=='PASS_ACTIVE_SEMANTICS' and defs['allHeaderDefinitionsExact'] else 'FAIL',active=active,allDefinitions=defs)

def equal(a,b):
    with pymupdf.open(a) as x,pymupdf.open(b) as y:
        return len(x)==len(y) and all(x[i].rect==y[i].rect and x[i].get_pixmap().samples==y[i].get_pixmap().samples for i in range(len(x)))

def run(source,folder,q):
    source=Path(source).resolve(strict=True);folder=Path(folder).absolute();editor.require(not folder.exists() and folder.parent.is_dir(),'new fit folder required')
    b=policy(source,q);items=list(grid(b,q));folder.mkdir()
    frozen=dict(source=evidence.gate.ref(source),policy=q,binding=b,grid=items,
        tools=[evidence.gate.ref(p) for p in [__file__,editor.__file__,measurement.__file__,runner.__file__,sem.__file__,definitions.__file__]],
        preservation='No HWPX tolerance. Only existing top/bottom margins may shrink; all other content/format/geometry/package preserved. Full native active+all definitions exact; PDF equality separate.',
        minimumScope='opposing vertical margins only, discrete0.5mm grid; no horizontal or continuous global optimum claim')
    write(folder/'inputs.json',frozen);jobs=[];attempts=[]
    def native(src,mode,out,pdf,job):
        for r in frozen['tools']:evidence.gate.verify_ref(r)
        observedNative=runner.run(src,mode,out,pdf,job,'host-approved')
        if observedNative['status']!='PASS_NATIVE':
            result.update(status='ENVIRONMENT_BLOCKED',nativeFailure=observedNative,failedJob=str(job),reason='stop serial batch; no automatic retry or next case')
            write(folder/'selection.json',result)
            raise ValueError('NATIVE_BLOCKED:'+json.dumps(observedNative,ensure_ascii=False))
        jobs.append(evidence.receipt_valid(job,src,out,pdf))
    result=dict(status='PENDING',baseline=None,attempts=attempts,nativeReceipts=jobs,selected=None,visual='NOT_REVIEWED',fullCompletion=False)
    baseline=folder/'baseline';baseline.mkdir();native(source,'OpenOnly',None,baseline/'before.pdf',baseline/'before-job')
    observed=measurement.inspect_pdf(baseline/'before.pdf',source);write(baseline/'measurement.json',observed);result['baseline']=dict(pdf=evidence.gate.ref(baseline/'before.pdf'),measurement=observed)
    reason=('content_inconclusive' if observed['missing_fragments'] else 'already_one_page' if observed['page_count']==1 else 'not_two_page_small_overflow' if observed['page_count']!=2 or observed['tail_images'] or not 1<=observed['tail_line_count']<=q['maxOverflowLines'] or observed['tail_fraction']>.25 else None)
    if reason:result.update(status='SKIPPED',reason=reason)
    else:
        for item in items:
            d=folder/f"candidate-{item['index']:03d}";d.mkdir();request=dict(schema=editor.SCHEMA,sourceSha256=editor.sha(source),binding=b,top=item['top'],bottom=item['bottom'],editableReason=q['editableReason'])
            write(d/'request.json',request);write(d/'dry-run.json',editor.apply(source,d/'edited.hwpx',request,True));editor.require(not (d/'edited.hwpx').exists(),'dry-run published file')
            write(d/'edit.json',editor.apply(source,d/'edited.hwpx',request));write(d/'preservation.json',editor.verify(source,d/'edited.hwpx',request))
            native(d/'edited.hwpx','OpenOnly',None,d/'before.pdf',d/'before-job');native(d/'edited.hwpx','SaveAs',d/'saved.hwpx',d/'saved.pdf',d/'saved-job')
            check=proof(d/'edited.hwpx',d/'saved.hwpx');write(d/'save-proof.json',check);obs=measurement.inspect_pdf(d/'saved.pdf',source);write(d/'measurement.json',obs)
            row=dict(grid=item,case=str(d),saved=evidence.gate.ref(d/'saved.hwpx'),pdf=evidence.gate.ref(d/'saved.pdf'),measurement=obs,internal=check['status'],pdfPixelsEqual=equal(d/'before.pdf',d/'saved.pdf'))
            attempts.append(row);print('fit',folder.name,item['index'],obs['page_count'],check['status'],flush=True)
            if check['status']!='PASS' or not row['pdfPixelsEqual']:
                result.update(status='FAIL_INTERNAL_OR_OUTPUT',reason='strict failure retained; no skipping unsafe smaller candidate');break
            if obs['page_count']==1 and obs['pdf_content_checked']:
                result.update(status='PENDING_VISUAL_REVIEW',selected=row,reason='first fit in frozen vertical grid');break
        else:result.update(status='NO_FIT',reason='no fit within frozen floor and grid')
    evidence.gate.verify_ref(frozen['source']);result['sourceUnchanged']=True
    write(folder/'selection.json',result);return result
