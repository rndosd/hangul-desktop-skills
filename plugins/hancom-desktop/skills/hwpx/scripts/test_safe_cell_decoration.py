from pathlib import Path
import unittest,tempfile,json,copy,io,zipfile
from lxml import etree as E
import safe_cell_decoration as f
class Guards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.src=Path(__file__).resolve().parents[1]/'assets/cell-decoration/source.hwpx';self.out=Path(self.tmp.name)/'candidate.hwpx';self.req=dict(schema=f.SCHEMA,source_sha256=f.sha(self.src),table=1,edits=[dict(row=3,column=1,borders={'right':{'type':'DOT','width_mm':.5,'color':'#303030'}})])
 def tearDown(self):self.tmp.cleanup()
 def reject(self,req):
  with self.assertRaises(ValueError):f.apply(self.src,self.out,req)
  self.assertFalse(self.out.exists())
 def styles(self,path):
  m=f.parts(Path(path).read_bytes());_,_,_,t=f.locate(Path(path).read_bytes(),1);cs,g=f.shape(t);_,_,styles=f.header(m);return cs,styles
 def test_shared_edge_mirrored(self):
  r=f.apply(self.src,self.out,self.req);self.assertEqual([(v['row'],v['column'],v['explicit']) for v in r['affectedCells']],[(3,1,True),(3,2,False)]);cs,styles=self.styles(self.out);self.assertEqual(dict(styles[cs[2,0].get('borderFillIDRef')].find(f.H+'rightBorder').attrib),dict(styles[cs[2,1].get('borderFillIDRef')].find(f.H+'leftBorder').attrib))
 def test_shared_edge_conflict_refused(self):self.reject(dict(self.req,edits=self.req['edits']+[dict(row=3,column=2,borders={'left':{'type':'SOLID'}})]))
 def test_partial_merged_neighbor_refused(self):self.reject(dict(self.req,edits=[dict(row=4,column=2,borders={'bottom':{'type':'DOT'}})]))
 def test_full_merged_neighbor_accepted(self):
  f.apply(self.src,self.out,dict(self.req,edits=[dict(row=4,column=x,borders={'bottom':{'type':'DOT'}}) for x in [2,3]]));cs,styles=self.styles(self.out);self.assertEqual(styles[cs[4,1].get('borderFillIDRef')].find(f.H+'topBorder').get('type'),'DOT')
 def test_none_keeps_other_sides(self):
  old,styles=self.styles(self.src);f.apply(self.src,self.out,dict(self.req,edits=[dict(row=3,column=1,borders={'right':{'type':'NONE'}})]));cs,changed=self.styles(self.out);a=styles[old[2,0].get('borderFillIDRef')];b=changed[cs[2,0].get('borderFillIDRef')]
  for side in ['topBorder','bottomBorder','leftBorder']:self.assertEqual(f.snapshot(a.find(f.H+side)),f.snapshot(b.find(f.H+side)))
 def test_all_diagonal_directions(self):
  for direction in ['NW_SE','NE_SW','CROSS','NONE']:
   p=Path(self.tmp.name)/(direction+'.hwpx');f.apply(self.src,p,dict(self.req,edits=[dict(row=2,column=1,diagonal={'direction':direction,'type':'SOLID','width_mm':.3})]));cs,st=self.styles(p);s=st[cs[1,0].get('borderFillIDRef')];self.assertEqual(s.find(f.H+'slash').get('type'),'CENTER' if direction in ['NE_SW','CROSS'] else 'NONE');self.assertEqual(s.find(f.H+'backSlash').get('type'),'CENTER' if direction in ['NW_SE','CROSS'] else 'NONE')
 def test_merged_anchor_diagonal(self):f.apply(self.src,self.out,dict(self.req,edits=[dict(row=5,column=2,diagonal={'direction':'NW_SE'})]))
 def test_covered_anchor_refused(self):self.reject(dict(self.req,edits=[dict(row=5,column=3,fill_color='#FFFFFF')]))
 def test_same_fill_preserves_different_borders(self):
  first=Path(self.tmp.name)/'first.hwpx';f.apply(self.src,first,self.req);old,st=self.styles(first);req=dict(self.req,source_sha256=f.sha(first),edits=[dict(row=3,column=x,fill_color='#EEEEEE') for x in [1,3]]);f.apply(first,self.out,req);cs,new=self.styles(self.out)
  for a in [(2,0),(2,2)]:
   before=st[old[a].get('borderFillIDRef')];after=new[cs[a].get('borderFillIDRef')]
   for side in f.SIDES.values():self.assertEqual(f.snapshot(before.find(f.H+side)),f.snapshot(after.find(f.H+side)))
  self.assertNotEqual(cs[2,0].get('borderFillIDRef'),cs[2,2].get('borderFillIDRef'))
 def test_native_omitted_diagonal_can_be_enabled(self):
  data=self.mutate(self.src.read_bytes(),'Contents/header.xml',lambda r:[n.getparent().remove(n) for n in list(r.iter(f.H+'diagonal'))]);source=Path(self.tmp.name)/'no-diag.hwpx';source.write_bytes(data);req=dict(self.req,source_sha256=f.sha(source),edits=[dict(row=2,column=1,diagonal={'direction':'NW_SE'})]);f.apply(source,self.out,req);cs,styles=self.styles(self.out);self.assertEqual(styles[cs[1,0].get('borderFillIDRef')].find(f.H+'backSlash').get('type'),'CENTER')
 def test_fill_removal_retains_border(self):
  first=Path(self.tmp.name)/'filled.hwpx';req=dict(self.req,edits=[dict(row=3,column=1,fill_color='#EEEEEE')]);f.apply(self.src,first,req);f.apply(first,self.out,dict(req,source_sha256=f.sha(first),edits=[dict(row=3,column=1,fill_color=None)]));cs,st=self.styles(self.out);self.assertIsNone(st[cs[2,0].get('borderFillIDRef')].find(f.C+'fillBrush'))
 def test_invalid_color(self):self.reject(dict(self.req,edits=[dict(row=3,column=1,fill_color='red')]))
 def test_nonstandard_width(self):self.reject(dict(self.req,edits=[dict(row=3,column=1,borders={'top':{'width_mm':.333}})]))
 def test_bool_width(self):self.reject(dict(self.req,edits=[dict(row=3,column=1,borders={'top':{'width_mm':True}})]))
 def test_bad_side(self):self.reject(dict(self.req,edits=[dict(row=3,column=1,borders={'inside':{'type':'DOT'}})]))
 def test_bad_line_type(self):self.reject(dict(self.req,edits=[dict(row=3,column=1,borders={'top':{'type':'MAGIC'}})]))
 def test_hidden_enabled_diagonal(self):self.reject(dict(self.req,edits=[dict(row=3,column=1,diagonal={'direction':'CROSS','type':'NONE'})]))
 def test_empty_edit(self):self.reject(dict(self.req,edits=[dict(row=3,column=1)]))
 def test_text_write_refused(self):self.reject(dict(self.req,edits=[dict(row=3,column=1,text='change')]))
 def test_stale_hash(self):self.reject(dict(self.req,source_sha256='0'*64))
 def test_bool_coordinate(self):self.reject(dict(self.req,edits=[dict(row=True,column=1,fill_color='#EEEEEE')]))
 def test_duplicate_edit(self):self.reject(dict(self.req,edits=self.req['edits']*2))
 def test_dry_run(self):f.apply(self.src,self.out,self.req,True);self.assertFalse(self.out.exists())
 def test_no_overwrite(self):
  self.out.write_bytes(b'keep')
  with self.assertRaises(ValueError):f.apply(self.src,self.out,self.req)
  self.assertEqual(self.out.read_bytes(),b'keep')
 def test_source_unchanged(self):
  old=f.sha(self.src);f.apply(self.src,self.out,self.req);self.assertEqual(f.sha(self.src),old)
 def mutate(self,data,member,fn):
  m=f.parts(data);root=f.xml(m[member]);fn(root);m[member]=E.tostring(root,encoding='utf8');buf=io.BytesIO()
  with zipfile.ZipFile(buf,'w') as z:
   for k,v in m.items():z.writestr(k,v)
  return buf.getvalue()
 def test_original_style_mutation_detected(self):
  f.apply(self.src,self.out,self.req);changed=self.mutate(self.out.read_bytes(),'Contents/header.xml',lambda r:next(r.iter(f.H+'topBorder')).set('width','9 mm'))
  with self.assertRaises(ValueError):f.verify(self.src.read_bytes(),changed,self.req)
 def test_non_target_cell_mutation_detected(self):
  f.apply(self.src,self.out,self.req);changed=self.mutate(self.out.read_bytes(),'Contents/section0.xml',lambda r:next(r.iter(f.P+'cellMargin')).set('left','999'))
  with self.assertRaises(ValueError):f.verify(self.src.read_bytes(),changed,self.req)
 def test_multiple_paragraphs_and_bold_retained(self):
  r=f.apply(self.src,self.out,dict(self.req,edits=[dict(row=4,column=2,fill_color='#EEEEEE')]));self.assertTrue(r['checks']['cellTextRunsAndLineBreakTailsEqual'])
 def test_native_linebreak_tails_preserved(self):
  src=self.src.parents[1]/'cell-spacing/source.hwpx';req=dict(self.req,source_sha256=f.sha(src),edits=[dict(row=2,column=1,fill_color='#EEEEEE')]);f.apply(src,self.out,req);before=f.xml(f.parts(src.read_bytes())['Contents/section0.xml']);after=f.xml(f.parts(self.out.read_bytes())['Contents/section0.xml']);self.assertEqual([(n.text,n.tail) for n in before.iter(f.P+'lineBreak')],[(n.text,n.tail) for n in after.iter(f.P+'lineBreak')])
 def test_verifier_hash_binding(self):
  with self.assertRaises(ValueError):f.verify(self.src.read_bytes(),self.src.read_bytes(),dict(self.req,source_sha256='0'*64))
 def test_protected_neighbor_refused(self):
  before=self.mutate(self.src.read_bytes(),'Contents/section0.xml',lambda r:f.shape(next(r.iter(f.P+'tbl')))[0][2,1].set('protect','1'));req=dict(self.req,source_sha256=__import__('hashlib').sha256(before).hexdigest())
  with self.assertRaises(ValueError):f.plan(before,req)
if __name__=='__main__':unittest.main(verbosity=2)
