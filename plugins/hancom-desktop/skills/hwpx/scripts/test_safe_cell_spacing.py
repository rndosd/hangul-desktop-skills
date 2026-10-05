from pathlib import Path
import unittest,tempfile,json,copy,io,zipfile,math
from lxml import etree as E
import safe_cell_spacing as f
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.src=Path(__file__).resolve().parents[1]/'assets/cell-spacing/source.hwpx';self.out=Path(self.tmp.name)/'new.hwpx';self.req=dict(schema=f.SCHEMA,source_sha256=f.sha(self.src),table=1,edits=[dict(row=2,column=1,vertical_align='TOP')])
 def tearDown(self):self.tmp.cleanup()
 def reject(self,req):
  with self.assertRaises(ValueError):f.apply(self.src,self.out,req)
  self.assertFalse(self.out.exists())
 def test_top_center_bottom(self):
  for v in ['TOP','CENTER','BOTTOM']:
   p=Path(self.tmp.name)/(v+'.hwpx');req=dict(self.req,edits=[dict(row=2,column=1,vertical_align=v)]);r=f.apply(self.src,p,req);self.assertTrue(r['checks']['allActiveStylesUnchanged'])
 def test_padding_multiple_paragraphs_and_runs(self):
  r=f.apply(self.src,self.out,dict(self.req,edits=[dict(row=4,column=2,margins_mm=dict(left=4,right=3,top=2,bottom=2))]));self.assertTrue(r['checks']['paragraphsRunsAndNativeBreaksPreserved'])
 def test_native_linebreak_tail_preserved(self):
  before=self.src.read_bytes();f.apply(self.src,self.out,self.req);_,_,b,t=f.locate(before,1);_,_,a,t=f.locate(self.out.read_bytes(),1);self.assertEqual([n.tail for n in b.iter(f.P+'lineBreak')],[n.tail for n in a.iter(f.P+'lineBreak')])
 def test_merged_anchor_spacing(self):f.apply(self.src,self.out,dict(self.req,edits=[dict(row=5,column=2,vertical_align='BOTTOM',margins_mm={'left':3})]))
 def test_covered_merged_coordinate_refused(self):self.reject(dict(self.req,edits=[dict(row=5,column=3,vertical_align='TOP')]))
 def test_dry_run(self):f.apply(self.src,self.out,self.req,True);self.assertFalse(self.out.exists())
 def test_stale_hash(self):self.reject(dict(self.req,source_sha256='0'*64))
 def test_standalone_verifier_rejects_wrong_hash(self):
  with self.assertRaises(ValueError):f.verify(self.src.read_bytes(),self.src.read_bytes(),dict(self.req,source_sha256='0'*64))
 def test_duplicate_cell(self):self.reject(dict(self.req,edits=self.req['edits']*2))
 def test_bool_coordinate(self):self.reject(dict(self.req,edits=[dict(row=True,column=1,vertical_align='TOP')]))
 def test_negative_margin(self):self.reject(dict(self.req,edits=[dict(row=2,column=1,margins_mm={'left':-1})]))
 def test_bool_margin(self):self.reject(dict(self.req,edits=[dict(row=2,column=1,margins_mm={'left':True})]))
 def test_nonfinite_margin(self):self.reject(dict(self.req,edits=[dict(row=2,column=1,margins_mm={'left':float('nan')})]))
 def test_unbounded_margin(self):self.reject(dict(self.req,edits=[dict(row=2,column=1,margins_mm={'left':11})]))
 def test_wrong_margin_side(self):self.reject(dict(self.req,edits=[dict(row=2,column=1,margins_mm={'outside':2})]))
 def test_empty_edit(self):self.reject(dict(self.req,edits=[dict(row=2,column=1)]))
 def test_squeeze_not_authorable(self):self.reject(dict(self.req,edits=[dict(row=2,column=1,line_wrap='SQUEEZE')]))
 def test_plain_text_write_not_allowed(self):self.reject(dict(self.req,edits=[dict(row=2,column=1,text='changed')]))
 def test_does_not_overwrite(self):
  self.out.write_bytes(b'keep')
  with self.assertRaises(ValueError):f.apply(self.src,self.out,self.req)
  self.assertEqual(self.out.read_bytes(),b'keep')
 def test_original_unchanged(self):
  old=f.sha(self.src);f.apply(self.src,self.out,self.req);self.assertEqual(f.sha(self.src),old)
 def mutate(self,data,fn):
  m=f.parts(data);r=f.xml(m['Contents/section0.xml']);fn(r);m['Contents/section0.xml']=E.tostring(r,encoding='utf-8')
  buf=io.BytesIO()
  with zipfile.ZipFile(buf,'w') as z:
   for k,v in m.items():z.writestr(k,v)
  return buf.getvalue()
 def test_corrupted_linebreak_tail_refused(self):
  f.apply(self.src,self.out,self.req);a=self.mutate(self.out.read_bytes(),lambda r:setattr(next(r.iter(f.P+'lineBreak')),'tail','lost text'))
  with self.assertRaises(ValueError):f.verify(self.src.read_bytes(),a,self.req)
 def test_corrupted_run_style_refused(self):
  f.apply(self.src,self.out,self.req);a=self.mutate(self.out.read_bytes(),lambda r:next(r.iter(f.P+'run')).set('charPrIDRef','999'))
  with self.assertRaises(ValueError):f.verify(self.src.read_bytes(),a,self.req)
 def test_inherited_margins_keep_unrequested_sides(self):
  _,_,r,t=f.locate(self.src.read_bytes(),1);cs,g=f.shape(t);c=cs[1,0];c.set('hasMargin','0');c.find(f.P+'cellMargin').set('right','9999');values=f.effective(c,t);spec=f.edits(dict(self.req,edits=[dict(row=2,column=1,margins_mm={'left':5})]),t)[1,0];self.assertEqual(spec['margins']['right'],values['right']);self.assertEqual(spec['margins']['bottom'],values['bottom'])
 def test_protected_target_refused(self):
  _,_,r,t=f.locate(self.src.read_bytes(),1);cs,g=f.shape(t);cs[1,0].set('protect','1')
  with self.assertRaises(ValueError):f.edits(self.req,t)
 def test_fixed_size_wrap_refused(self):
  _,_,r,t=f.locate(self.src.read_bytes(),1);t.find(f.P+'sz').set('protect','1')
  with self.assertRaises(ValueError):f.edits(dict(self.req,edits=[dict(row=4,column=2,line_wrap='BREAK')]),t)
 def test_nested_control_refused(self):
  _,_,r,t=f.locate(self.src.read_bytes(),1);cs,g=f.shape(t);p=cs[1,0].find('.//'+f.P+'p');p.find(f.P+'run').append(p.makeelement(f.P+'ctrl',{}))
  with self.assertRaises(ValueError):f.shape(t)
if __name__=='__main__':unittest.main(verbosity=2)
