"""Guard failures, atomic publication and valid controls for the common facade."""
from pathlib import Path
import copy,sys,uuid,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import hangul_task as task

class CommonTask(unittest.TestCase):
 def setUp(self):self.temp=Path(__file__).resolve().parent/('.test-common-'+uuid.uuid4().hex);self.temp.mkdir();self.out=self.temp/'result.hwpx'
 def tearDown(self):
  for name in ['result.hwpx','result.receipt.json','bad.hwpx']:(self.temp/name).unlink(missing_ok=True)
  self.temp.rmdir()
 def new_request(self):
  return dict(schema=task.SCHEMA,operation='new',purpose='가상 예산 검토',audience='시험 독자',kind='보고서',title='가상 예산 검토',facts={'f1':'제공 예산은 900,000원이다.','f2':'이 자료는 가상 검토안이다.'},numbered_headings=True,blocks=[dict(type='heading',text='검토 내용',level=1),dict(type='heading',text='제공 조건',level=2),dict(type='paragraph',facts=['f1','f2']),dict(type='table',headers=['항목','예산'],rows=[['제공 예산','900,000원']],reason='제공 금액을 확인한다.')])
 def table_request(self):
  return dict(schema=task.SCHEMA,operation='table',headers=['단계','실행 업무','담당','완료 목표'],reason='가상 시험에서 완료 업무를 삭제하고 명칭과 설명을 추가한다.',operations=[dict(op='delete',key={'실행 업무':'물품 목록과 사진 기록 확정'}),dict(op='insert_after',key={'실행 업무':'새 사업장 통신·전원 점검'},cells=['사전 점검','새 점검명: 전체 설명을 유지한다.','시설지원반','10월 21일'],heightHwpunit=2400)])
 def blocked_new(self,q):
  with self.assertRaises((ValueError,KeyError,TypeError)):task.new(self.out,q)
  self.assertFalse(self.out.exists())
 def blocked_table(self,q):
  source=ROOT/'assets/complex-structure/source.hwpx';before=task.sha(source)
  with self.assertRaises(ValueError):task.table(source,self.out,q)
  self.assertFalse(self.out.exists());self.assertEqual(before,task.sha(source))
 def test_doctor_is_not_permission_or_native_proof(self):
  d=task.doctor();self.assertEqual(d['writePermission'],'UNTESTED');self.assertEqual(d['securityModule'],'NOT_CHECKED');self.assertIn(str(ROOT/'vendor'),d['hwpxModule'])
 def test_new_valid_and_exact_claim_links(self):
  q=self.new_request();dry=task.new(self.out,q,True);self.assertFalse(self.out.exists());self.assertEqual(dry['design']['claims'][0],{'text':q['facts']['f1'],'evidence':['f1']});result=task.new(self.out,q);self.assertEqual(result['status'],'PASS_STRUCTURE')
 def test_missing_fact_rejected(self):
  q=self.new_request();q['blocks'][2]['facts']=['f1'];self.blocked_new(q)
 def test_format_alias_rejected(self):
  q=self.new_request();q['format']={'font_size_pt':10};self.blocked_new(q)
 def test_unknown_heading_field_rejected(self):
  q=self.new_request();q['blocks'][0]['list']={'kind':'number'};self.blocked_new(q)
 def test_non_source_number_rejected(self):
  q=self.new_request();q['blocks'].append(dict(type='paragraph',text='실제 예산은 999,999원이다.'));self.blocked_new(q)
 def test_bad_table_shape_rejected(self):
  q=self.new_request();q['blocks'][3]['rows']=[['항목만']];self.blocked_new(q)
 def test_unknown_fact_ref_rejected(self):
  q=self.new_request();q['blocks'][2]['facts']=['unknown'];self.blocked_new(q)
 def test_overwrite_rejected(self):
  self.out.write_bytes(b'keep')
  with self.assertRaises(FileExistsError):task.new(self.out,self.new_request())
  self.assertEqual(self.out.read_bytes(),b'keep')
 def test_table_atomic_and_complete_name(self):
  source=ROOT/'assets/complex-structure/source.hwpx';before=task.sha(source);q=self.table_request();dry=task.table(source,self.out,q,True);self.assertFalse(self.out.exists());self.assertEqual(dry['status'],'PASS_STRUCTURE');task.table(source,self.out,q)
  import semantic_table_binding as b
  result=b.bind(self.out,q['headers'],{'실행 업무':q['operations'][1]['cells'][1]});self.assertEqual(result['values'],q['operations'][1]['cells']);self.assertEqual(before,task.sha(source))
 def test_late_failure_no_partial_final(self):
  q=self.table_request();q['operations'].append({'op':'unsupported','key':{}});self.blocked_table(q)
 def test_incomplete_row_rejected(self):
  q=self.table_request();q['operations'][1]['cells']=q['operations'][1]['cells'][:3];self.blocked_table(q)
 def test_header_mismatch_rejected(self):
  q=self.table_request();q['headers'][0]='다른 제목';self.blocked_table(q)
 def test_partial_key_rejected(self):
  q=self.table_request();q['operations'][0]['key']['실행 업무']='물품 목록';self.blocked_table(q)
 def test_unbounded_height_rejected(self):
  q=self.table_request();q['operations'][1]['heightHwpunit']=99999;self.blocked_table(q)
 def test_replace_unique_valid_and_missing_blocked(self):
  source=ROOT/'assets/mixed-runs/source.hwpx';old='실제 운영 결정을 내리기 전에는 원본과 담당 확인이 필요하다.';before=task.sha(source)
  result=task.replace(source,self.out,old,'실제 운영 결정을 내리기 전에는 원본과 담당자의 서면 확인이 필요하다.');self.assertEqual(result['status'],'PASS_STRUCTURE');self.assertEqual(before,task.sha(source))
  with self.assertRaises(ValueError):task.replace(source,self.temp/'bad.hwpx','없는문구','새문구')
  self.assertFalse((self.temp/'bad.hwpx').exists())
if __name__=='__main__':unittest.main()
