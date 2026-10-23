"""Guard failures, atomic publication and valid controls for the common facade."""
from pathlib import Path
import subprocess,sys,uuid,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import hangul_task as task

class CommonTask(unittest.TestCase):
 def setUp(self):self.temp=Path(__file__).resolve().parent/('.test-common-'+uuid.uuid4().hex);self.temp.mkdir();self.out=self.temp/'result.hwpx'
 def tearDown(self):
  for name in ['result.hwpx','result.receipt.json','bad.hwpx']:(self.temp/name).unlink(missing_ok=True)
  self.temp.rmdir()
 def table_request(self):
  return dict(schema=task.SCHEMA,operation='table',headers=['단계','실행 업무','담당','완료 목표'],reason='가상 시험에서 완료 업무를 삭제하고 명칭과 설명을 추가한다.',operations=[dict(op='delete',key={'실행 업무':'물품 목록과 사진 기록 확정'}),dict(op='insert_after',key={'실행 업무':'새 사업장 통신·전원 점검'},cells=['사전 점검','새 점검명: 전체 설명을 유지한다.','시설지원반','10월 21일'],heightHwpunit=2400)])
 def blocked_table(self,q):
  source=ROOT/'assets/complex-structure/source.hwpx';before=task.sha(source)
  with self.assertRaises(ValueError):task.table(source,self.out,q)
  self.assertFalse(self.out.exists());self.assertEqual(before,task.sha(source))
 def test_doctor_is_not_permission_or_native_proof(self):
  d=task.doctor();self.assertEqual(d['writePermission'],'UNTESTED');self.assertEqual(d['securityModule'],'NOT_CHECKED');self.assertIn(str(ROOT/'vendor'),d['hwpxModule'])
 def test_removed_blank_document_commands_publish_nothing(self):
  for args in [('new',str(self.out)),('schema','new')]:
   result=subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'scripts/hangul_task.py'),*args],capture_output=True)
   self.assertEqual(result.returncode,2);self.assertFalse(self.out.exists())
  result=subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'scripts/create_new_document.py')],capture_output=True)
  self.assertEqual(result.returncode,2);self.assertIn(b'BLOCKED_REMOVED_WORKFLOW',result.stdout);self.assertFalse(self.out.exists())
 def test_source_template_copy_preserves_original_and_rejects_overwrite(self):
  from select_document_template import select
  source=ROOT/'assets/mixed-runs/source.hwpx';before=task.sha(source)
  result=select(ROOT,output=self.out,user_source=source)
  self.assertEqual(result['selection'],'user_source_first');self.assertEqual(before,task.sha(self.out));self.assertEqual(before,task.sha(source))
  with self.assertRaises(FileExistsError):select(ROOT,output=self.out,user_source=source)
  self.assertEqual(before,task.sha(self.out))
 def test_source_template_rejects_extension_change(self):
  from select_document_template import select
  source=ROOT/'assets/mixed-runs/source.hwpx'
  with self.assertRaises(ValueError):select(ROOT,output=self.temp/'wrong.hwp',user_source=source)
  self.assertFalse((self.temp/'wrong.hwp').exists())
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
