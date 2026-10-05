import pathlib,tempfile,unittest,dataclasses
from unittest.mock import patch
from hwpx import HwpxDocument
from safe_table_layout import inspect,apply,SCHEMA
from hwpx.table_patch import apply_table_ops
class TableLayoutTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name);self.src=self.root/'source.hwpx';self.out=self.root/'out.hwpx';d=HwpxDocument.new();d.add_paragraph('KEEP');t=d.add_table(4,2,width=round(170*7200/25.4))
  for r,row in enumerate([['업무','상태'],['수집','대기'],['점검','완료'],['정리','제출']]):
   for c,text in enumerate(row):t.cell(r,c).set_text(text)
  d.save_to_path(self.src);d.close();self.before=self.src.read_bytes();self.ins=inspect(self.src,1)
 def req(self,**kw):return dict(schema=SCHEMA,source_sha256=self.ins['source_sha256'],table=1,**kw)
 def blocked(self,req):
  with self.assertRaises((ValueError,AssertionError)):apply(self.src,self.out,req)
  self.assertFalse(self.out.exists());self.assertEqual(self.src.read_bytes(),self.before)
 def test_insert_preserves_template_and_original(self):
  r=apply(self.src,self.out,self.req(operation='insert_after',row=3,values=['공유','안내']));self.assertTrue(r['checks']['nonTargetXmlEqual']);rows=inspect(self.out,1)['rows'];self.assertEqual(rows,[['업무','상태'],['수집','대기'],['점검','완료'],['공유','안내'],['정리','제출']]);self.assertEqual(self.src.read_bytes(),self.before)
 def test_delete_exact_data_row(self):
  apply(self.src,self.out,self.req(operation='delete_row',row=2));self.assertEqual(inspect(self.out,1)['rows'],[['업무','상태'],['점검','완료'],['정리','제출']])
 def test_resize_keeps_text_and_total_width(self):
  apply(self.src,self.out,self.req(operation='resize',widths_mm=[60,110],heights_mm={'4':18}));after=inspect(self.out,1);self.assertEqual(after['rows'],self.ins['rows']);self.assertAlmostEqual(sum(after['widths_mm']),170,places=2);self.assertAlmostEqual(after['heights_mm'][3],18,places=2)
 def test_header_cannot_be_deleted(self):self.blocked(self.req(operation='delete_row',row=1))
 def test_width_expansion_requires_separate_support(self):self.blocked(self.req(operation='resize',widths_mm=[60,130]))
 def test_stale_source_is_rejected(self):
  r=self.req(operation='delete_row',row=2);r['source_sha256']='0'*64;self.blocked(r)
 def test_no_output_created_by_dry_run(self):
  r=apply(self.src,self.out,self.req(operation='delete_row',row=2),dry_run=True);self.assertFalse(r['published']);self.assertFalse(self.out.exists())
 def test_merged_target_is_rejected(self):
  d=HwpxDocument.open(self.src);d.tables.all[0].merge_cells(1,0,2,0);d.save_to_path(self.src);d.close()
  with self.assertRaises(ValueError):inspect(self.src,1)
 def test_nested_target_is_rejected(self):
  d=HwpxDocument.new();host=d.add_table(1,1);inner=host.cell(0,0).add_table(2,1);inner.cell(0,0).set_text('a');inner.cell(1,0).set_text('b');d.save_to_path(self.src);d.close()
  with self.assertRaises(ValueError):inspect(self.src,2)
 def test_non_target_corruption_prevents_publication(self):
  def bad(*a,**kw):
   r=apply_table_ops(*a,**kw)
   # Public parser can read the test corruption; preservation must still reject it.
   import io,zipfile
   buf=io.BytesIO()
   with zipfile.ZipFile(io.BytesIO(r.data)) as zin,zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as zout:
    for name in zin.namelist():zout.writestr(name,zin.read(name).replace(b'KEEP',b'LOST') if name.endswith('section0.xml') else zin.read(name))
   return dataclasses.replace(r,data=buf.getvalue())
  with patch('safe_table_layout.apply_table_ops',bad):self.blocked(self.req(operation='delete_row',row=2))
if __name__=='__main__':unittest.main(verbosity=2)
