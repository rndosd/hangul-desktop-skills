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
    return dict(status='READY_LOCAL_TOOLS',skillRoot=str(ROOT),configuration=str(config),configurationExists=config.is_file(),python=sys.executable,hwpxModule=str(actual),parserSha256=sha(parser),commands=['doctor','schema new','schema table','replace','table','new'],writePermission='UNTESTED',native='NOT_CHECKED',securityModule='NOT_CHECKED')
def schema(operation):
    if operation=='new':
        return dict(schema=SCHEMA,operation='new',purpose='문서 목적',audience='독자',kind='보고서',title='제목',facts={'f1':'원자료의 정확한 문장'},numbered_headings=True,blocks=[dict(type='heading',level=1,text='적절한 큰 항목'),dict(type='heading',level=2,text='필요한 하위 항목'),dict(type='paragraph',facts=['f1']),dict(type='table',headers=['항목','내용'],rows=[['항목명','제공 내용']],reason='같은 속성을 비교한다.')],format={},review={'claims':'원자료 대조 결과를 작성한다.'})
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
def compile_new(request):
    keys(request,{'schema','operation','purpose','audience','kind','title','subtitle','facts','blocks','numbered_headings','format','review','allow_draft','unknowns'}, {'schema','operation','purpose','audience','kind','title','facts','blocks'})
    need(request['schema']==SCHEMA and request['operation']=='new','new 요청 schema/operation 불일치')
    facts=request['facts'];need(isinstance(facts,dict) and all(isinstance(k,str) and k and isinstance(v,str) and v.strip() for k,v in facts.items()),'facts는 원자료 id: 정확한 문장 객체')
    need(type(request.get('numbered_headings',False))is bool,'numbered_headings는 true/false')
    need(isinstance(request['blocks'],list) and 1<=len(request['blocks'])<=300,'블록은 1~300개')
    brief=dict(purpose=request['purpose'],audience=request['audience'],kind=request['kind'],facts={k:dict(text=v,required=True) for k,v in facts.items()},allow_draft=request.get('allow_draft',False),unknowns=request.get('unknowns',[]),requirements=[])
    blocks=[];claims=[]
    for i,item in enumerate(request['blocks']):
        need(isinstance(item,dict),'블록 객체 필요');typ=item.get('type');block=dict(id=f'b{i+1}',type=typ)
        if typ=='heading':
            keys(item,{'type','text','level'},{'type','text','level'});block.update(text=item['text'],level=item['level'])
        elif typ=='paragraph':
            keys(item,{'type','text','facts','emphasis','list','reason'},{'type'})
            need(('text'in item)!=('facts'in item),'문단은 text 또는 facts 중 하나')
            if 'facts'in item:
                refs=item['facts'];strings(refs);need(all(x in facts for x in refs),'알 수 없는 fact id')
                block.update(text=' '.join(facts[x]for x in refs),evidence=refs)
                claims.extend(dict(text=facts[x],evidence=[x])for x in refs)
            else: block['text']=item['text']
            for key in ['emphasis','list','reason']:
                if key in item: block[key]=item[key]
        elif typ=='table':
            keys(item,{'type','headers','rows','reason','widthWeights','aligns','caption'},{'type','headers','rows','reason'})
            headers=item['headers'];strings(headers);need(len(set(headers))==len(headers),'열 제목 중복')
            n=len(headers);weights=item.get('widthWeights',[1]*n);aligns=item.get('aligns',['left']*n)
            need(isinstance(weights,list) and isinstance(aligns,list) and len(weights)==len(aligns)==n,'열 너비/정렬 개수 불일치')
            need(isinstance(item['rows'],list) and bool(item['rows']),'비어 있지 않은 표 행 필요')
            rows=[]
            for row in item['rows']:
                strings(row);need(len(row)==n,'모든 열의 문자열 셀 값 필요');rows.append({f'c{x+1}':v for x,v in enumerate(row)})
            block.update(columns=[dict(key=f'c{x+1}',label=v,widthWeight=weights[x],align=aligns[x])for x,v in enumerate(headers)],rows=rows,reason=item['reason'])
            if 'caption'in item:block['caption']=item['caption']
        elif typ in ('bullets','page_break'):
            allowed={'type','items','ordered','reason'} if typ=='bullets'else{'type','reason'}
            keys(item,allowed,{'type','items'} if typ=='bullets'else{'type','reason'});block.update({k:v for k,v in item.items()if k!='type'})
        else: raise ValueError('heading/paragraph/table/bullets/page_break만 지원')
        blocks.append(block)
    fmt=dict(request.get('format',{}))
    if request.get('numbered_headings'):
        need('heading_numbering'not in fmt,'간편 번호 선택과 직접 번호 설정을 동시에 사용하지 마세요.')
        fmt['heading_numbering']=[dict(format=form,text=f'^{i}.',start=1)for i,form in enumerate(['DIGIT','HANGUL_SYLLABLE','LATIN_SMALL'],1)]
    plan=dict(schemaVersion='hwpx.document_plan.v1',title=request['title'],blocks=blocks)
    if 'subtitle'in request:plan['subtitle']=request['subtitle']
    design=dict(schema='hwpx.new_document.v1',plan=plan,coverage={},claims=claims,format=fmt,review=request.get('review',{}))
    return brief,design
def new(output,request,dry_run=False):
    activate()
    import create_new_document as guarded
    brief,design=compile_new(request);design=guarded.prepare_design(brief,design)
    validation=guarded.validate(brief,design)
    need(validation['ok'],'새 문서 입력 검사 실패: '+json.dumps(validation['mandatory_failures'],ensure_ascii=False))
    if dry_run:return dict(status='PASS_INPUT',documentPublished=False,brief=brief,design=design,validation=validation,native='NOT_CHECKED')
    result=guarded.create(brief,design,output)
    return dict(**result,documentPublished=True,validation=validation)
def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor');s=sub.add_parser('schema');s.add_argument('operation',choices=['new','table'])
    s=sub.add_parser('replace');s.add_argument('source');s.add_argument('output');s.add_argument('--find',required=True);s.add_argument('--replace',required=True)
    for cmd in ['table','new']:
        s=sub.add_parser(cmd)
        if cmd=='table':s.add_argument('source')
        s.add_argument('output');s.add_argument('--request',required=True);s.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    try:
        if a.command=='doctor':result=doctor()
        elif a.command=='schema':result=schema(a.operation)
        elif a.command=='replace':result=replace(a.source,a.output,a.find,a.replace)
        elif a.command=='table':result=table(a.source,a.output,read(a.request),a.dry_run)
        else:result=new(a.output,read(a.request),a.dry_run)
        if a.command!='schema':
            result.setdefault('native','NOT_CHECKED');result.setdefault('entryScript',str(Path(__file__).resolve()));result.setdefault('entrySha256',sha(__file__))
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except Exception as ex:
        print(json.dumps(dict(status='BLOCKED',reason=str(ex),errorType=type(ex).__name__,native='NOT_CHECKED',nextStep='입력과 대상 구조를 확인하세요. schema new/table 또는 references/simple-entry.md를 읽으세요.'),ensure_ascii=False));return 2
if __name__=='__main__':raise SystemExit(main())
