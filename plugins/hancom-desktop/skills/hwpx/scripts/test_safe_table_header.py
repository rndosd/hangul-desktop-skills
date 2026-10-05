from pathlib import Path
import unittest,tempfile,zipfile,io,copy
from lxml import etree as E
import safe_table_header as f
from safe_cell_layout import parts
class HeaderGuards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.src=Path(__file__).resolve().parents[1]/'assets/merged-headers/two.hwpx';self.out=Path(self.tmp.name)/'out.hwpx';self.req=dict(schema=f.SCHEMA,source_sha256=f.sha(self.src),table=1,header_rows=[1,2],repeat_header=True)
 def tearDown(self):self.tmp.cleanup()
 def reject(self,req):
  with self.assertRaises(ValueError):f.apply(self.src,self.out,req)
  self.assertFalse(self.out.exists())
 def packed(self,m):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
   for k,v in m.items():z.writestr(k,v)
  return b.getvalue()
 def mutation(self,data,member,callback):
  m=parts(data);r=f.xml(m[member]);callback(r);m[member]=E.tostring(r,xml_declaration=True,encoding='UTF-8');return self.packed(m)
 def source_mutation(self,callback):
  data=self.mutation(self.src.read_bytes(),'Contents/section0.xml',callback);self.src=Path(self.tmp.name)/'source.hwpx';self.src.write_bytes(data);self.req['source_sha256']=f.sha(self.src)
 def test_repeat_all_owned_header_cells(self):
  f.apply(self.src,self.out,self.req);_,_,_,t=f.locate(self.out.read_bytes(),1);cs,_=f.shape(t);self.assertTrue(all(c.get('header')=='1' for a,c in cs.items() if a[0]<2));self.assertTrue(all(c.get('header')=='0' for a,c in cs.items() if a[0]>=2));self.assertTrue(f.verify(self.src.read_bytes(),self.out.read_bytes(),self.req)['bodyCellsExact'])
 def test_vertical_merge_height_sum(self):
  req=dict(self.req,row_heights_mm=[10,12]);f.apply(self.src,self.out,req);_,_,_,t=f.locate(self.out.read_bytes(),1);cs,_=f.shape(t);self.assertEqual(cs[0,0].find(f.P+'cellSz').get('height'),str(round(10*7200/25.4)+round(12*7200/25.4)));self.assertEqual(cs[1,1].find(f.P+'cellSz').get('height'),str(round(12*7200/25.4)))
 def test_three_tiers(self):
  self.src=self.src.with_name('three.hwpx');req=dict(self.req,source_sha256=f.sha(self.src),header_rows=[1,2,3],alignment='CENTER',vertical_align='CENTER',row_heights_mm=[10,11,12]);f.apply(self.src,self.out,req);self.assertTrue(f.verify(self.src.read_bytes(),self.out.read_bytes(),req)['mergeGridAndWidthsPreserved'])
 def test_partial_margin_sides(self):
  f.apply(self.src,self.out,dict(self.req,margins_mm={'left':2}));_,_,_,old=f.locate(self.src.read_bytes(),1);_,_,_,new=f.locate(self.out.read_bytes(),1);bc,_=f.shape(old);ac,_=f.shape(new);self.assertEqual(bc[0,0].find(f.P+'cellMargin').get('right'),ac[0,0].find(f.P+'cellMargin').get('right'))
 def test_disable_prefix_markers(self):
  f.apply(self.src,self.out,dict(self.req,repeat_header=False));_,_,_,t=f.locate(self.out.read_bytes(),1);self.assertTrue(all(c.get('header')=='0' for c in t.iter(f.P+'tc')))
 def test_dryrun_no_publish(self):
  before=self.src.read_bytes();receipt=f.apply(self.src,self.out,self.req,True);self.assertFalse(receipt['published']);self.assertFalse(self.out.exists());self.assertEqual(before,self.src.read_bytes())
 def test_exclusive_output(self):
  self.out.write_bytes(b'keep');self.assertRaises(ValueError,f.apply,self.src,self.out,self.req);self.assertEqual(self.out.read_bytes(),b'keep')
 def test_stale_hash(self):self.reject(dict(self.req,source_sha256='0'*64))
 def test_boolean_row(self):self.reject(dict(self.req,header_rows=[True,2]))
 def test_boolean_table(self):self.reject(dict(self.req,table=True))
 def test_noncontiguous_header(self):self.reject(dict(self.req,header_rows=[1,3]))
 def test_lower_only_header(self):self.reject(dict(self.req,header_rows=[2]))
 def test_four_tiers(self):self.reject(dict(self.req,header_rows=[1,2,3,4]))
 def test_empty_changes(self):self.reject({k:v for k,v in self.req.items() if k!='repeat_header'})
 def test_unknown_property(self):self.reject(dict(self.req,font_size=7))
 def test_repeat_integer(self):self.reject(dict(self.req,repeat_header=1))
 def test_alignment_invalid(self):self.reject(dict(self.req,alignment='JUSTIFY'))
 def test_vertical_invalid(self):self.reject(dict(self.req,vertical_align='BASELINE'))
 def test_heights_count(self):self.reject(dict(self.req,row_heights_mm=[10]))
 def test_heights_boolean(self):self.reject(dict(self.req,row_heights_mm=[True,10]))
 def test_heights_nan(self):self.reject(dict(self.req,row_heights_mm=[float('nan'),10]))
 def test_heights_oversize(self):self.reject(dict(self.req,row_heights_mm=[31,10]))
 def test_heights_too_small(self):self.reject(dict(self.req,row_heights_mm=[4,10]))
 def test_margins_boolean(self):self.reject(dict(self.req,margins_mm={'left':True}))
 def test_margins_negative(self):self.reject(dict(self.req,margins_mm={'left':-1}))
 def test_margin_unknown(self):self.reject(dict(self.req,margins_mm={'inside':2}))
 def test_insufficient_width(self):
  self.src=self.src.with_name('three.hwpx');self.req.update(source_sha256=f.sha(self.src),header_rows=[1,2,3]);self.reject(dict(self.req,margins_mm={'left':10,'right':10}))
 def test_insufficient_height(self):self.reject(dict(self.req,row_heights_mm=[5,5],margins_mm={'top':3,'bottom':3}))
 def test_cross_header_body_merge(self):self.reject(dict(self.req,header_rows=[1]))
 def test_merged_body(self):
  from hwpx import HwpxDocument
  with HwpxDocument.open(self.src) as doc:
   doc.tables.all[0].merge_cells(2,1,2,2);self.src=Path(self.tmp.name)/'body-merge.hwpx';doc.save_to_path(self.src)
  self.req['source_sha256']=f.sha(self.src);self.reject(self.req)
 def test_fixed_table(self):
  self.source_mutation(lambda r:r.find('.//'+f.P+'tbl').set('noAdjust','1'));self.reject(self.req)
 def test_inline_table(self):
  self.source_mutation(lambda r:r.find('.//'+f.P+'tbl/'+f.P+'pos').set('treatAsChar','1'));self.reject(self.req)
 def test_cell_split_mode(self):
  self.source_mutation(lambda r:r.find('.//'+f.P+'tbl').set('pageBreak','CELL'));self.reject(self.req)
 def test_protected_header(self):
  self.source_mutation(lambda r:r.find('.//'+f.P+'tc').set('protect','1'));self.reject(self.req)
 def test_native_linebreak_tail_preserved(self):
  def change(root):
   text=root.find('.//'+f.P+'tc/'+f.P+'subList/'+f.P+'p/'+f.P+'run/'+f.P+'t');text.text='first';node=E.SubElement(text,f.P+'lineBreak');node.tail='last'
  self.source_mutation(change);f.apply(self.src,self.out,self.req);self.assertTrue(f.verify(self.src.read_bytes(),self.out.read_bytes(),self.req)['allTextRunsBreakTailsAndControlsPreserved'])
 def test_absolute_anchor_refused(self):
  self.source_mutation(lambda r:r.find('.//'+f.P+'tbl/'+f.P+'pos').set('vertRelTo','PAGE'));self.reject(self.req)
 def test_existing_extra_header_marker_refused(self):
  self.source_mutation(lambda r:r.findall('.//'+f.P+'tc')[8].set('header','1'));self.reject(self.req)
 def test_rich_cell(self):
  self.source_mutation(lambda r:E.SubElement(r.find('.//'+f.P+'tc/'+f.P+'subList/'+f.P+'p/'+f.P+'run'),f.P+'ctrl'));self.reject(self.req)
 def corruption(self,member,callback):
  f.apply(self.src,self.out,self.req);after=self.mutation(self.out.read_bytes(),member,callback)
  with self.assertRaises(ValueError):f.verify(self.src.read_bytes(),after,self.req)
 def test_detect_body_text_corruption(self):self.corruption('Contents/section0.xml',lambda r:r.findall('.//'+f.P+'tc')[8].find('.//'+f.P+'t').__setattr__('text','corrupt'))
 def test_detect_border_corruption(self):self.corruption('Contents/section0.xml',lambda r:r.find('.//'+f.P+'tc').set('borderFillIDRef','999'))
 def test_detect_non_target_style_corruption(self):self.corruption('Contents/header.xml',lambda r:r.find('.//'+f.H+'charPr').set('height','777'))
 def test_detect_geometry_corruption(self):self.corruption('Contents/section0.xml',lambda r:r.find('.//'+f.P+'tc/'+f.P+'cellSz').set('width','7'))
 def test_detect_non_target_section_corruption(self):self.corruption('Contents/section0.xml',lambda r:r.find(f.P+'p').set('id','999'))
if __name__=='__main__':unittest.main()
