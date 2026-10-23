"""Stable common task interface. Existing guarded engines remain authoritative."""
from pathlib import Path
import argparse, hashlib, json, os, sys
from contextlib import contextmanager
from candidate_runtime import activate

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
def doctor():
    config=ROOT/'environment.json'
    if not config.is_file(): config=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'skills/hwpx/environment.json'
    actual=activate();parser=actual.parent/'opc/xml_utils.py'
    return dict(status='READY_LOCAL_TOOLS',skillRoot=str(ROOT),configuration=str(config),configurationExists=config.is_file(),python=sys.executable,hwpxModule=str(actual),parserSha256=sha(parser),commands=['doctor','schema table','replace','table'],writePermission='UNTESTED',native='NOT_CHECKED',securityModule='NOT_CHECKED')
def schema(operation):
    return dict(schema=SCHEMA,operation='table',headers=['열 제목1','열 제목2'],reason='사용자 메모의 완료 업무 삭제와 새 업무 추가',operations=[dict(op='delete',key={'열 제목1':'삭제할 셀의 완전한 문구'}),dict(op='insert_after',key={'열 제목1':'기준 셀의 완전한 문구'},cells=['새 항목명: 설명까지 전체','다른 열 값'],heightHwpunit=2400)])
def replace(source,output,old,new):
    activate()
    from safe_replace import replace as guarded
    return guarded(source,output,old,new)
def table(source,output,request,dry_run=False):
    keys(request,{'schema','operation','headers','reason','operations'},{'schema','operation','headers','reason','operations'})
    need(request['schema']==SCHEMA and request['operation']=='table','table 요청 schema/operation 불일치')
    strings(request['headers']);need(isinstance(request['reason'],str) and len(request['reason'])>=8,'구체적인 편집 이유 필요')
    operations=request['operations'];need(isinstance(operations,list) and 1<=len(operations)<=20,'연산은 1~20개')
    source=Path(source).resolve(strict=True);output=Path(output).absolute()
    need(output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and not output.is_symlink() and source!=output.resolve(),'다른 새 .hwpx 출력 경로 필요')
    activate()
    import semantic_table_binding as binding
    import safe_mixed_table_structure as guarded
    original=sha(source);stages=[]
    # All stages are private. One final publication only after every guard passes.
    with stage_directory(output.parent) as temp:
        current=source
        for i,op in enumerate(operations):
            need(isinstance(op,dict),'연산 객체 필요')
            kind=op.get('op');need(kind in ('delete','insert_after'),'delete/insert_after만 지원')
            keys(op,{'op','key'} if kind=='delete' else {'op','key','cells','heightHwpunit'}, {'op','key'} if kind=='delete' else {'op','key','cells','heightHwpunit'})
            target=binding.bind(current,request['headers'],op['key'])
            parameters={}
            if kind=='insert_after':
                strings(op['cells']);need(len(op['cells'])==len(request['headers']),'모든 열의 완전한 셀 값 필요. 항목명과 설명을 함께 보존하세요.')
                need(all(len(m)==1 and len(m[0]['runs'])==1 for m in target['models']),'간편 삽입은 모든 기준 셀이 한 문단/한 run일 때만 지원. 상세 경로에서 전체 run 지도를 검토하세요.')
                parameters=dict(cells=[[[v]] for v in op['cells']],heightHwpunit=op['heightHwpunit'])
            q=binding.row_request(current,target,'delete_row'if kind=='delete'else'clone_after',parameters,request['reason'])
            destination=Path(temp)/f'stage-{i}.hwpx'
            preflight=guarded.apply(current,destination,q,True)
            need(preflight['status']=='PASS_MIXED_TABLE_PRESERVATION','표 보존 검사 실패')
            result=guarded.apply(current,destination,q,False)
            need(result['status']=='PASS_MIXED_TABLE_PRESERVATION','표 보존 검사 실패')
            stages.append(dict(operation=op,binding=q,checks=result));current=destination
        need(sha(source)==original,'실행 중 원본 변경')
        output_hash=sha(current)
        if not dry_run:
            with output.open('xb') as f: f.write(current.read_bytes())
    return dict(status='PASS_STRUCTURE',dryRun=dry_run,documentPublished=not dry_run,sourceSha256=original,outputSha256=output_hash,stages=stages,native='NOT_CHECKED')
def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor');s=sub.add_parser('schema');s.add_argument('operation',choices=['table'])
    s=sub.add_parser('replace');s.add_argument('source');s.add_argument('output');s.add_argument('--find',required=True);s.add_argument('--replace',required=True)
    for cmd in ['table']:
        s=sub.add_parser(cmd)
        if cmd=='table':s.add_argument('source')
        s.add_argument('output');s.add_argument('--request',required=True);s.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    try:
        if a.command=='doctor':result=doctor()
        elif a.command=='schema':result=schema(a.operation)
        elif a.command=='replace':result=replace(a.source,a.output,a.find,a.replace)
        elif a.command=='table':result=table(a.source,a.output,read(a.request),a.dry_run)
        if a.command!='schema':
            result.setdefault('native','NOT_CHECKED');result.setdefault('entryScript',str(Path(__file__).resolve()));result.setdefault('entrySha256',sha(__file__))
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except Exception as ex:
        print(json.dumps(dict(status='BLOCKED',reason=str(ex),errorType=type(ex).__name__,native='NOT_CHECKED',nextStep='입력과 대상 구조를 확인하세요. schema table 또는 references/simple-entry.md를 읽으세요.'),ensure_ascii=False));return 2
if __name__=='__main__':raise SystemExit(main())
