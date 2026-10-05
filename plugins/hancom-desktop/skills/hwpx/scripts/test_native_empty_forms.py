import sys,pathlib,tempfile,unittest,copy,zipfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from hwpx import HwpxDocument
from lxml import etree as E
from form_fill import inspect_form,make_form_plan,apply_form,REQUEST
from safe_edit import sections
class NativeEmptyTests(unittest.TestCase):
 def test_childless_native_run_filled_and_existing_style_preserved(self):
  with tempfile.TemporaryDirectory() as temp:
   root=pathlib.Path(temp);src=root/'source.hwpx';out=root/'out.hwpx'
   d=HwpxDocument.new();t=d.add_table(1,2);t.cell(0,0).set_text('제목');t.cell(0,1).set_text('');p=t.cell(0,1).paragraphs[0]
   r=p.runs[0];styled=p.add_run('',bold=True);r.char_pr_id_ref=styled.char_pr_id_ref
   # Synthetic test fixture reproduces native saving of empty text nodes.
   for run in p.runs:
    for child in list(run.element):run.element.remove(child)
   d.save_to_path(src);d.close();original=src.read_bytes()
   req={'schema':REQUEST,'fields':[dict(id='title',label='제목',direction='right',expected_occurrences=1,paragraphs=[1],values=[['시험 제목']])]}
   ins=inspect_form(src,req);self.assertEqual(ins['status'],'REQUIRES_EXPLICIT_PLAN')
   rec=apply_form(src,out,make_form_plan(ins));self.assertTrue(rec['run_diff'][0]['create_plain_text'])
   self.assertEqual(src.read_bytes(),original)
   before=sections(src)[0][1];after=sections(out)[0][1];ns={'hp':'http://www.hancom.co.kr/hwpml/2011/paragraph'}
   br=before.findall('.//hp:tc',ns)[1].findall('.//hp:run',ns);ar=after.findall('.//hp:tc',ns)[1].findall('.//hp:run',ns)
   self.assertEqual([dict(x.attrib) for x in br],[dict(x.attrib) for x in ar]);self.assertEqual(len(ar[0]),1);self.assertEqual(ar[0][0].text,'시험 제목');self.assertEqual(len(ar[1]),0)
 def test_control_run_is_not_accepted_as_empty(self):
  with tempfile.TemporaryDirectory() as temp:
   src=pathlib.Path(temp)/'source.hwpx';d=HwpxDocument.new();t=d.add_table(1,2);t.cell(0,0).set_text('제목');t.cell(0,1).set_text('');run=t.cell(0,1).paragraphs[0].runs[0]
   for child in list(run.element):run.element.remove(child)
   E.SubElement(run.element,'{http://www.hancom.co.kr/hwpml/2011/paragraph}ctrl')
   d.save_to_path(src);d.close()
   req={'schema':REQUEST,'fields':[dict(id='title',label='제목',direction='right',expected_occurrences=1,paragraphs=[1],values=[['시험 제목']])]}
   self.assertEqual(inspect_form(src,req)['status'],'BLOCKED')
 def test_run_with_stray_text_is_not_accepted_as_empty(self):
  with tempfile.TemporaryDirectory() as temp:
   src=pathlib.Path(temp)/'source.hwpx';d=HwpxDocument.new();t=d.add_table(1,2);t.cell(0,0).set_text('제목');t.cell(0,1).set_text('');run=t.cell(0,1).paragraphs[0].runs[0]
   for child in list(run.element):run.element.remove(child)
   run.element.text='hidden unexpected text';d.save_to_path(src);d.close()
   req={'schema':REQUEST,'fields':[dict(id='title',label='제목',direction='right',expected_occurrences=1,paragraphs=[1],values=[['시험 제목']])]}
   self.assertEqual(inspect_form(src,req)['status'],'BLOCKED')
if __name__=='__main__':unittest.main(verbosity=2)
