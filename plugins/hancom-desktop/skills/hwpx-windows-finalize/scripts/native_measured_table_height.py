"""Opt-in measured table-height preparation; strict native comparison unchanged."""
from pathlib import Path
import sys,json,subprocess,shutil,os
from importlib.metadata import version
S=Path(__file__).resolve().parent
sys.path.insert(0,str(S.parent.parent/'hwpx/scripts'))
from candidate_runtime import activate
activate()
from hwpx import HwpxDocument
import safe_edit as oracle
import safe_native_page_settings as adapter
import compare_active_semantics as sem
import compare_package_definitions as definitions
import audit_native_file_roundtrip as file_audit
import hancom_completion_gate as gate
import run_native_job as runner
import plan_grid_cell as grid
import visible_paragraphs as visibility
import pymupdf
P=sem.P

def need(ok,message):
    if not ok:raise ValueError(message)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,v):gate.write_new(Path(p),v)
def ref(p):return gate.ref(Path(p))
def tool_refs():
    return [ref(S/n) for n in ['native_measured_table_height.py','native_height_cli.py','Invoke-HancomNativeHeight.ps1','Hancom.NativeHeight.Worker.ps1','Hancom.RowSplit.Common.ps1','Hancom.Environment.ps1','plan_grid_cell.py','compare_active_semantics.py','compare_package_definitions.py','audit_native_file_roundtrip.py','run_native_job.py','visible_paragraphs.py']]

def inspect(source,ids):
    source=Path(source).resolve(strict=True);need(source.suffix.lower()=='.hwpx','existing HWPX required')
    need(version('python-hwpx')=='6.3.0','qualified public adapter requires6.3.0')
    need(isinstance(ids,list) and 1<=len(ids)<=2 and all(isinstance(x,str) and x for x in ids) and len(ids)==len(set(ids)),'explicit unique table IDs required')
    sections=oracle.sections(source);need(len(sections)==1,'one section required');part,root=sections[0];tables=list(root.iter(P+'tbl'));need(1<=len(tables)<=2,'one or two existing tables required')
    inventory=[t.get('id') for t in tables];need(all(inventory) and len(set(inventory))==len(inventory) and set(ids)<=set(inventory),'exact unambiguous table IDs required');rows=[]
    for identity in ids:
        ordinal=inventory.index(identity)+1;t=tables[ordinal-1];host=t.getparent().getparent();size=t.find(P+'sz');pos=t.find(P+'pos');margin=t.find(P+'outMargin')
        need(host.tag==P+'p' and host.getparent() is root,'root floating tables only')
        need(t.get('pageBreak') in ['CELL','TABLE'] and t.get('lock')==t.get('noAdjust')==size.get('protect')=='0' and pos.get('treatAsChar')=='0','unprotected floating CELL/TABLE required')
        need(size.get('heightRelTo')=='ABSOLUTE' and size.get('widthRelTo')=='ABSOLUTE','existing absolute table size required')
        plan=grid.plan(source,ordinal,int(t.get('rowCnt')),1);need(len(plan['actions'])<=20,'qualified cell route exceeds20moves')
        need(int(size.get('width'))>0 and 0<int(size.get('height'))<100000000,'positive bounded stored size required')
        rows.append(dict(tableId=identity,ordinal=ordinal,sizePath=list(adapter.location(size)),size=dict(size.attrib),outside=dict(margin.attrib),grid=plan))
    return dict(source=ref(source),part=part,sectionSha256=adapter.fingerprint(root),tableInventory=inventory,targets=rows,native='NOT_CALLED',qualifiedBuild='13, 0, 0, 3903')

def validate_measurement(source,d,expected,module_name):
    r=read(d/'job/receipt.json');plan=read(d/'grid-plan.json');job=read(d/'job/job.json');w=r.get('worker') or {};geometry=w.get('tableGeometry')
    need(r.get('status')=='PASS_COM' and r.get('sourceUnchanged') is True and not r.get('artifacts') and not r['cleanup']['remaining'] and not r['cleanup']['forced'],'owned read-only measurement did not complete')
    need(w.get('comCreated') is True and w.get('securityModuleRegistered') is True and w.get('registerModuleArguments')==['FilePathCheckDLL',module_name],'COM/module measurement binding failed')
    need(w.get('version')=='13, 0, 0, 3903' and not w['saveAs'] and not w['pdfExport'] and w['mutation'] is None and w['cleanup']['quit'],'measurement build or no-mutation contract failed')
    need(plan==expected['grid'] and plan['source']==ref(source) and job['input']==str(Path(source).resolve()) and job['sourceSha256'].lower()==ref(source)['sha256'],'measurement source/plan mismatch')
    need(geometry and geometry['tableId']==expected['tableId']==w['grid']['tableId'],'measurement target ID mismatch')
    seen=w['grid']['observations'];need(len(seen)==len(plan['route']),'incomplete cell route')
    for a,b in zip(plan['route'],seen):need(a['text']==b['text'] and a['row']==b['row'] and a['column']==b['column'],'cell route readback changed')
    values=[]
    for key in ['caret','selected']:
        need(len(geometry[key])==2,'two APIs required for each context')
        for row in geometry[key]:
            returned=row['getDefaultReturned'];need((returned is True or type(returned) is int and returned==1) and row['error'] is None and row['noExecuteOrSetItem'],'GetDefault did not explicitly succeed')
            data={v['name']:v for v in row['values']};wanted=['Height','LayoutHeight','Width','OutsideMarginTop','OutsideMarginBottom']
            for name in wanted:need(data[name]['status']=='READ_NUMERIC' and data[name]['numeric'] is True and type(data[name]['raw']) is int,'unconfirmed numeric measurement:'+name)
            values.append({name:data[name]['raw'] for name in wanted})
    v=values[0];need(all(x==v for x in values) and v['Height']==v['LayoutHeight'] and 0<v['Height']<100000000,'conflicting native height measurements')
    need(v['Width']==int(expected['size']['width']) and v['OutsideMarginTop']==int(expected['outside']['top']) and v['OutsideMarginBottom']==int(expected['outside']['bottom']),'native non-height geometry mismatch')
    return dict(tableId=expected['tableId'],source=ref(source),values=v,receipt=ref(d/'job/receipt.json'),grid=ref(d/'grid-plan.json'),job=ref(d/'job/job.json'),binding=ref(d/'binding.json'))

def measure(source,d,expected,context):
    metadata,ps=runner.dependencies();d.mkdir();write(d/'grid-plan.json',expected['grid']);write(d/'binding.json',dict(source=ref(source),tools=tool_refs(),desktop=metadata,context=context,contextIsCallerChoiceNotPermissionGrant=True))
    argv=[str(ps),'-NoProfile','-STA','-File',str(S/'Invoke-HancomNativeHeight.ps1'),'-Operation','InspectGrid','-InputPath',str(Path(source).resolve()),'-GridPlanPath',str(d/'grid-plan.json'),'-TargetText',expected['grid']['route'][0]['text'],'-RunDirectory',str(d/'job'),'-TimeoutSeconds','120']
    try:
        p=subprocess.run(argv,env=runner.environment_map(os.environ),capture_output=True,text=True,encoding='utf-8-sig',errors='replace',timeout=150);write(d/'command.json',dict(argv=argv,exitCode=p.returncode,stdout=p.stdout,stderr=p.stderr))
    except subprocess.TimeoutExpired:
        write(d/'timeout.json',dict(status='UNKNOWN_NATIVE_OUTCOME_NO_RETRY',automaticRetry=False));raise ValueError('native measurement controller timed out; preserve job and inspect owner before any retry')
    need(p.returncode==0,'native measurement blocked; preserve receipt and do not retry unchanged')
    for item in read(d/'binding.json')['tools']:gate.verify_ref(item)
    return validate_measurement(source,d,expected,metadata['moduleName'])

def apply(source,output,binding,proofs):
    source=Path(source).resolve(strict=True);output=Path(output).absolute();need(binding==inspect(source,[t['tableId'] for t in binding['targets']]),'stale public binding')
    need(not output.exists() and output.resolve()!=source and output.parent.is_dir(),'new private output required');need(len(proofs)==len(binding['targets']),'all selected measurements required');attrs={};changes=[]
    for target,proof in zip(binding['targets'],proofs):
        need(proof['source']==ref(source) and proof['tableId']==target['tableId'],'stale or different measurement')
        d=Path(proof['receipt']['path']).parent.parent
        for key in ['source','receipt','grid','job','binding']:gate.verify_ref(proof[key])
        bound=read(d/'binding.json');need(bound['source']==ref(source) and bound['tools']==tool_refs(),'measurement tool/source provenance changed')
        metadata,_=runner.dependencies();need(bound['desktop']==metadata,'measurement desktop changed')
        need(proof==validate_measurement(source,d,target,metadata['moduleName']),'measurement proof changed')
        height=proof['values']['Height'];old=int(target['size']['height'])
        if old!=height:attrs[binding['part'],tuple(target['sizePath'])]={'height':str(height)}
        changes.append(dict(tableId=target['tableId'],before=old,measured=height,changed=old!=height))
    expected=oracle.snapshot(source,attribute_overrides=attrs)
    if not attrs:shutil.copyfile(source,output);need(source.read_bytes()==output.read_bytes(),'unchanged byte-copy differs')
    else:
        with HwpxDocument.open(source) as doc:
            need(len(doc.sections)==1,'one public section required');section=doc.sections[0];need(adapter.fingerprint(section.element)==binding['sectionSha256'],'public source section mismatch')
            for (_,path),values in attrs.items():adapter.at(section.element,path).set('height',values['height'])
            section.mark_dirty();doc.save_to_path(output)
    need(expected==oracle.snapshot(output),'non-target package changed during measured-height preparation');gate.verify_ref(binding['source'])
    return dict(status='PASS_MEASURED_SELECTED_HEIGHT_ONLY' if attrs else 'UNCHANGED_MEASURED_HEIGHT_BYTE_COPY',source=ref(source),prepared=ref(output),changes=changes,
        allNonTargetPackageExact=True,noCacheClearing=True,noHeightExceptionInComparator=True,measurements=proofs)

def same_pixels(a,b):
    with pymupdf.open(a) as x,pymupdf.open(b) as y:return len(x)==len(y) and all((x[i].rect,x[i].get_pixmap().samples)==(y[i].rect,y[i].get_pixmap().samples) for i in range(len(x)))

def visible(source,pdfpaths):
    p=sem.Package(source);root=sem.parse(p.members[p.validated['sections'][0]]);ct=visibility.chrome(root,{key[1]:int(n.get('height'))/100 for key,n in p.defs.items() if key[0]=='charPr'});expected=[t for t in p.paragraph_texts() if visibility.norm(t)]
    rows=[dict(pdf=ref(path),result=visibility.assess(path,expected,ct)) for path in pdfpaths];need(all(x['result']['status']=='PASS_VISIBLE_TEXT' for x in rows),'visible content missing')
    return dict(status='PASS_VISIBLE_TEXT',rows=rows,scope='source text visibility only; manual review and order/style/internal checks remain separate')

def run(source,work,ids,context):
    need(context in ['ordinary-shell','host-approved'],'explicit caller context required');source=Path(source).resolve(strict=True);work=Path(work).absolute();binding=inspect(source,ids)
    need(not work.exists() and work.parent.is_dir(),'new work directory required');runner.dependencies();work.mkdir()
    tools=tool_refs();write(work/'plan.json',dict(schema='hwpx.native-measured-height.v1',binding=binding,tools=tools,context=context,noHeightExemption=True,settingsChanges=False));native=[]
    def native_job(src,mode,out,pdfpath,label):
        v=runner.run(src,mode,out,pdfpath,work/(label+'-job'),context);need(v['status']=='PASS_NATIVE','native stage failed:'+label)
        import native_write
        native.append(native_write.receipt_valid(work/(label+'-job'),src,out,pdfpath))
    try:
        proofs=[measure(source,work/('measurement-'+str(i+1)),target,context) for i,target in enumerate(binding['targets'])];write(work/'measurements.json',proofs)
        native_job(source,'OpenOnly',None,work/'source-before.pdf','source-before')
        prepared=work/'prepared.hwpx';write(work/'author.json',apply(source,prepared,binding,proofs))
        native_job(prepared,'OpenOnly',None,work/'before.pdf','before');native_job(prepared,'SaveAs',work/'saved.hwpx',work/'saved.pdf','saved');native_job(work/'saved.hwpx','SaveAs',work/'repeat.hwpx',work/'repeat.pdf','repeat')
        audits=[file_audit.audit(prepared,work/'saved.hwpx'),file_audit.audit(work/'saved.hwpx',work/'repeat.hwpx')];write(work/'file-audit.json',dict(rows=audits))
        need(all(x['strictActiveAndAllDefinitions']=='PASS' for x in audits),'strict active/ALL definitions changed; no height fallback')
        pdfs=[work/(s+'.pdf') for s in ['source-before','before','saved','repeat']];need(all(same_pixels(pdfs[0],p) for p in pdfs[1:]),'measured preparation or native saving changed actual layout');write(work/'visible-content.json',visible(source,pdfs))
        for r in tools:gate.verify_ref(r)
        gate.verify_ref(binding['source'])
        result=dict(status='READY_FOR_VISUAL_REVIEW',source=ref(source),prepared=ref(prepared),saved=ref(work/'saved.hwpx'),pdf=ref(work/'saved.pdf'),repeat=ref(work/'repeat.hwpx'),author=ref(work/'author.json'),audit=ref(work/'file-audit.json'),nativeReceipts=native,measurements=ref(work/'measurements.json'),allFourPdfPixelsEqual=True,
            strictActiveAndAllDefinitionsExact=True,noHeightExemption=True,rawDifferencesRetained=True,manualReview='NOT_REVIEWED',sameFeatureReedit='SEPARATE_NOT_CHECKED',publication=False,fullGoalCompletion=False)
    except (ValueError,KeyError,OSError,gate.GateError) as ex:
        result=dict(status='BLOCKED_NO_RETRY',error=str(ex),nativeReceipts=native,sourceUnchanged=ref(source)==binding['source'],automaticRetry=False,publication=False,fullGoalCompletion=False)
    write(work/'result.json',result);return result
