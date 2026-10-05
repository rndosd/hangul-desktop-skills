from pathlib import Path
import sys,json,copy,tempfile,unittest,zipfile,io
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import safe_summary_style as s
SOURCE=Path(__file__).resolve().parents[1]/'assets/summary-rows/source.hwpx'
if not SOURCE.exists():SOURCE=Path(__file__).parent/'source.hwpx'
def mutate(data,fn):
 m=s.locate(data,1)[0];root=s.xml(m['Contents/section0.xml']);fn(root);from lxml import etree;m['Contents/section0.xml']=etree.tostring(root,xml_declaration=True,encoding='UTF-8');out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for k,v in m.items():z.writestr(k,v)
 return out.getvalue()
class Guards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.r=Path(self.tmp.name);self.src=self.r/'source.hwpx';self.src.write_bytes(SOURCE.read_bytes());self.out=self.r/'out.hwpx';self.req=dict(schema=s.SCHEMA,source_sha256=s.sha(self.src),table=1,edits=[dict(row=7,column=1,expected_texts=['소계 1'],bold=True,alignment='LEFT')])
 def tearDown(self):self.tmp.cleanup()
 def fail(self,req=None):
  with self.assertRaises((ValueError,TypeError)):s.apply(self.src,self.out,req or self.req)
  self.assertFalse(self.out.exists())
 def test_clone_preserves_existing_definitions(self):
  result=s.apply(self.src,self.out,self.req);self.assertTrue(result['checks']['oldStylesAndUnselectedCellsPreserved']);s.verify(self.src.read_bytes(),self.out.read_bytes(),self.req)
 def test_remove_bold(self):
  s.apply(self.src,self.out,self.req);new=self.r/'restored.hwpx';req=copy.deepcopy(self.req);req['source_sha256']=s.sha(self.out);req['edits'][0]['bold']=False;s.apply(self.out,new,req);s.verify(self.out.read_bytes(),new.read_bytes(),req)
 def test_dry_run(self):self.assertFalse(s.apply(self.src,self.out,self.req,True)['published']);self.assertFalse(self.out.exists())
 def test_existing_output(self):self.out.write_bytes(b'keep');self.assertRaises(ValueError,s.apply,self.src,self.out,self.req);self.assertEqual(self.out.read_bytes(),b'keep')
 def test_source_output(self):self.assertRaises(ValueError,s.apply,self.src,self.src,self.req)
 def test_stale(self):self.req['source_sha256']='0'*64;self.fail()
 def test_duplicate(self):self.req['edits']*=2;self.fail()
 def test_covered_merged(self):self.req['edits'][0]['column']=2;self.fail()
 def test_wrong_text(self):self.req['edits'][0]['expected_texts']=['소계'];self.fail()
 def test_partial_paragraphs(self):self.req['edits'][0].update(row=3,column=2,expected_texts=['현장 운영 지원 / 1차 운영 (검토 완료)']);self.fail()
 def test_multi_paragraph_runs(self):
  e=self.req['edits'][0];e.update(row=3,column=2,expected_texts=['현장 운영 지원 / 1차 운영 (검토 완료)','담당자 확인 후 집행']);result=s.apply(self.src,self.out,self.req);self.assertTrue(result['checks']['exactRequestedStylesAndNumericDisplay'])
 def test_unknown(self):self.req['edits'][0]['font_size']=8;self.fail()
 def test_unknown_root(self):self.req['auto']=True;self.fail()
 def test_bold_type(self):self.req['edits'][0]['bold']=1;self.fail()
 def test_address_bool(self):self.req['edits'][0]['row']=True;self.fail()
 def test_alignment(self):self.req['edits'][0]['alignment']='JUSTIFY';self.fail()
 def test_keep_bool(self):self.req['edits'][0]['keep_with_next']=1;self.fail()
 def test_empty_changes(self):self.req['edits'][0]={k:v for k,v in self.req['edits'][0].items() if k in ['row','column','expected_texts']};self.fail()
 def test_limit(self):self.req['edits']*=101;self.fail()
 def test_protected(self):
  data=mutate(self.src.read_bytes(),lambda r:list(r.iter(s.P+'tc'))[24].set('protect','1'));self.src.write_bytes(data);self.req['source_sha256']=s.sha(self.src);self.fail()
 def test_fixed(self):
  self.src.write_bytes(mutate(self.src.read_bytes(),lambda r:next(r.iter(s.P+'tbl')).set('noAdjust','1')));self.req['source_sha256']=s.sha(self.src);self.fail()
 def test_control(self):
  self.src.write_bytes(mutate(self.src.read_bytes(),lambda r:next(next(r.iter(s.P+'tc')).iter(s.P+'run')).append(r.makeelement(s.P+'ctrl',{}))));self.req['source_sha256']=s.sha(self.src);self.fail()
 def test_corrupt_verifier(self):
  original=s.HwpxDocument.to_bytes
  def bad(doc):
   data=original(doc);m=s.locate(data,1)[0];header=s.xml(m['Contents/header.xml']);from lxml import etree
   header.find('.//'+s.H+'charPr').set('height','800');m['Contents/header.xml']=etree.tostring(header,xml_declaration=True,encoding='UTF-8');out=io.BytesIO()
   with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for k,v in m.items():z.writestr(k,v)
   return out.getvalue()
  with patch.object(s.HwpxDocument,'to_bytes',bad):self.fail()
 def test_numeric_integration(self):
  self.req['edits']=[dict(row=2,column=3,expected_texts=['1200'],alignment='RIGHT',number_format=dict(decimal_places=1,grouping=True))];s.apply(self.src,self.out,self.req);_,_,_,t=s.locate(self.out.read_bytes(),1);self.assertEqual(s.texts(s.shape(t)[0][(1,2)]),['1,200.0'])
 def test_unsupported_rounded_number(self):self.req['edits']=[dict(row=4,column=4,expected_texts=['92.25'],number_format=dict(decimal_places=1,grouping=True))];self.fail()
 def test_numeric_multi(self):self.req['edits'][0].update(row=3,column=2,expected_texts=['현장 운영 지원 / 1차 운영 (검토 완료)','담당자 확인 후 집행'],number_format=dict(decimal_places=1,grouping=True));self.fail()
 def test_keep_with_next_request(self):self.req['edits'][0].update(keep_with_next=True);s.apply(self.src,self.out,self.req)
class Numbers(unittest.TestCase):
 def test_values(self):
  for before,expected in [('1200','1,200.0'),('2400.5','2,400.5'),('0','0.0'),('-50','-50.0'),('1,234.50','1,234.5')]:self.assertEqual(s.formatted_number(before,dict(decimal_places=1,grouping=True)),expected)
 def test_invalid(self):
  for value in ['12,34','1 234','1.200,5','12%','100원','1e3','NaN','']:
   with self.assertRaises(ValueError):s.formatted_number(value,dict(decimal_places=1,grouping=True))
 def test_rounding_refused(self):self.assertRaises(ValueError,s.formatted_number,'1.234',dict(decimal_places=2,grouping=True))
 def test_bool_decimals(self):self.assertRaises(ValueError,s.formatted_number,'12',dict(decimal_places=True,grouping=True))
 def test_precision_bound(self):self.assertRaises(ValueError,s.formatted_number,'12',dict(decimal_places=5,grouping=True))
 def test_grouping_bool(self):self.assertRaises(ValueError,s.formatted_number,'12',dict(decimal_places=2,grouping=1))
 def test_unknown_option(self):self.assertRaises(ValueError,s.formatted_number,'12',dict(decimal_places=2,grouping=True,round=True))
if __name__=='__main__':unittest.main()


