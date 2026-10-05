from pathlib import Path
import sys,unittest,tempfile,copy,zipfile,io
from unittest.mock import patch
from lxml import etree as E
sys.path.append(str(Path(__file__).resolve().parent))
import safe_word_wrap as w
import safe_table_columns as c
from safe_edit import candidates,digest
from safe_cell_layout import parts,P,H,xml
class WordGuards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.src=Path(__file__).resolve().parents[1]/'assets/word-flow/source.hwpx';self.out=Path(self.tmp.name)/'out.hwpx';self.text='점검 자료를 확인하고 사전검토결과보고서를 제출한다.';t=candidates(self.src,self.text,digest(self.src))[0];self.req=dict(schema=w.SCHEMA,source_sha256=digest(self.src),targets=[dict(part=t['part'],paragraph_path=list(t['paragraph_path']),expected_text=self.text,korean='WORD',latin='WORD',reason='어절 보존')])
 def tearDown(self):self.tmp.cleanup()
 def reject(self,req):
  self.assertRaises(ValueError,w.apply,self.src,self.out,req);self.assertFalse(self.out.exists())
 def change(self,k,v):
  req=copy.deepcopy(self.req);req['targets'][0][k]=v;return req
 def test_clone_and_other_styles_exact(self):
  w.apply(self.src,self.out,self.req);bm=parts(self.src.read_bytes());am=parts(self.out.read_bytes());bh=xml(bm['Contents/header.xml']);ah=xml(am['Contents/header.xml']);old={p.get('id'):p for p in bh.iter(H+'paraPr')};new={p.get('id'):p for p in ah.iter(H+'paraPr')};self.assertTrue(all(w.shape(n)==w.shape(new[k]) for k,n in old.items()));self.assertEqual(len(new),len(old)+1)
 def test_multi_paragraph_native_bullets_preserved(self):
  text='검토 의견을 담당자에게 전달하고 확인 내용을 기록한다.';t=candidates(self.src,text,digest(self.src))[0];req=copy.deepcopy(self.req);req['targets'].append(dict(req['targets'][0],part=t['part'],paragraph_path=list(t['paragraph_path']),expected_text=text));receipt=w.apply(self.src,self.out,req);self.assertEqual(len(receipt['changes']),2)
 def test_dryrun(self):self.assertFalse(w.apply(self.src,self.out,self.req,True)['published']);self.assertFalse(self.out.exists())
 def test_exclusive(self):self.out.write_bytes(b'keep');self.assertRaises(ValueError,w.apply,self.src,self.out,self.req);self.assertEqual(self.out.read_bytes(),b'keep')
 def test_stale_hash(self):self.reject(dict(self.req,source_sha256='0'*64))
 def test_duplicate(self):self.reject(dict(self.req,targets=self.req['targets']*2))
 def test_negative_path(self):self.reject(self.change('paragraph_path',[-1]))
 def test_boolean_path(self):self.reject(self.change('paragraph_path',[True]))
 def test_float_path(self):self.reject(self.change('paragraph_path',[1.0]))
 def test_empty_path(self):self.reject(self.change('paragraph_path',[]))
 def test_wrong_text(self):self.reject(self.change('expected_text','없는 문구'))
 def test_partial_text(self):self.reject(self.change('expected_text','점검 자료'))
 def test_empty_text(self):self.reject(self.change('expected_text',''))
 def test_missing_reason(self):self.reject(self.change('reason',''))
 def test_enum_only(self):self.reject(self.change('korean','CHARACTER'))
 def test_hyphen_not_allowed(self):self.reject(self.change('latin','HYPHENATION'))
 def test_unknown_key(self):self.reject(dict(self.req,font=9))
 def test_unknown_target_key(self):req=copy.deepcopy(self.req);req['targets'][0]['tracking']=-9;self.reject(req)
 def test_empty_targets(self):self.reject(dict(self.req,targets=[]))
 def test_too_many_targets(self):self.reject(dict(self.req,targets=self.req['targets']*21))
 def protected_source(self,flag):
  m=parts(self.src.read_bytes());r=xml(m['Contents/section0.xml']);node=r
  for i in self.req['targets'][0]['paragraph_path']:node=node[i]
  owner=next(p for p in node.iterancestors() if p.tag==P+('tc' if flag=='protect' else 'tbl'));owner.set(flag,'1');m['Contents/section0.xml']=E.tostring(r);self.src=Path(self.tmp.name)/'protected.hwpx'
  with zipfile.ZipFile(self.src,'x') as z:
   for k,v in m.items():z.writestr(k,v)
  self.req['source_sha256']=digest(self.src)
 def test_protected_cell_refused(self):self.protected_source('protect');self.reject(self.req)
 def test_fixed_table_refused(self):self.protected_source('noAdjust');self.reject(self.req)
 def test_style_corruption_refuses_publication(self):
  original=w.HwpxDocument.to_bytes
  def wrong(doc):
   m=parts(original(doc));root=xml(m['Contents/header.xml']);root.find('.//'+H+'charPr').set('height','888');m['Contents/header.xml']=E.tostring(root);b=io.BytesIO()
   with zipfile.ZipFile(b,'w') as z:
    for k,v in m.items():z.writestr(k,v)
   return b.getvalue()
  with patch.object(w.HwpxDocument,'to_bytes',wrong):self.reject(self.req)
class ColumnGuards(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.src=Path(__file__).resolve().parents[1]/'assets/word-flow/source.hwpx';self.out=Path(self.tmp.name)/'out.hwpx';self.req=dict(schema=c.SCHEMA,source_sha256=digest(self.src),table=1,widths_mm=[32,138])
 def tearDown(self):self.tmp.cleanup()
 def reject(self,req):self.assertRaises(ValueError,c.apply,self.src,self.out,req);self.assertFalse(self.out.exists())
 def mutate(self,callback):
  m=parts(self.src.read_bytes());r=xml(m['Contents/section0.xml']);callback(r);m['Contents/section0.xml']=E.tostring(r);self.src=Path(self.tmp.name)/'src.hwpx'
  with zipfile.ZipFile(self.src,'x') as z:
   for k,v in m.items():z.writestr(k,v)
  self.req['source_sha256']=digest(self.src)
 def test_multiple_paragraphs_and_bullet_styles_preserved(self):
  receipt=c.apply(self.src,self.out,self.req);self.assertTrue(receipt['checks']['allParagraphsRunsListsStylesBordersPreserved']);self.assertTrue(c.verify(self.src.read_bytes(),self.out.read_bytes(),self.req)['exactColumnWidths'])
 def test_dryrun(self):self.assertFalse(c.apply(self.src,self.out,self.req,True)['published']);self.assertFalse(self.out.exists())
 def test_stale(self):self.reject(dict(self.req,source_sha256='0'*64))
 def test_width_total(self):self.reject(dict(self.req,widths_mm=[40,140]))
 def test_width_count(self):self.reject(dict(self.req,widths_mm=[170]))
 def test_width_nan(self):self.reject(dict(self.req,widths_mm=[float('nan'),138]))
 def test_width_boolean(self):self.reject(dict(self.req,widths_mm=[True,169]))
 def test_usable_width(self):self.reject(dict(self.req,widths_mm=[5,165]))
 def test_no_change(self):self.reject(dict(self.req,widths_mm=[95,75]))
 def test_unknown_key(self):self.reject(dict(self.req,height=5))
 def test_protected_table(self):self.mutate(lambda r:r.find('.//'+P+'tbl').set('lock','1'));self.reject(self.req)
 def test_fixed_table(self):self.mutate(lambda r:r.find('.//'+P+'tbl').set('noAdjust','1'));self.reject(self.req)
 def test_protected_cell(self):self.mutate(lambda r:r.find('.//'+P+'tc').set('protect','1'));self.reject(self.req)
 def test_inline(self):self.mutate(lambda r:r.find('.//'+P+'tbl/'+P+'pos').set('treatAsChar','1'));self.reject(self.req)
 def test_rich_cell(self):self.mutate(lambda r:E.SubElement(r.find('.//'+P+'tc/'+P+'subList/'+P+'p/'+P+'run'),P+'ctrl'));self.reject(self.req)
 def test_geometry_corruption_detected(self):
  c.apply(self.src,self.out,self.req);m=parts(self.out.read_bytes());r=xml(m['Contents/section0.xml']);r.find('.//'+P+'tc/'+P+'cellSz').set('height','1');m['Contents/section0.xml']=E.tostring(r);b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:
   for k,v in m.items():z.writestr(k,v)
  self.assertRaises(ValueError,c.verify,self.src.read_bytes(),b.getvalue(),self.req)
class TrackingGuards(unittest.TestCase):
 def setUp(self):
  from safe_format import SCHEMA
  self.tmp=tempfile.TemporaryDirectory();self.src=Path(__file__).resolve().parents[1]/'assets/word-flow/fit.hwpx';self.out=Path(self.tmp.name)/'out.hwpx';text='점검 자료를 확인하고 사전검토결과보고서를 제출한다.';t=candidates(self.src,text,digest(self.src))[0];self.req=dict(schema=SCHEMA,source_sha256=digest(self.src),targets=[dict(part=t['part'],paragraph_path=list(t['paragraph_path']),expected_text=text,letter_spacing=-1,ratio=100,reason='minimal tracking fit trial')])
 def tearDown(self):self.tmp.cleanup()
 def test_existing_formatter_preserves_font_size_and_ratio(self):
  from safe_format import apply_format
  r=apply_format(self.src,self.out,self.req);self.assertFalse(r['font_size_reduced']);self.assertTrue(r['all_unrequested_format_and_text_preserved']);self.assertTrue(all(c['after_ratio']==c['before_ratio']==100 for c in r['changes']))
 def test_excessive_compression_rejected(self):
  from safe_format import apply_format
  self.req['targets'][0]['letter_spacing']=-6;self.assertRaises(ValueError,apply_format,self.src,self.out,self.req);self.assertFalse(self.out.exists())
 def test_tracking_wrong_paragraph_rejected(self):
  from safe_format import apply_format
  self.req['targets'][0]['expected_text']='wrong paragraph';self.assertRaises(ValueError,apply_format,self.src,self.out,self.req);self.assertFalse(self.out.exists())
 def test_tracking_boolean_rejected(self):
  from safe_format import apply_format
  self.req['targets'][0]['letter_spacing']=True;self.assertRaises(ValueError,apply_format,self.src,self.out,self.req);self.assertFalse(self.out.exists())
if __name__=='__main__':unittest.main()
