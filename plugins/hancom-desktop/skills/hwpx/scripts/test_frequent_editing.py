from pathlib import Path
import unittest,tempfile,copy,json,zipfile,io
import safe_cell_layout as f
import create_report_pages as p
class Guards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.out=Path(self.tmp.name)/'new.hwpx';self.src=Path(__file__).resolve().parents[1]/'assets/cell-layout-fixture.hwpx';self.merged=Path(__file__).resolve().parents[1]/'assets/cell-layout-merged-fixture.hwpx';self.req=dict(schema=f.SCHEMA,source_sha256=f.sha(self.src),table=1,operation='merge',range=[2,1,2,3])
 def tearDown(self):self.tmp.cleanup()
 def apply(self,req=None):return f.apply(self.src,self.out,req or self.req)
 def blocked(self,req):
  with self.assertRaises(ValueError):self.apply(req)
  self.assertFalse(self.out.exists())
 def test_blank_merge(self):
  old=f.sha(self.src);r=self.apply();self.assertTrue(r['checks']['targetContentPreserved']);self.assertEqual(old,f.sha(self.src));_,_,_,t=f.locate(self.out.read_bytes(),1);self.assertEqual(f.span(f.geometry(t)[0][1,0]),(1,3))
 def test_unmerge_retains_styles(self):
  req=dict(self.req,source_sha256=f.sha(self.merged),operation='unmerge');r=f.apply(self.merged,self.out,req);self.assertTrue(r['checks']['stylesPreserved'])
 def test_all_horizontal_alignments(self):
  for a in ['LEFT','CENTER','RIGHT']:
   r=f.apply(self.src,Path(self.tmp.name)/(a+'.hwpx'),dict(self.req,operation='align',range=[3,1,3,3],alignment=a));self.assertTrue(r['checks']['stylesPreserved'])
 def test_dry_run(self):f.apply(self.src,self.out,self.req,True);self.assertFalse(self.out.exists())
 def test_stale_hash(self):self.blocked(dict(self.req,source_sha256='0'*64))
 def test_content_loss(self):self.blocked(dict(self.req,range=[3,1,3,3]))
 def test_vertical_outside_scope(self):self.blocked(dict(self.req,range=[2,1,3,1]))
 def test_partial_unmerge(self):
  with self.assertRaises(ValueError):f.apply(self.merged,self.out,dict(self.req,source_sha256=f.sha(self.merged),operation='unmerge',range=[2,1,2,2]))
 def test_invalid_bool_coordinate(self):self.blocked(dict(self.req,range=[True,1,2,3]))
 def test_out_of_bounds(self):self.blocked(dict(self.req,range=[2,1,2,9]))
 def test_unknown_request_key(self):self.blocked(dict(self.req,force=True))
 def test_no_overwrite(self):
  self.out.write_bytes(b'keep')
  with self.assertRaises(ValueError):self.apply()
  self.assertEqual(self.out.read_bytes(),b'keep')
 def test_alignment_on_merged_cell(self):
  with self.assertRaises(ValueError):f.apply(self.merged,self.out,dict(self.req,source_sha256=f.sha(self.merged),operation='align',alignment='CENTER'))
 def test_alignment_unsupported(self):self.blocked(dict(self.req,operation='align',alignment='JUSTIFY',range=[3,1,3,3]))
 def test_non_target_corruption_detected(self):
  self.apply();b=self.src.read_bytes();a=self.out.read_bytes();m=f.parts(a);part='Contents/section0.xml';root=f.xml(m[part]);node=next(n for n in root.iter(f.P+'t') if n.text=='보존 표식');node.text='손상';m[part]=f.E.tostring(root,encoding='utf-8');buf=io.BytesIO()
  with zipfile.ZipFile(buf,'w') as z:
   for n,v in m.items():z.writestr(n,v)
  with self.assertRaises(ValueError):f.verify(b,buf.getvalue(),self.req)
 def fresh(self):
  r=Path(__file__).resolve().parents[1]/'assets/report-pages-test';b=json.loads((r/'brief.json').read_text(encoding='utf8'));d=json.loads((r/'design.json').read_text(encoding='utf8'));doc,_=p.author.compose(b,d);return doc
 def opts(self):return dict(schema=p.SCHEMA,header_text='운영 점검 보고서',footer_text='업무 검토용 · 합성 예시',cover=True,body_start_text='운영 점검')
 def test_native_page_controls_inventory(self):
  with self.fresh() as d:
   p.apply_new(d,self.opts());s=d.sections[0];self.assertEqual(len(list(s.element.iter(p.P+'pageNum'))),1);self.assertEqual(len(list(s.element.iter(p.P+'newNum'))),1);self.assertTrue(s.properties.visibility.hide_first_page_num);self.assertFalse(s.properties.element.findall(p.P+'header'))
 def test_no_cover(self):
  with self.fresh() as d:p.apply_new(d,dict(schema=p.SCHEMA,cover=False));self.assertEqual(len(list(d.sections[0].element.iter(p.P+'newNum'))),0)
 def test_no_missing_body_binding(self):
  with self.fresh() as d:
   with self.assertRaises(ValueError):p.apply_new(d,dict(self.opts(),body_start_text='없는 항목'))
 def test_body_without_page_break_rejected(self):
  with self.fresh() as d:
   with self.assertRaises(ValueError):p.apply_new(d,dict(self.opts(),body_start_text='운영 점검 자료'))
 def test_not_repeat_page_controls(self):
  with self.fresh() as d:
   p.apply_new(d,self.opts())
   with self.assertRaises(ValueError):p.apply_new(d,self.opts())
 def test_page_text_newline_rejected(self):
  with self.fresh() as d:
   with self.assertRaises(ValueError):p.apply_new(d,dict(self.opts(),header_text='a\nb'))
if __name__=='__main__':unittest.main(verbosity=2)

