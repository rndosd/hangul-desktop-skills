"""Source-package guards for optional report flow, spacing and page margins."""
import copy,tempfile,unittest,zipfile,xml.etree.ElementTree as E
from pathlib import Path
from create_new_document import create,prepare_design,formatting,audit_output,NS

def fixture():
 b=dict(request='운영 검토 초안 작성',purpose='운영 방식 검토',audience='담당자',kind='합성 시험',allow_draft=True,facts={},unknowns=[],requirements=[dict(id='main',description='운영 검토',must_include=['운영'])])
 blocks=[dict(id='h',type='heading',level=1,text='운영 방향'),dict(id='p',type='paragraph',text='운영 절차를 검토한다.'),dict(id='t',type='table',caption='역할 확인',columns=[dict(key='a',label='역할'),dict(key='b',label='내용')],rows=[dict(a='담당',b='안내를 확인한다.')],reason='같은 속성 비교'),dict(id='tail',type='paragraph',text='필요한 내용을 확인한 뒤 보완한다.')]
 d=dict(schema='hwpx.new_document.v1',plan=dict(schemaVersion='hwpx.document_plan.v1',title='운영 검토 시험',blocks=blocks),coverage={'main':['h','p','t','tail']},claims=[],review={},format={'table_layout':dict(cell_margins_mm=dict(left=1.5,right=1.5,top=1,bottom=1),vertical_align='TOP',line_wrap='BREAK',page_break='TABLE',repeat_header=True,treat_as_char=False)})
 return b,prepare_design(b,d)
class PageFlowChecks(unittest.TestCase):
 def test_outer_spacing_persisted_and_audited(self):
  b,d=fixture();d['format']['table_outer_spacing_pt']={'before':6,'after':8}
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'x.hwpx';create(b,d,p)
   with zipfile.ZipFile(p) as z:s=E.fromstring(z.read('Contents/section0.xml'))
   out=s.find('.//hp:tbl/hp:outMargin',NS);self.assertEqual(out.get('top'),'600');self.assertEqual(out.get('bottom'),'800');self.assertEqual(audit_output(p,b,d)['status'],'PASS_STRUCTURE')
 def test_spacing_invalid_values_rejected(self):
  for val in [dict(before=-1,after=8),dict(before=True,after=8),dict(before=6,after=99),dict(before=6,after=8,extra=0)]:
   b,d=fixture();d['format']['table_outer_spacing_pt']=val
   with self.assertRaises(ValueError):formatting(b,d)
 def test_partial_page_margins_merge_and_persist(self):
  b,d=fixture();d['format']['margins_mm']={'top':15,'bottom':15,'left':17,'right':17}
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'x.hwpx';create(b,d,p);self.assertEqual(audit_output(p,b,d)['status'],'PASS_STRUCTURE')
  d['format']['margins_mm']={'top':15};self.assertEqual(formatting(b,d)['margins_mm'],dict(left=20,right=20,top=15,bottom=20))
 def test_invalid_page_margins_rejected(self):
  for val in [{'top':True},{'top':-1},{'top':float('nan')},{'left':180},{'unknown':10}]:
   b,d=fixture();d['format']['margins_mm']=val
   with self.assertRaises(ValueError):formatting(b,d)
 def test_major_heading_has_more_front_space(self):
  b,d=fixture();fmt=formatting(b,d);self.assertGreater(fmt['heading_layout'][0]['spacing_before_pt'],fmt['heading_layout'][1]['spacing_before_pt']);self.assertGreater(fmt['heading_layout'][0]['spacing_before_pt'],fmt['body_spacing_pt']['after'])
 def test_header_and_split_anchor_persist(self):
  for mode in ['CELL','TABLE']:
   b,d=fixture();d['format']['table_layout']['page_break']=mode
   with tempfile.TemporaryDirectory() as folder:
    p=Path(folder)/'x.hwpx';create(b,d,p)
    with zipfile.ZipFile(p) as z:s=E.fromstring(z.read('Contents/section0.xml'))
    t=s.find('.//hp:tbl',NS);self.assertEqual(t.get('pageBreak'),mode);self.assertEqual(t.get('repeatHeader'),'1');self.assertEqual(t.find('hp:pos',NS).get('treatAsChar'),'0');self.assertTrue(all(c.get('header')=='1' for c in t.find('hp:tr',NS)))
 def test_boolean_anchor_required(self):
  for val in [0,1,'false',None]:
   b,d=fixture();d['format']['table_layout']['treat_as_char']=val
   with self.assertRaises(ValueError):formatting(b,d)
 def test_native_empty_anchor_text_is_prepared(self):
  b,d=fixture()
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'x.hwpx';create(b,d,p)
   with zipfile.ZipFile(p) as z:s=E.fromstring(z.read('Contents/section0.xml'))
   host=next(p for p in s.findall('hp:p',NS) if p.find('hp:run/hp:tbl',NS) is not None);r=host.find('hp:run',NS);self.assertEqual(list(r)[-1].tag,'{'+NS['hp']+'}t');self.assertIsNotNone(r.find('hp:tbl',NS))
if __name__=='__main__':unittest.main()
