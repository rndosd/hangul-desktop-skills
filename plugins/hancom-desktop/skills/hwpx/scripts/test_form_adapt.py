from pathlib import Path
import sys,json,copy,tempfile,unittest,io,zipfile,os
from unittest.mock import patch
script_root=Path(__file__).resolve().parent
if not (script_root/'safe_cell_layout.py').is_file():script_root=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'skills/hwpx/scripts'
sys.path.insert(0,str(script_root))
import form_adapt as a
import safe_repeat_rows as r
SOURCE=Path(__file__).resolve().parents[1]/'assets/form-adaptation/source.hwpx'
if not SOURCE.exists():SOURCE=Path(__file__).parent/'source.hwpx'
REQUEST=Path(__file__).resolve().parents[1]/'assets/form-adaptation/short-request.json'
if not REQUEST.exists():REQUEST=Path(__file__).parent/'short-request.json'
def mutate(data,fn):
 m=r.locate(data,3)[0];root=__import__('safe_cell_layout').xml(m['Contents/section0.xml']);fn(root);from lxml import etree;m['Contents/section0.xml']=etree.tostring(root,xml_declaration=True,encoding='UTF-8');b=io.BytesIO()
 with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
  for k,v in m.items():z.writestr(k,v)
 return b.getvalue()
class Adaptation(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.d=Path(self.tmp.name);self.src=self.d/'source.hwpx';self.src.write_bytes(SOURCE.read_bytes());self.out=self.d/'out.hwpx';self.req=json.loads(REQUEST.read_text(encoding='utf-8-sig'));self.req['source_sha256']=a.sha(self.src)
 def tearDown(self):self.tmp.cleanup()
 def reject(self):
  with self.assertRaises((ValueError,TypeError,KeyError)):a.apply(self.src,self.out,self.req)
  self.assertFalse(self.out.exists());self.assertEqual(self.src.read_bytes(),SOURCE.read_bytes())
 def test_short(self):self.assertTrue(a.apply(self.src,self.out,self.req)['checks']['allRequestedFieldsAndRepeatValuesReadBack'])
 def test_expand(self):self.req['repeat']['values']=[['항목 '+str(i),'추진 내용 '+str(i)] for i in range(8)];self.assertTrue(a.apply(self.src,self.out,self.req)['checks']['protectedTablesExact'])
 def test_dry_run(self):self.assertFalse(a.apply(self.src,self.out,self.req,True)['published']);self.assertFalse(self.out.exists())
 def test_existing(self):self.out.write_bytes(b'keep');self.assertRaises(ValueError,a.apply,self.src,self.out,self.req);self.assertEqual(self.out.read_bytes(),b'keep')
 def test_same_source(self):self.assertRaises(ValueError,a.apply,self.src,self.src,self.req)
 def test_stale(self):self.req['source_sha256']='0'*64;self.reject()
 def test_protected_field(self):self.req['fields'][0]['table']=1;self.reject()
 def test_protected_repeat(self):self.req['repeat']['table']=1;self.reject()
 def test_protected_resize(self):self.req['geometry'][0]['table']=1;self.reject()
 def test_protected_flow(self):self.req['flow']=[dict(table=1,page_break='TABLE')];self.reject()
 def test_required_label(self):self.req['required_labels'].append('없는 필수 라벨');self.reject()
 def test_duplicate_protected(self):self.req['preserve_tables']=[1,1];self.reject()
 def test_missing_protected(self):self.req['preserve_tables']=[];self.reject()
 def test_unknown(self):self.req['auto_shrink']=True;self.reject()
 def test_no_reason(self):self.req['editable_reason']='';self.reject()
 def test_wrong_header(self):self.req['repeat']['expected_headers'][0]='이름';self.reject()
 def test_wrong_template(self):self.req['repeat']['template_row']=1;self.reject()
 def test_boolean_template(self):self.req['repeat']['template_row']=True;self.reject()
 def test_zero_rows(self):self.req['repeat']['values']=[];self.reject()
 def test_limit(self):self.req['repeat']['values']=[['a','b']]*41;self.reject()
 def test_column_count(self):self.req['repeat']['values']=[['a']];self.reject()
 def test_newline(self):self.req['repeat']['values'][0][1]='a\nb';self.reject()
 def test_empty_row(self):self.req['repeat']['values']=[['','']];self.reject()
 def test_late_resize_failure_atomic(self):self.req['geometry'][0]['widths_mm']=[60,160];self.reject();self.assertFalse(any(self.d.glob('adapt-form-*')))
 def test_ambiguous_field(self):self.req['fields'][0]['expected_occurrences']=2;self.reject()
 def test_field_repeat_overlap(self):self.req['fields'][0]['table']=3;self.reject()
 def test_flow_unknown(self):self.req['flow']=[dict(table=3,unknown=True)];self.reject()
 def test_populated_repeat(self):
  data=mutate(self.src.read_bytes(),lambda s:list(s.iter(r.P+'tbl'))[2].findall(r.P+'tr')[1].find(r.P+'tc').find(r.P+'subList')[0].find(r.P+'run').append(s.makeelement(r.P+'t',{})));m=r.locate(data,3)[0];root=__import__('safe_cell_layout').xml(m['Contents/section0.xml']);list(root.iter(r.P+'tbl'))[2].findall(r.P+'tr')[1].find(r.P+'tc').find(r.P+'subList')[0].find(r.P+'run')[0].text='기존 업무';from lxml import etree;m['Contents/section0.xml']=etree.tostring(root);b=io.BytesIO()
  with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
   for k,v in m.items():z.writestr(k,v)
  req=dict(schema=r.SCHEMA,source_sha256=__import__('hashlib').sha256(b.getvalue()).hexdigest(),editable_reason='시험',**self.req['repeat']);self.assertRaises(ValueError,r.checked,b.getvalue(),req)
 def test_protected_cell(self):
  data=mutate(self.src.read_bytes(),lambda s:list(s.iter(r.P+'tbl'))[2].findall(r.P+'tr')[1].find(r.P+'tc').set('protect','1'));req=dict(schema=r.SCHEMA,source_sha256=__import__('hashlib').sha256(data).hexdigest(),editable_reason='시험',**self.req['repeat']);self.assertRaises(ValueError,r.checked,data,req)
 def test_fixed_table(self):
  data=mutate(self.src.read_bytes(),lambda s:list(s.iter(r.P+'tbl'))[2].set('noAdjust','1'));req=dict(schema=r.SCHEMA,source_sha256=__import__('hashlib').sha256(data).hexdigest(),editable_reason='시험',**self.req['repeat']);self.assertRaises(ValueError,r.checked,data,req)
 def test_multi_paragraph(self):
  data=mutate(self.src.read_bytes(),lambda s:list(s.iter(r.P+'tbl'))[2].findall(r.P+'tr')[1].find(r.P+'tc').find(r.P+'subList').append(copy.deepcopy(list(s.iter(r.P+'tbl'))[2].findall(r.P+'tr')[1].find(r.P+'tc').find(r.P+'subList')[0])));req=dict(schema=r.SCHEMA,source_sha256=__import__('hashlib').sha256(data).hexdigest(),editable_reason='시험',**self.req['repeat']);self.assertRaises(ValueError,r.checked,data,req)
 def test_blank_source_and_ids(self):
  req=dict(schema=r.SCHEMA,source_sha256=r.sha(self.src),editable_reason='시험',**self.req['repeat']);q=r.apply(self.src,self.out,req);self.assertTrue(q['checks']['paragraphIdsUnique']);self.assertTrue(q['checks']['onlyBlankSourceRowsRemoved'])
 def test_corruption_prevents_publication(self):
  original=r.HwpxDocument.to_bytes
  def corrupt(doc):return mutate(original(doc),lambda s:list(s.iter(r.P+'tbl'))[0].find(r.P+'tr').find(r.P+'tc').set('protect','1'))
  with patch.object(r.HwpxDocument,'to_bytes',corrupt):self.reject()
if __name__=='__main__':unittest.main()
