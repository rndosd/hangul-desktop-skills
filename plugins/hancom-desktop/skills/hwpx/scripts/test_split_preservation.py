from pathlib import Path
import sys,tempfile,unittest,copy,io,zipfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent));sys.path.insert(0,str(Path(__file__).resolve().parent))
import safe_cell_layout as c
from namespace_literal_guard import preserve_namespace_literals
from hwpx.oxml.table import HwpxOxmlTable
SOURCE=Path(__file__).resolve().parents[1]/'assets/complex-structure/source.hwpx'
if not SOURCE.exists():SOURCE=Path('outputs/complex-structure/original-final/saved.hwpx')
apply=preserve_namespace_literals(c.apply)
def fixture(data,alignment):
 from lxml import etree as E
 m,part,root,t=c.locate(data,6);cell=c.geometry(t)[0][2,0];cell.find(c.P+'subList').set('vertAlign',alignment);m[part]=E.tostring(root,encoding='UTF-8',xml_declaration=True);out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for k,v in m.items():z.writestr(k,v)
 return out.getvalue()
class SplitPreservation(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.d=Path(self.tmp.name);self.source=self.d/'source.hwpx';self.source.write_bytes(SOURCE.read_bytes());self.output=self.d/'out.hwpx';self.req=dict(schema=c.SCHEMA,source_sha256=c.sha(self.source),table=6,operation='unmerge',range=[3,1,3,3])
 def tearDown(self):self.tmp.cleanup()
 def reject(self):
  old=self.source.read_bytes()
  with self.assertRaises(ValueError):apply(self.source,self.output,self.req)
  self.assertFalse(self.output.exists());self.assertEqual(old,self.source.read_bytes())
 def align(self,v):self.source.write_bytes(fixture(self.source.read_bytes(),v));self.req['source_sha256']=c.sha(self.source)
 def success(self,v):
  self.align(v);r=apply(self.source,self.output,self.req);self.assertTrue(r['checks']['stylesPreserved']);self.assertTrue(r['checks']['nonTargetPackageAndXmlPreserved']);cells=c.geometry(c.locate(self.output.read_bytes(),6)[3])[0]
  self.assertEqual([cells[2,i].find(c.P+'subList').get('vertAlign') for i in range(3)],[v]*3);self.assertEqual(c.text(cells[2,0]),'운영 공지: 기존 창구 폐쇄와 신규 창구 개시를 같은 시각에 안내한다.');self.assertEqual([c.text(cells[2,i]) for i in [1,2]],['',''])
 def test_top_source_survives_default_center_bug(self):self.success('TOP')
 def test_bottom_source_survives_default_center_bug(self):self.success('BOTTOM')
 def test_center_source_still_works(self):self.success('CENTER')
 def test_dryrun(self):self.assertFalse(apply(self.source,self.output,self.req,True)['published']);self.assertFalse(self.output.exists())
 def test_stale(self):self.req['source_sha256']='0'*64;self.reject()
 def test_partial_merge_range(self):self.req['range']=[3,1,3,2];self.reject()
 def test_vertical_split_refused(self):self.req['range']=[2,1,3,3];self.reject()
 def test_populated_merge_refused(self):self.req.update(operation='merge',range=[2,1,2,3]);self.reject()
 def test_unknown_source_alignment(self):self.align('UNKNOWN');self.reject()
 def test_non_target_corruption_still_refused(self):
  original=HwpxOxmlTable.split_merged_cell
  def corrupt(t,y,x):
   result=original(t,y,x);t.cell(0,0).element.find(c.P+'subList').set('vertAlign','BOTTOM');return result
  with patch.object(HwpxOxmlTable,'split_merged_cell',corrupt):self.reject()
 def test_new_cell_unrelated_property_corruption_refused(self):
  original=HwpxOxmlTable.split_merged_cell
  def corrupt(t,y,x):
   result=original(t,y,x);t.cell(y,x+1).element.find(c.P+'subList').set('lineWrap','SQUEEZE');return result
  with patch.object(HwpxOxmlTable,'split_merged_cell',corrupt):self.reject()
if __name__=='__main__':unittest.main()
