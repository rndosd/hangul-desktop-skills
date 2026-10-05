import sys,json,pathlib,hashlib,zipfile,xml.etree.ElementTree as ET,argparse
S=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(S))
from hwpx import HwpxDocument
import create_new_document as e
import safe_edit as se
import form_fill as ff

def dump(path,obj):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():raise FileExistsError(path)
 path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def build(root,format_path=None):
 root=pathlib.Path(root);root.mkdir(parents=True,exist_ok=True)
 B=[]
 def add(kind,**kw):B.append(dict(id=f'b{len(B)}',type=kind,**kw))
 def h(level,text):add('heading',level=level,text=text)
 def p(text):add('paragraph',text=text)
 def table(cap,headers,rows):
  keys=[f'c{i}' for i in range(len(headers))];add('table',caption=cap,columns=[dict(key=k,label=v,widthWeight=1 if i==0 else 3) for i,(k,v) in enumerate(zip(keys,headers))],rows=[dict(zip(keys,r)) for r in rows],reason='문구와 비대상 서식 보존 시험')
 p('기존 보고서에서 필요한 내용만 수정하는 시험 문서다. 아래 내용은 업무 편집 검증을 위한 가상 예시이며 실제 조사 결과가 아니다.')
 h(1,'추진 계획');h(2,'운영 방향');h(3,'자료 준비')
 p('부서별로 자료를 검토한 뒤 다음 회의에서 운영안을 확정한다.')
 p('문구 교체 위치: 현장 점검을 완료한 뒤 결과를 공유한다.')
 p('검토 중 불필요한 임시 안내를 삭제하고 핵심 설명을 유지한다.')
 p('확인 필요: 일정은 담당자와 다시 협의한다.')
 p('확인 필요: 예산은 승인 절차를 따른다.')
 p('보존 문장: 작업 담당자와 검토자는 결과 및 변경 이력을 함께 확인한다.')
 add('page_break',reason='본문과 표의 편집 결과를 독립적으로 검토')
 h(1,'표 내용 검토');h(2,'진행 상태')
 table('업무 진행표',['업무','진행 상태'],[['자료 수집','확인 대기'],['현장 점검','확인 대기'],['보고서 정리','수정 전 안내']])
 h(2,'병합 영역과 결재란');p('병합 영역의 설명만 바꾸고 셀 경계·결재란·비대상 문구를 보존한다.')
 p('병합표 위치');p('결재표 위치')
 add('page_break',reason='기존 빈 양식의 라벨 및 반복 항목 시험')
 h(1,'운영 기록 양식');h(2,'기록 항목')
 table('기존 기록 양식',['구분','내용'],[['사업명',''],['추진목적',''],['활동',''],['활동','']])
 p('보존 안내: 반복 활동은 위에서 아래 순서로 입력하고, 빈 칸의 글자·문단 서식과 셀 여백을 유지한다.')
 brief=dict(request='자주 쓰는 기존 보고서 편집 기능 시험',purpose='대상 변경과 비대상 보존 검증',audience='문서 편집 담당자',kind='편집 시험',allow_draft=True,facts={},requirements=[dict(id='common',description='자주 쓰는 편집 시험',must_include=['추진 계획','운영 기록 양식'])],unknowns=[])
 format_path=pathlib.Path(format_path) if format_path else S.parent/'references'/'common-edit-fixture-format.json'
 fmt=json.loads(format_path.read_text(encoding='utf-8-sig'))['format']
 design=dict(schema='hwpx.new_document.v1',plan=dict(schemaVersion='hwpx.document_plan.v1',title='업무 보고서 편집 시험',subtitle='',blocks=B),coverage={'common':[b['id'] for b in B]},claims=[],format=fmt,review={'content':'합성 사례','native':'pending'})
 design=e.prepare_design(brief,design);e.create(brief,design,root/'fixture-base.hwpx')
 d=HwpxDocument.open(root/'fixture-base.hwpx')
 for i,para in enumerate(d.paragraphs):
  if para.text=='문구 교체 위치: 현장 점검을 완료한 뒤 결과를 공유한다.':
   para.text='문구 교체 위치: ';para.add_run('현장 ',bold=True);para.add_run('점검',italic=True);para.add_run('을 완료한 뒤 결과를 공유한다.')
  if para.text=='병합표 위치':
   para.text='';t=para.add_table(2,3,width=round(161*7200/25.4));t.merge_cells(0,0,1,1)
   t.cell(0,0).set_text('병합 설명: 참여자는 접수 후 안내를 받는다.');t.cell(0,2).set_text('보존 오른쪽 위');t.cell(1,2).set_text('보존 오른쪽 아래')
  if para.text=='결재표 위치':
   para.text='';t=para.add_table(2,3,width=round(161*7200/25.4))
   for r,row in enumerate([['담당','검토','승인'],['보존 담당란','보존 검토란','보존 승인란']]):
    for c,v in enumerate(row):t.cell(r,c).set_text(v)
  if para.text and para.text not in {b.get('text') for b in B if b['type']=='heading'} and para.text not in [design['plan']['title'],B[0]['text']]:
   d.styles.apply_paragraph_format(paragraph_index=i,indent_left_mm=9,first_line_indent_mm=0)
 # Create two existing empty paragraphs in the purpose slot, before native baseline save.
 for t in d.tables:
  if t.cell(0,0).text=='구분':
   if t.cell(1,0).text=='사업명':t.cell(2,1).add_paragraph('')
 report=d.validate();assert report.ok,[str(x) for x in report.errors]
 path=root/'fixture.hwpx';assert not path.exists();d.save_to_path(path);d.close()
 dump(root/'fixture.json',dict(sha256=sha(path),validation=dict(ok=report.ok,errors=[str(x) for x in report.errors]),synthetic=True))
 print('FIXTURE_CREATED',path)

def edit(source,root):
 source=pathlib.Path(source).resolve();root=pathlib.Path(root);root.mkdir(parents=True,exist_ok=True);before=sha(source)
 specs=[('부서별로 자료를 검토한 뒤 다음 회의에서 운영안을 확정한다.','부서별 자료와 현장 의견을 함께 검토하고, 남은 확인 사항을 정리한 뒤 다음 회의에서 운영안을 확정한다.',dict(kind='body',prefix='부서별로')),
 ('현장 점검','현장 운영 점검',dict(kind='body',prefix='문구 교체 위치:')),
 ('불필요한 임시 안내를 ','',dict(kind='body',prefix='검토 중')),
 ('확인 필요','협의 예정',dict(kind='body',prefix='확인 필요: 일정')),
 ('확인 대기','점검 완료',dict(kind='cell',table=1,row=3,column=2)),
 ('수정 전 안내','공유 자료를 정리하고 검토 의견을 반영한 뒤 최종본을 제출한다.',dict(kind='cell',table=1,row=4,column=2)),
 ('참여자는 접수 후 안내를 받는다.','참여자는 접수 내용을 확인한 뒤 현장 안내에 따라 이동한다.',dict(kind='cell',table=2,row=1,column=1))]
 plan=dict(schema=se.SCHEMA,source_sha256=before,style_policy=se.POLICY,edits=[]);selections=[]
 for find,repl,wanted in specs:
  kw={k:wanted[k] for k in ['table','row','column'] if k in wanted}
  ins=se.inspect_targets(source,find,**kw)
  targets=[t for t in ins['targets'] if t['scope']['kind']==wanted['kind'] and t.get('supported') and (not wanted.get('prefix') or t['context'].startswith(wanted['prefix']))]
  if len(targets)!=1:raise ValueError(('target_count',find,targets,ins))
  target=targets[0];part=se.make_plan(ins,[target['target_id']],repl);plan['edits']+=part['edits'];selections.append(target)
 dump(root/'text-plan.json',plan);dump(root/'text-selection.json',selections)
 out=root/'text-edited.hwpx';dump(root/'text-dry-run.json',se.apply_plan(source,out,plan,dry_run=True));dump(root/'text-receipt.json',se.apply_plan(source,out,plan))
 req=dict(schema=ff.REQUEST,fields=[dict(id='title',label='사업명',direction='right',table=4,expected_occurrences=1,paragraphs=[1],values=[['현장 운영 개선 시범 사업']]),dict(id='purpose',label='추진목적',direction='right',table=4,expected_occurrences=1,paragraphs=[1,2],values=[['운영 절차와 안내 자료를 정리하여 참여자의 혼선을 줄인다.','담당 역할과 확인 기준을 합의하고 시범 운영 결과를 점검한다.']]),dict(id='activities',label='활동',direction='right',table=4,expected_occurrences=2,paragraphs=[1],values=[['안내 자료를 검토하고 담당 역할을 확인한다.'],['현장 운영을 점검하고 보완 과제를 정리한다.']])])
 ins=ff.inspect_form(out,req);dump(root/'form-inspection.json',ins);plan=ff.make_form_plan(ins);dump(root/'form-plan.json',plan)
 final=root/'edited-candidate.hwpx';dump(root/'form-dry-run.json',ff.apply_form(out,final,plan,dry_run=True));dump(root/'form-receipt.json',ff.apply_form(out,final,plan))
 assert sha(source)==before
 dump(root/'edit-summary.json',dict(source=str(source),sourceSha256=before,candidateSha256=sha(final),textEdits=len(specs),formParagraphs=5,sourceUnchanged=True,structure='PASS_STRUCTURE',native='pending'))
 print('CANDIDATE_CREATED',final)
if __name__=='__main__':
 a=argparse.ArgumentParser();sub=a.add_subparsers(dest='action',required=True);b=sub.add_parser('build');b.add_argument('--output-dir',required=True);b.add_argument('--format');x=sub.add_parser('edit');x.add_argument('--source',required=True);x.add_argument('--output-dir',required=True);args=a.parse_args()
 if args.action=='build':build(args.output_dir,args.format)
 else:edit(args.source,args.output_dir)



