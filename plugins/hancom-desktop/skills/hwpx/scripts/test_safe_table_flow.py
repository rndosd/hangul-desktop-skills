from pathlib import Path
import unittest,tempfile,copy,zipfile,io
from lxml import etree as E
import safe_table_flow as f
class FlowGuards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.src=Path(__file__).resolve().parents[1]/'assets/table-flow/source.hwpx';self.out=Path(self.tmp.name)/'out.hwpx';self.req=dict(schema=f.SCHEMA,source_sha256=f.sha(self.src),table=1,page_break='TABLE')
 def tearDown(self):self.tmp.cleanup()
 def reject(self,req):
  with self.assertRaises(ValueError):f.apply(self.src,self.out,req)
  self.assertFalse(self.out.exists())
 def write_mutated(self,name,mutator):
  data=f.parts(self.src.read_bytes());mutator(data);p=Path(self.tmp.name)/name
  with zipfile.ZipFile(p,'x',zipfile.ZIP_DEFLATED) as z:
   for k,v in data.items():z.writestr(k,v)
  return p
 def mutate_section(self,data,callback):
  r=f.xml(data['Contents/section0.xml']);callback(r);data['Contents/section0.xml']=E.tostring(r,xml_declaration=True,encoding='UTF-8')
 def test_only_split_property_changes(self):
  f.apply(self.src,self.out,self.req);self.assertTrue(f.verify(self.src.read_bytes(),self.out.read_bytes(),self.req)['cellGeometryAndFormattingPreserved'])
 def test_repeat_requires_and_sets_first_row(self):
  req=dict(self.req,repeat_header=True,header_rows=[1]);f.apply(self.src,self.out,req);_,_,_,t=f.locate(self.out.read_bytes(),1);self.assertEqual(t.get('repeatHeader'),'1');self.assertTrue(all(c.get('header')=='1' for c in t.findall(f.P+'tr')[0]))
 def test_disable_keeps_header_flags(self):
  f.apply(self.src,self.out,dict(self.req,repeat_header=False));_,_,_,t=f.locate(self.out.read_bytes(),1);_,_,_,old=f.locate(self.src.read_bytes(),1);self.assertEqual([c.get('header') for c in t.iter(f.P+'tc')],[c.get('header') for c in old.iter(f.P+'tc')])
 def test_one_spacing_side_only(self):
  f.apply(self.src,self.out,dict(self.req,outer_spacing_pt={'after':8}));_,_,_,t=f.locate(self.out.read_bytes(),1);_,_,_,old=f.locate(self.src.read_bytes(),1);self.assertEqual(t.find(f.P+'outMargin').get('top'),old.find(f.P+'outMargin').get('top'));self.assertEqual(t.find(f.P+'outMargin').get('bottom'),'800')
 def test_caption_public_style_clone(self):
  self.src=self.src.with_name('caption.hwpx');req=dict(schema=f.SCHEMA,source_sha256=f.sha(self.src),table=1,caption={'expected_text':'운영 점검 제목 유지','keep_with_next':True});f.apply(self.src,self.out,req);self.assertTrue(f.verify(self.src.read_bytes(),self.out.read_bytes(),req)['oldSharedStylesUnchanged'])
 def test_anchor_binding_only_requested_flag(self):
  req=dict(self.req,anchor_same_page=True);f.apply(self.src,self.out,req);self.assertTrue(f.verify(self.src.read_bytes(),self.out.read_bytes(),req)['nonTargetPackagePreserved']);_,_,_,t=f.locate(self.out.read_bytes(),1);self.assertEqual(t.find(f.P+'pos').get('holdAnchorAndSO'),'1')
 def test_anchor_boolean_only(self):self.reject(dict(self.req,anchor_same_page=1))
 def test_anchor_false_not_supported(self):self.reject(dict(self.req,anchor_same_page=False))
 def test_anchor_page_relative_refused(self):
  self.src=self.write_mutated('absolute.hwpx',lambda d:self.mutate_section(d,lambda r:r.find('.//'+f.P+'tbl/'+f.P+'pos').set('vertRelTo','PAGE')));self.reject(dict(self.req,source_sha256=f.sha(self.src),anchor_same_page=True))
 def test_caption_explicit_page_break(self):
  self.src=self.src.with_name('caption.hwpx');req=dict(schema=f.SCHEMA,source_sha256=f.sha(self.src),table=1,caption={'expected_text':'운영 점검 제목 유지','keep_with_next':True,'page_break_before':True});f.apply(self.src,self.out,req);self.assertTrue(f.verify(self.src.read_bytes(),self.out.read_bytes(),req)['allTextRunsNativeBreakTailsAndControlsPreserved'])
 def test_caption_page_break_boolean(self):self.reject(dict(self.req,caption={'expected_text':'운영 점검 기록','keep_with_next':True,'page_break_before':1}))
 def test_caption_no_unknown_flags(self):self.reject(dict(self.req,caption={'expected_text':'운영 점검 기록','keep_with_next':True,'font_size':9}))
 def test_wrong_caption_refused(self):self.reject(dict(self.req,caption={'expected_text':'다른 제목','keep_with_next':True}))
 def test_caption_boolean_required(self):self.reject(dict(self.req,caption={'expected_text':'운영 점검 기록','keep_with_next':1}))
 def test_empty_changes_refused(self):self.reject({k:v for k,v in self.req.items() if k!='page_break'})
 def test_no_split_none(self):self.reject(dict(self.req,page_break='NONE'))
 def test_no_unknown_key(self):self.reject(dict(self.req,font_size=9))
 def test_stale_hash(self):self.reject(dict(self.req,source_sha256='0'*64))
 def test_repeat_boolean(self):self.reject(dict(self.req,repeat_header=1))
 def test_header_rows_explicit(self):self.reject(dict(self.req,repeat_header=True))
 def test_header_rows_no_implicit(self):self.reject(dict(self.req,header_rows=[1]))
 def test_header_rows_limited(self):self.reject(dict(self.req,repeat_header=True,header_rows=[1,2]))
 def test_boolean_header_row_refused(self):self.reject(dict(self.req,repeat_header=True,header_rows=[True]))
 def test_spacing_negative(self):self.reject(dict(self.req,outer_spacing_pt={'after':-1}))
 def test_spacing_nan(self):self.reject(dict(self.req,outer_spacing_pt={'after':float('nan')}))
 def test_spacing_boolean(self):self.reject(dict(self.req,outer_spacing_pt={'after':True}))
 def test_spacing_oversized(self):self.reject(dict(self.req,outer_spacing_pt={'after':37}))
 def test_inline_rejected(self):
  self.src=self.write_mutated('inline.hwpx',lambda d:self.mutate_section(d,lambda r:r.find('.//'+f.P+'tbl/'+f.P+'pos').set('treatAsChar','1')));self.reject(dict(self.req,source_sha256=f.sha(self.src)))
 def test_locked_table_rejected(self):
  self.src=self.write_mutated('fixed.hwpx',lambda d:self.mutate_section(d,lambda r:r.find('.//'+f.P+'tbl').set('noAdjust','1')));self.reject(dict(self.req,source_sha256=f.sha(self.src)))
 def test_locked_object_rejected(self):
  self.src=self.write_mutated('locked.hwpx',lambda d:self.mutate_section(d,lambda r:r.find('.//'+f.P+'tbl').set('lock','1')));self.reject(dict(self.req,source_sha256=f.sha(self.src)))
 def test_native_linebreak_tail_preserved(self):
  def add_break(root):
   text=root.find('.//'+f.P+'tc/'+f.P+'subList/'+f.P+'p/'+f.P+'run/'+f.P+'t');text.text='native first';node=text.makeelement(f.P+'lineBreak',{});node.tail='native last';text.append(node)
  self.src=self.write_mutated('break.hwpx',lambda d:self.mutate_section(d,add_break));req=dict(self.req,source_sha256=f.sha(self.src));f.apply(self.src,self.out,req);self.assertTrue(f.verify(self.src.read_bytes(),self.out.read_bytes(),req)['allTextRunsNativeBreakTailsAndControlsPreserved'])
 def test_unrelated_style_corruption_detected(self):
  f.apply(self.src,self.out,self.req);data=f.parts(self.out.read_bytes());header=f.xml(data['Contents/header.xml']);header.find('.//'+f.H+'charPr').set('height','777');data['Contents/header.xml']=E.tostring(header,xml_declaration=True,encoding='UTF-8');b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:
   for k,v in data.items():z.writestr(k,v)
  with self.assertRaises(ValueError):f.verify(self.src.read_bytes(),b.getvalue(),self.req)
 def test_protected_header_rejected(self):
  self.src=self.write_mutated('protected.hwpx',lambda d:self.mutate_section(d,lambda r:r.find('.//'+f.P+'tc').set('protect','1')));self.reject(dict(self.req,source_sha256=f.sha(self.src),repeat_header=True,header_rows=[1]))
 def test_dryrun_and_source_unchanged(self):
  before=self.src.read_bytes();result=f.apply(self.src,self.out,self.req,True);self.assertFalse(self.out.exists());self.assertEqual(before,self.src.read_bytes());self.assertFalse(result['published'])
 def test_existing_output_refused(self):self.out.write_bytes(b'existing');self.assertRaises(ValueError,f.apply,self.src,self.out,self.req);self.assertEqual(self.out.read_bytes(),b'existing')
 def test_body_corruption_detected(self):
  f.apply(self.src,self.out,self.req);data=f.parts(self.out.read_bytes());self.mutate_section(data,lambda r:r.find('.//'+f.P+'tc/'+f.P+'cellSz').set('width','1'));b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:
   for k,v in data.items():z.writestr(k,v)
  with self.assertRaises(ValueError):f.verify(self.src.read_bytes(),b.getvalue(),self.req)
 def test_verifier_hash_bound(self):
  f.apply(self.src,self.out,self.req)
  with self.assertRaises(ValueError):f.verify(self.src.read_bytes(),self.out.read_bytes(),dict(self.req,source_sha256='0'*64))
if __name__=='__main__':unittest.main()
