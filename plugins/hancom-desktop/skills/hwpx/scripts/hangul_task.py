"""Stable common task interface. Existing guarded engines remain authoritative."""
from pathlib import Path
import argparse, copy, hashlib, json, os, re, sys, runpy
from contextlib import contextmanager
from candidate_runtime import activate, identity

ROOT=Path(__file__).resolve().parents[1]
SCHEMA='hangul.task.v1'
def need(ok, reason):
    if not ok: raise ValueError(reason)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def keys(value, allowed, required=()):
    need(isinstance(value,dict) and set(required)<=set(value) and not set(value)-set(allowed), '지원 키: '+', '.join(sorted(allowed)))
def strings(values):
    need(isinstance(values,list) and bool(values) and all(isinstance(v,str) for v in values),'문자열 배열 필요')
@contextmanager
def stage_directory(parent):
    from workspace_candidate_directory import workspace_candidate_directory
    with workspace_candidate_directory(prefix='hangul-task-',dir=parent) as folder:
        try:yield folder
        finally:
            for i in range(20): (Path(folder)/f'stage-{i}.hwpx').unlink(missing_ok=True)
            (Path(folder)/'sections.hwpx').unlink(missing_ok=True)  # fill_sections pass 1
def doctor():
    config=ROOT/'environment.json'
    if not config.is_file(): config=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'skills/hwpx/environment.json'
    actual=activate();parser=actual.parent/'opc/xml_utils.py'
    return dict(status='READY_LOCAL_TOOLS',skillRoot=str(ROOT),configuration=str(config),configurationExists=config.is_file(),python=sys.executable,hwpxModule=str(actual),parserSha256=sha(parser),runtime=identity(),commands=['doctor','schema table','inspect','inspect-body','text-plan','text','layout','replace','table','source','source-check','batch','tool','compose','assemble','register','fill','preview'],writePermission='UNTESTED',native='NOT_CHECKED',securityModule='NOT_CHECKED')
def schema(operation):
    return dict(schema=SCHEMA,operation='table',headers=['열 제목1','열 제목2'],reason='사용자 메모의 완료 업무 삭제와 새 업무 추가',operations=[dict(op='delete',key={'열 제목1':'삭제할 셀의 완전한 문구'}),dict(op='insert_after',key={'열 제목1':'기준 셀의 완전한 문구'},cells=['새 항목명: 설명까지 전체','다른 열 값'],heightHwpunit=2400)])
def replace(source,output,old,new):
    activate()
    from safe_replace import replace as guarded
    return guarded(source,output,old,new)

def inspect_text(source, queries, output):
    from safe_edit import inspect_many, write_new_json
    from inspection_summary import text_summary
    result=inspect_many(source,queries)
    write_new_json(output,result)
    return text_summary(result,output)

def inspect_body(source, output, find=None):
    from safe_body_structure import inspect
    from safe_edit import write_new_json
    from inspection_summary import body_summary
    result=inspect(source)
    write_new_json(output,result)
    return body_summary(result,output,find)

def text_plan(inspections, changes, output):
    from safe_edit import combine_plans, write_new_json
    from inspection_summary import plan_summary
    result=combine_plans(inspections,changes)
    write_new_json(output,result)
    return plan_summary(result,output)

def _with_layout(source, output, layout, dry_run, edit, stage_name):
    """One private content/layout transaction, shared by text and batch."""
    from layout_task import apply_layout
    source, output = Path(source).resolve(strict=True), Path(output).absolute()
    need(output.suffix.lower()=='.hwpx' and source!=output.resolve() and not output.exists() and not output.is_symlink() and output.parent.is_dir(),'원본과 다른 새 .hwpx 출력 경로가 필요합니다.')
    original=sha(source)
    need(layout.get('expectedRevision')=='sha256:'+original,'stale layout revision')
    with stage_directory(output.parent) as temp:
        intermediate, candidate = Path(temp)/'stage-0.hwpx', Path(temp)/'stage-1.hwpx'
        edited=edit(intermediate)
        if not intermediate.is_file():
            # Keep the engine's precise failure/recovery evidence. A generic
            # wrapper error must not hide the unsupported command or revision.
            edited['output']={'filename':str(output)}
            edited['documentPublished']=False
            pipeline=edited.get('verificationReport',{}).get('savePipeline')
            if pipeline is not None:pipeline['outputPath']=None
            return edited
        adapted=apply_layout(intermediate,candidate,dict(layout,expectedRevision='sha256:'+sha(intermediate)),dry_run)
        adapted[stage_name]={'status':edited.get('status'),'layout_follow_up':edited.get('layout_follow_up',[])}
        adapted['sourceSha256']=original
        adapted['output']={'filename':str(output)}
        adapted['documentPublished']=False
        pipeline=adapted.get('verificationReport',{}).get('savePipeline')
        if pipeline is not None:pipeline['outputPath']=None
        need(sha(source)==original,'실행 중 원본 변경')
        if not dry_run and adapted.get('status')=='PASS_STRUCTURE':
            need(candidate.is_file() and sha(candidate)==adapted['outputSha256'],'검증된 후보와 출력 해시 불일치')
            os.link(candidate,output)
            adapted['documentPublished']=True
            if pipeline is not None:pipeline['outputPath']=str(output)
        return adapted

def text(source, output, plan, dry_run=False, layout=None):
    activate()
    from safe_edit import apply_plan
    if layout is not None:
        return _with_layout(source,output,layout,dry_run,lambda target:apply_plan(source,target,plan,dry_run=False),'textStage')
    return apply_plan(source,output,plan,dry_run=dry_run)

def batch(request,dry_run=False,layout=None):
    """Apply a revision-bound public batch with the selected preservation runtime."""
    actual=activate()
    from hwpx_automation.office.agent import apply_document_commands,validate_agent_batch
    plan=validate_agent_batch(request)
    need(plan['expectedRevision'] is not None,'원본 revision이 필요합니다.')
    need(plan['output']['overwrite'] is False,'기존 출력 덮어쓰기는 지원하지 않습니다.')
    if layout is not None:
        return _with_layout(plan['input']['filename'],plan['output']['filename'],layout,dry_run or plan['dryRun'],lambda target:batch(dict(request,output={'filename':str(target),'overwrite':False},dryRun=False)),'contentStage')
    source=Path(plan['input']['filename']).resolve(strict=True)
    output=Path(plan['output']['filename']).absolute()
    need(output.suffix.lower()=='.hwpx' and source!=output.resolve() and not output.exists() and not output.is_symlink() and output.parent.is_dir(),'원본과 다른 새 .hwpx 출력 경로가 필요합니다.')
    original=sha(source)
    with stage_directory(output.parent) as temp:
        candidate=Path(temp)/'candidate.hwpx'
        staged=dict(request,input={'filename':str(source)},output={'filename':str(candidate),'overwrite':False},dryRun=dry_run or plan['dryRun'])
        result=apply_document_commands(staged).to_dict()
        result['output']={'filename':str(output)}
        result['documentPublished']=False
        pipeline=result['verificationReport'].get('savePipeline')
        if pipeline is not None:pipeline['outputPath']=None
        if result['ok']:
            need(sha(source)==original,'실행 중 원본 변경')
            if not result['dryRun']:
                output_hash=sha(candidate)
                need(result['documentRevision']=='sha256:'+output_hash,'검증된 후보와 출력 해시 불일치')
                os.link(candidate,output)
                result['outputSha256']=output_hash
                result['documentPublished']=True
                if pipeline is not None:pipeline['outputPath']=str(output)
    result['status']='PASS_STRUCTURE' if result['ok'] else 'BLOCKED'
    result['runtime']={'module':str(actual),'parserSha256':sha(actual.parent/'opc/xml_utils.py'),'shared':identity()}
    return result
def table(source,output,request,dry_run=False):
    keys(request,{'schema','operation','headers','reason','operations'},{'schema','operation','headers','reason','operations'})
    need(request['schema']==SCHEMA and request['operation']=='table','table 요청 schema/operation 불일치')
    strings(request['headers']);need(isinstance(request['reason'],str) and len(request['reason'])>=8,'구체적인 편집 이유 필요')
    operations=request['operations'];need(isinstance(operations,list) and 1<=len(operations)<=20,'연산은 1~20개')
    source=Path(source).resolve(strict=True);output=Path(output).absolute()
    need(output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and not output.is_symlink() and source!=output.resolve(),'다른 새 .hwpx 출력 경로 필요')
    activate()
    import safe_mixed_table_structure as guarded
    return guarded.apply_sequence(source,output,request['headers'],operations,request['reason'],dry_run)
def run_tool(name, arguments):
    need(Path(name).name==name and name.endswith('.py') and '/' not in name and '\\' not in name, 'installed helper filename required')
    target=Path(__file__).parent/name
    need(target.is_file() and target.resolve().parent==Path(__file__).resolve().parent and name not in ('hangul_task.py','candidate_runtime.py'), 'existing helper in this skill required')
    activate()
    previous=sys.argv
    try:
        sys.argv=[str(target),*arguments]
        runpy.run_path(str(target),run_name='__main__')
    finally:sys.argv=previous
    return 0

def compose(request, output, pdf, run_dir, context, timeout=120):
    native_scripts=ROOT.parent/'hwpx-windows-finalize/scripts'
    need((native_scripts/'compose_native.py').is_file(), 'paired native composition helper required')
    sys.path.insert(0,str(native_scripts))
    from compose_native import compose as native_compose
    return native_compose(request,output,pdf,run_dir,context,timeout)

TITLE_KINDS=('chapter','heading','task','subhead')
def _titles_left_above_tables(outline, pdf):
    """Outline indexes of titles followed by a table whose text is the last line of a page that is not the last.

    A table that splits across pages floats with the text, so the title's keep-with-next holds only the table's
    anchor line; when no table row fits below the title, the title stays alone at the page end."""
    import pymupdf
    nodes=outline.get('nodes',[])
    titles=[i for i,n in enumerate(nodes[:-1]) if n.get('t') in TITLE_KINDS and nodes[i+1].get('t')=='table' and not nodes[i].get('pageBreakBefore')]
    if not titles:return []
    flat=lambda s:re.sub(r'\s+','',s)
    ends=[]
    with pymupdf.open(pdf) as document:
        for page in list(document)[:-1]:
            limit=page.rect.height*0.92  # above the page number
            lines=[(l['bbox'][1],''.join(s['text'] for s in l['spans'])) for b in page.get_text('dict')['blocks'] for l in b.get('lines',[]) if l['bbox'][3]<limit]
            lines=[t for y,t in sorted(lines) if t.strip()]
            if lines:ends.append(flat(''.join(lines[-2:])))
    stranded=[]
    for i in titles:
        if any(flat(nodes[i]['text'])[:12] in end for end in ends):
            while i and nodes[i-1].get('t') in TITLE_KINDS:i-=1  # a chapter right above the title goes with it
            stranded.append(i)
    return stranded

def assemble(template, outline, output, pdf, run_dir, context, catalog=None, timeout=240):
    """Outline -> parts of one assembly template, assembled in one owned Hangul job."""
    native_scripts=ROOT.parent/'hwpx-windows-finalize/scripts'
    need((native_scripts/'native_assembly.py').is_file(), 'paired native assembly helper required')
    sys.path.insert(0,str(native_scripts))
    from native_assembly import load_template, build_plan, check_output, describe
    if outline is None:  # --describe: what an outline can use on this template, no Hangul
        return dict(status='DESCRIBED',template=describe(load_template(catalog or ROOT/'assets/document-templates/assembly',template)))
    from run_native_job import run
    from wrap_alignment import measure
    from page_layout import measure as page_layout
    manifest=load_template(catalog or ROOT/'assets/document-templates/assembly',template)
    tables=Path(run_dir).with_name(Path(run_dir).name+'-tables')  # table copies; the run folder itself must be new
    need(not tables.exists(),f'already exists: {tables}')
    notes=[]
    plan=build_plan(manifest,outline,tables,notes)
    result=run(plan['base']['path'],'SaveAs',output,pdf,run_dir,context,timeout,composition=plan)
    stranded=_titles_left_above_tables(outline,pdf) if result['status']=='PASS_NATIVE' else []
    if stranded:  # a title ended a page and its table began the next: start those titles on the next page, once
        retry=Path(run_dir).with_name(Path(run_dir).name+'-retry')
        need(not retry.exists() and not retry.with_name(retry.name+'-tables').exists(),f'already exists: {retry}')
        retry.mkdir()
        moved=copy.deepcopy(outline)
        for index in stranded:moved['nodes'][index]['pageBreakBefore']=True
        notes=[]
        plan=build_plan(manifest,moved,retry.with_name(retry.name+'-tables'),notes)
        again=Path(retry)/'out'
        result=run(plan['base']['path'],'SaveAs',retry/Path(output).name,retry/Path(pdf).name,again,context,timeout,composition=plan)
        if result['status']=='PASS_NATIVE':
            os.replace(retry/Path(output).name,output);os.replace(retry/Path(pdf).name,pdf)
        result['titlesMovedToNextPage']=[outline['nodes'][i]['text'] for i in stranded]
    result['template']=dict(id=manifest['id'],label=manifest['label'],source=manifest['source'].get('attribution'))
    result['substitutions']=[n for n in notes if n['role']!='block']  # roles, tables and cover fields drawn with a substitute
    result['blocks']=[n for n in notes if n['role']=='block']  # parts that went in with their source wording, to review
    if result['status']=='PASS_NATIVE':
        receipt=json.loads(Path(result['receiptPath']).read_text(encoding='utf-8-sig'))
        result['pages']=receipt.get('pageCountAfter')
        result['assembly']=check_output(output,plan)
        if not result['assembly']['ok']:result['status']='FAIL_ASSEMBLY_TEXT'
        result['wrapAlignment']=measure(pdf)
        result['pageLayout']=page_layout(pdf)
    return result

def register(source, template_id, out):
    """Register a user's plan as an assembly template (propose, build, self reproduction, other lengths) and report
    only what the person decides on: the preview, what an outline can use, and source wording left in blocks."""
    import subprocess
    need(re.fullmatch(r'[a-z0-9][a-z0-9-]{1,40}',template_id),'--id: 소문자·숫자·- 2~41자')
    work=Path(out).resolve()
    need(not work.exists(),f'already exists: {work}')
    done=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).with_name('register_assembly_template.py')),str(Path(source).resolve(strict=True)),str(work),'--id',template_id],
                        capture_output=True,text=True,encoding='utf-8',errors='replace')
    need((work/'report.json').is_file(),'registration stopped: '+(done.stderr.strip().splitlines() or ['no report'])[-1])
    report=read(work/'report.json')
    if report.get('status')=='FAIL_BUILD':
        return dict(status='FAIL_BUILD',part=report.get('part'),reason=report.get('error'),work=str(work))
    native_scripts=ROOT.parent/'hwpx-windows-finalize/scripts'
    sys.path.insert(0,str(native_scripts))
    from native_assembly import load_template, describe
    catalog=Path(report['catalog'])
    blocks=[b for b in report.get('toReview',{}).get('blocks',[]) if b['texts']]
    info=describe(load_template(catalog,template_id))
    return dict(status='REGISTERED' if report['status']=='PASS' else 'REVIEW',template=template_id,catalog=str(catalog),
                use=f'assemble --template {template_id} --catalog "{catalog}"',
                preview=str(work/'repro.pdf'),sourcePdf=str(work/'source.pdf'),
                canUse=dict(roles=list(info['roles'].values()),tables=[dict(part=t['part'],role=t['role'],columns=t.get('columns') or t['header'],repeat=t['repeat']) for t in info['tables']],
                            cover=info['cover']['fields']),
                problems=report.get('check1',{}).get('problems',[])+[f'{name}: {v.get("error") or v.get("status")}' for name,v in report.get('check2',{}).items() if not v.get('ok')],
                # parts kept as the source has them: an outline names them only to reuse that wording (a fixed notice)
                sourceWording=dict(blocks=len(blocks),examples=[b['texts'][0] for b in blocks[:5]]),
                report=str(work/'report.json'))

def preview(pdf, output):
    native_scripts=ROOT.parent/'hwpx-windows-finalize/scripts'
    need((native_scripts/'hancom_completion_gate.py').is_file(),'paired native preview helper required')
    sys.path.insert(0,str(native_scripts))
    from hancom_completion_gate import preview_pdf
    from wrap_alignment import measure
    from page_layout import measure as page_layout
    result=preview_pdf(pdf,output)
    result['wrapAlignment']=measure(pdf)
    result['pageLayout']=page_layout(pdf)
    return result

def layout_check(source, pdf=None):
    """Common layout rules: structure from the HWPX, wrapped-line positions from its Hangul PDF."""
    from layout_rules import check
    result=dict(check(source),source=str(Path(source).resolve()),sourceSha256=sha(source))
    if pdf:
        native_scripts=ROOT.parent/'hwpx-windows-finalize/scripts'
        sys.path.insert(0,str(native_scripts))
        from wrap_alignment import measure
        from page_layout import measure as page_layout
        result['wrapAlignment']=measure(pdf)
        result['pageLayout']=page_layout(pdf)
        if result['wrapAlignment']['warnings'] or result['pageLayout']['warnings']:result['status']='WARN'
    return result

def _layout_rules_after_fill(result):
    """Fill publishes regardless; layout findings are warnings for the review, never a block."""
    output=result.get('output',{}).get('filename')
    if not output or not result.get('documentPublished') or not Path(output).is_file():return result
    try:
        from layout_rules import check
        report=check(output)
        result['layoutRules']={key:report[key] for key in ('status','checkedParagraphs','warnings')}
    except Exception as ex:
        result['layoutRules']={'status':'NOT_CHECKED','reason':f'{type(ex).__name__}: {ex}'}
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor');s=sub.add_parser('schema');s.add_argument('operation',choices=['table'])
    s=sub.add_parser('tool');s.add_argument('script');s.add_argument('arguments',nargs=argparse.REMAINDER)
    s=sub.add_parser('compose');s.add_argument('--request',required=True);s.add_argument('--output',required=True);s.add_argument('--pdf',required=True);s.add_argument('--run',required=True);s.add_argument('--context',choices=['ordinary-shell','host-approved'],required=True);s.add_argument('--timeout',type=int,default=120)
    s=sub.add_parser('register');s.add_argument('source');s.add_argument('--id',required=True);s.add_argument('--out',required=True)
    s=sub.add_parser('assemble');s.add_argument('--template',required=True);s.add_argument('--describe',action='store_true');s.add_argument('--outline');s.add_argument('--output');s.add_argument('--pdf');s.add_argument('--run');s.add_argument('--context',choices=['ordinary-shell','host-approved']);s.add_argument('--catalog');s.add_argument('--timeout',type=int,default=240)
    s=sub.add_parser('fill');s.add_argument('--template');s.add_argument('--values');s.add_argument('--content');s.add_argument('--output');s.add_argument('--styles');s.add_argument('--catalog',default=str(ROOT/'assets/document-templates/full-plans.json'));s.add_argument('--dry-run',action='store_true')
    s=sub.add_parser('preview');s.add_argument('pdf');s.add_argument('--output',required=True)
    s=sub.add_parser('layout-check');s.add_argument('source');s.add_argument('--pdf')
    s=sub.add_parser('replace');s.add_argument('source');s.add_argument('output');s.add_argument('--find',required=True);s.add_argument('--replace',required=True)
    s=sub.add_parser('source');s.add_argument('source');s.add_argument('--cache',required=True)
    s=sub.add_parser('source-check');s.add_argument('source');s.add_argument('--analysis',required=True)
    s=sub.add_parser('batch');s.add_argument('--request',required=True);s.add_argument('--layout');s.add_argument('--dry-run',action='store_true')
    s=sub.add_parser('inspect');s.add_argument('source');s.add_argument('--queries',required=True);s.add_argument('--output',required=True)
    s=sub.add_parser('inspect-body');s.add_argument('source');s.add_argument('--output',required=True);s.add_argument('--find')
    s=sub.add_parser('text-plan');s.add_argument('--inspection',required=True);s.add_argument('--changes',required=True);s.add_argument('--output',required=True)
    s=sub.add_parser('text');s.add_argument('source');s.add_argument('output');s.add_argument('--plan',required=True);s.add_argument('--layout');s.add_argument('--dry-run',action='store_true')
    s=sub.add_parser('layout');s.add_argument('source');s.add_argument('output');s.add_argument('--request',required=True);s.add_argument('--dry-run',action='store_true')
    for cmd in ['table']:
        s=sub.add_parser(cmd)
        if cmd=='table':s.add_argument('source')
        s.add_argument('output');s.add_argument('--request',required=True);s.add_argument('--dry-run',action='store_true')
    for name in ('text','batch','layout','table','replace','fill'):
        sub.choices[name].add_argument('--full-output', action='store_true', help='Print the legacy complete JSON instead of a saved receipt summary.')
    a=p.parse_args()
    try:
        if a.command=='tool':return run_tool(a.script,a.arguments)
        if a.command=='doctor':result=doctor()
        elif a.command=='compose':result=compose(read(a.request),a.output,a.pdf,a.run,a.context,a.timeout)
        elif a.command=='assemble':
            if a.describe:result=assemble(a.template,None,None,None,None,None,a.catalog)
            else:
                need(all([a.outline,a.output,a.pdf,a.run,a.context]),'assemble needs --outline --output --pdf --run --context (or --describe)')
                result=assemble(a.template,read(a.outline),a.output,a.pdf,a.run,a.context,a.catalog,a.timeout)
        elif a.command=='register':result=register(a.source,a.id,a.out)
        elif a.command=='schema':result=schema(a.operation)
        elif a.command=='preview':result=preview(a.pdf,a.output)
        elif a.command=='layout-check':result=layout_check(a.source,a.pdf)
        elif a.command=='fill':
            from fill_template import describe,fill
            if a.content:
                need(not a.values,'--content supplies values; do not also pass --values')
                content=read(a.content)
                if a.template:
                    need(isinstance(content,dict) and content.get('template',a.template)==a.template,'conflicting content/template selection')
                    content=dict(content,template=a.template)
                from select_document_block import BlockLibrary
                routing=BlockLibrary(Path(a.catalog)).match_content(content)
                selected=routing['selected']
                if not selected:
                    result=dict(routing,status='BLOCKED',reason='CONTENT_CHOICE_REQUIRED' if routing['candidates'] else 'CONTENT_NO_MATCH',documentPublished=False)
                elif not a.output:
                    need(not a.styles and not a.dry_run,'content preview needs no styles/dry-run')
                    result=routing
                else:
                    result=_layout_rules_after_fill(fill(a.catalog,selected['template'],a.output,selected['values'],styles=read(a.styles) if a.styles else None,dry_run=a.dry_run))
                    result['contentSelection']={key:selected[key] for key in ('template','layout','repeat','fields','unfilledFields')}
            elif a.values:
                need(bool(a.template),'fill --values requires --template')
                need(bool(a.output),'fill --values requires --output')
                result=_layout_rules_after_fill(fill(a.catalog,a.template,a.output,read(a.values),styles=read(a.styles) if a.styles else None,dry_run=a.dry_run))
            else:
                need(bool(a.template),'fill requires --template or --content')
                need(not a.output and not a.styles and not a.dry_run,'describe needs only --template and optional --catalog')
                result=describe(a.catalog,a.template)
        elif a.command=='replace':result=replace(a.source,a.output,a.find,a.replace)
        elif a.command=='table':result=table(a.source,a.output,read(a.request),a.dry_run)
        elif a.command=='batch':result=batch(read(a.request),a.dry_run,read(a.layout) if a.layout else None)
        elif a.command=='inspect':result=inspect_text(a.source,read(a.queries),a.output)
        elif a.command=='inspect-body':result=inspect_body(a.source,a.output,a.find)
        elif a.command=='text-plan':result=text_plan(read(a.inspection),read(a.changes),a.output)
        elif a.command=='text':result=text(a.source,a.output,read(a.plan),a.dry_run,read(a.layout) if a.layout else None)
        elif a.command=='layout':
            from layout_task import apply_layout
            result=apply_layout(a.source,a.output,read(a.request),a.dry_run)
        elif a.command=='source':
            from prepare_source import prepare_source
            result=prepare_source(a.source,a.cache)
        elif a.command=='source-check':
            from prepare_source import check_source
            result=check_source(a.source,a.analysis)
        if a.command!='schema':
            result.setdefault('native',result.get('status') if a.command in ('compose','assemble','register') and result.get('status')!='DESCRIBED' else 'NOT_CHECKED');result.setdefault('entryScript',str(Path(__file__).resolve()));result.setdefault('entrySha256',sha(__file__))
        displayed=result
        if a.command in ('text','batch','layout','table','replace','fill') and not a.full_output and (a.command!='fill' or a.values or (a.content and result.get('ok') is not None)):
            from inspection_summary import saved_edit_summary
            output=getattr(a,'output',None) or result.get('output',{}).get('filename')
            displayed=saved_edit_summary(result,output)
            if 'contentSelection' in result:displayed['contentSelection']=result['contentSelection']
        print(json.dumps(displayed,ensure_ascii=False,indent=2));return (0 if result.get('status') in ('PASS_NATIVE','DESCRIBED') else 3) if a.command in ('compose','assemble') else (2 if result.get('status') in ('STALE','BLOCKED') else 0)
    except Exception as ex:
        print(json.dumps(dict(status='BLOCKED',reason=str(ex),errorType=type(ex).__name__,native='NOT_CHECKED',nextStep='reason에 해당하는 입력·지원 범위를 references/simple-entry.md에서 확인하세요. 보존·revision 실패는 중단하고 같은 요청을 자동 재시도하지 마세요.'),ensure_ascii=False));return 2
if __name__=='__main__':raise SystemExit(main())
