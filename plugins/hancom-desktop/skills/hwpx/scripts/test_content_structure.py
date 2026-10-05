from pathlib import Path
import os,sys,copy,tempfile,unittest,io,zipfile
from unittest.mock import patch
script_root=Path(__file__).resolve().parent
if not (script_root/'safe_cell_layout.py').exists():sys.path.insert(0,str(Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'skills/hwpx/scripts'))
import content_structure as c
import safe_row_heights as h
root=Path(__file__).resolve().parents[1]/'assets/content-structure'
if not root.exists():root=Path('outputs/content-structure').resolve()
SOURCE=root/'source.hwpx'
if not SOURCE.exists():SOURCE=root/'baseline/saved.hwpx'
def mutate(data,fn):
 m=c.parts(data);r=c.xml(m['Contents/section0.xml']);fn(r);from lxml import etree;m['Contents/section0.xml']=etree.tostring(r,encoding='UTF-8',xml_declaration=True);out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for k,v in m.items():z.writestr(k,v)
 return out.getvalue()
class ContentStructure(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.d=Path(self.tmp.name);self.source=self.d/'source.hwpx';self.source.write_bytes(SOURCE.read_bytes());self.out=self.d/'new.hwpx';self.plan=c.load(root/'narrative/plan.json');self.binding=c.load(root/'narrative/binding.json');self.binding['source_sha256']=c.sha(self.source)
 def tearDown(self):self.tmp.cleanup()
 def reject(self):
  with self.assertRaises((ValueError,TypeError,KeyError)):c.existing(self.source,self.out,self.plan,self.binding)
  self.assertFalse(self.out.exists());self.assertEqual(SOURCE.read_bytes(),self.source.read_bytes());self.assertFalse(any(self.d.glob('content-structure-*')))
 def test_narrative(self):
  v=c.existing(self.source,self.out,self.plan,self.binding);self.assertTrue(v['checks']['chosenRepresentationsExact']);t=c.forms.tables(self.out.read_bytes())[1];self.assertEqual(len(t.findall(c.P+'tr')),3);self.assertTrue(all(len(row.findall(c.P+'tc'))==1 for row in t.findall(c.P+'tr')))
 def test_actions(self):
  self.plan=c.load(root/'actions/plan.json');self.binding=c.load(root/'actions/binding.json');self.binding['source_sha256']=c.sha(self.source);self.assertTrue(c.existing(self.source,self.out,self.plan,self.binding)['checks']['allFactValuesAndOrderExact'])
 def test_comparison(self):
  self.plan=c.load(root/'comparison/plan.json');self.binding=c.load(root/'comparison/binding.json');self.binding['source_sha256']=c.sha(self.source);self.assertTrue(c.existing(self.source,self.out,self.plan,self.binding)['checks']['allFactValuesAndOrderExact'])
 def test_new_paragraphs(self):
  b,d=c.new_design(self.plan);self.assertTrue(c.author.validate(b,d)['ok']);self.assertFalse(any(x['type']=='table' for x in d['plan']['blocks']))
 def test_new_native_items(self):
  b,d=c.new_design(c.load(root/'actions/plan.json'));self.assertTrue(c.author.validate(b,d)['ok']);self.assertEqual(sum('list' in x for x in d['plan']['blocks']),8)
 def test_new_comparison(self):
  b,d=c.new_design(c.load(root/'comparison/plan.json'));self.assertTrue(c.author.validate(b,d)['ok']);self.assertEqual(len([x for x in d['plan']['blocks'] if x['type']=='table']),1)
 def test_new_mixed_content(self):
  more=c.load(root/'comparison/plan.json');self.plan['facts'].update(more['facts']);group=more['groups'][0];group['id']='comparison';self.plan['groups'].append(group);b,d=c.new_design(self.plan);self.assertTrue(c.author.validate(b,d)['ok']);self.assertEqual([x['type'] for x in d['plan']['blocks']],['paragraph','heading','paragraph','paragraph','table'])
 def test_declared_repetition(self):
  self.plan['groups'][0]['facts'].append('f0');self.plan['fact_uses']={'f0':2,'f1':1};b,d=c.new_design(self.plan);self.assertTrue(c.author.validate(b,d)['ok'])
 def test_bad_repetition_count(self):self.plan['fact_uses']={'f0':True,'f1':1};self.reject()
 def test_new_format_user_priority(self):
  self.plan['new_format']={'body_pt':12};b,d=c.new_design(self.plan);v=c.author.validate(b,d);self.assertTrue(v['ok']);self.assertEqual(v['resolved_format']['body_pt'],12)
 def test_unsupported_new_format(self):self.plan['new_format']={'unsupported_font_mode':True};self.assertRaises(ValueError,c.new_design,self.plan)
 def test_dry_run(self):self.assertFalse(c.existing(self.source,self.out,self.plan,self.binding,True)['published']);self.assertFalse(self.out.exists())
 def test_existing_output(self):self.out.write_bytes(b'keep');self.assertRaises(ValueError,c.existing,self.source,self.out,self.plan,self.binding);self.assertEqual(self.out.read_bytes(),b'keep')
 def test_same_source(self):self.assertRaises(ValueError,c.existing,self.source,self.source,self.plan,self.binding)
 def test_stale(self):self.binding['source_sha256']='0'*64;self.reject()
 def test_unknown_plan_key(self):self.plan['force_table']=True;self.reject()
 def test_missing_reason(self):self.plan['groups'][0]['reason']='';self.reject()
 def test_unknown_fact(self):self.plan['groups'][0]['facts'][0]='missing';self.reject()
 def test_missing_fact(self):self.plan['groups'][0]['facts'].pop();self.reject()
 def test_duplicate_fact(self):self.plan['groups'][0]['facts'].append(self.plan['groups'][0]['facts'][0]);self.reject()
 def test_origin(self):self.plan['facts']['f0']['origin']='invented_real_result';self.reject()
 def test_synthetic_disclosure(self):self.plan['disclosure']='확정 업무 실적';self.reject()
 def test_multiline(self):self.plan['facts']['f0']['text']='a\nb';self.reject()
 def test_unsupported_presentation(self):self.plan['groups'][0]['presentation']='diagram';self.reject()
 def test_unknown_binding_key(self):self.binding['auto_approve']=True;self.reject()
 def test_no_protected(self):self.binding['protected_tables']=[];self.reject()
 def test_protected_region(self):self.binding['groups']['content']['table']=1;self.reject()
 def test_missing_group_binding(self):self.binding['groups']={};self.reject()
 def test_extra_group_binding(self):self.binding['groups']['extra']=copy.deepcopy(self.binding['groups']['content']);self.reject()
 def test_caption_binding(self):self.binding['groups']['content']['caption']='이 문구가 없음';self.reject()
 def test_header_binding(self):self.binding['groups']['content']['expected_headers'][0]='없는 머리글';self.reject()
 def test_height_count(self):self.binding['groups']['content']['row_heights_mm'].pop();self.reject()
 def test_height_boolean(self):self.binding['groups']['content']['row_heights_mm'][0]=True;self.reject()
 def test_missing_required_label(self):self.binding['required_labels'].append('없음');self.reject()
 def test_comparison_shape(self):
  self.plan=c.load(root/'comparison/plan.json');self.plan['groups'][0]['rows'][0].pop();self.reject()
 def test_comparison_weight(self):self.plan=c.load(root/'comparison/plan.json');self.plan['groups'][0]['columns'][0]['weight']=float('nan');self.reject()
 def test_late_failure_atomic(self):
  with patch.object(c.cells,'apply',side_effect=ValueError('simulated merge failure')):self.reject()
 def test_outside_tamper_caught(self):
  before=self.source.read_bytes();c.existing(self.source,self.out,self.plan,self.binding);after=mutate(self.out.read_bytes(),lambda root:list(root.iter(c.P+'tbl'))[0].find(c.P+'tr').find(c.P+'tc').set('protect','1'));self.assertRaises(ValueError,c.verify_existing,before,after,self.plan,self.binding)
 def test_bound_caption_duplicate_is_scoped(self):
  # The source already has the caption phrase in the disclosure as well.
  root_node=c.xml(c.parts(self.source.read_bytes())['Contents/section0.xml']);self.assertGreater(sum('업무 내용' in ''.join(p.itertext()) for p in root_node.findall(c.P+'p')),1);v=c.existing(self.source,self.out,self.plan,self.binding);self.assertTrue(v['checks']['nonTargetXmlAndPackageExact'])
class RowHeights(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.d=Path(self.tmp.name);self.source=self.d/'source.hwpx';self.source.write_bytes(SOURCE.read_bytes());self.out=self.d/'new.hwpx';self.req=dict(schema=h.SCHEMA,source_sha256=h.sha(self.source),table=2,heights_mm=[7,14,16,18,20])
 def tearDown(self):self.tmp.cleanup()
 def reject(self):self.assertRaises((ValueError,TypeError,KeyError),h.apply,self.source,self.out,self.req);self.assertFalse(self.out.exists())
 def test_empty_styled_runs(self):self.assertTrue(h.apply(self.source,self.out,self.req)['checks']['exactHeightsOnly'])
 def test_dry_run(self):self.assertFalse(h.apply(self.source,self.out,self.req,True)['published']);self.assertFalse(self.out.exists())
 def test_stale(self):self.req['source_sha256']='0'*64;self.reject()
 def test_unknown(self):self.req['widths_mm']=[40,60,70];self.reject()
 def test_bool(self):self.req['heights_mm'][0]=True;self.reject()
 def test_small(self):self.req['heights_mm'][1]=4;self.reject()
 def test_nan(self):self.req['heights_mm'][1]=float('nan');self.reject()
 def test_count(self):self.req['heights_mm'].pop();self.reject()
 def test_protected(self):
  data=mutate(self.source.read_bytes(),lambda root:list(root.iter(c.P+'tbl'))[1].find(c.P+'tr').find(c.P+'tc').set('protect','1'));self.source.write_bytes(data);self.req['source_sha256']=h.sha(self.source);self.reject()
 def test_fixed(self):
  data=mutate(self.source.read_bytes(),lambda root:list(root.iter(c.P+'tbl'))[1].set('noAdjust','1'));self.source.write_bytes(data);self.req['source_sha256']=h.sha(self.source);self.reject()
 def test_existing(self):self.out.write_bytes(b'keep');self.assertRaises(ValueError,h.apply,self.source,self.out,self.req);self.assertEqual(self.out.read_bytes(),b'keep')
 def test_corrupt_public_result(self):
  original=h.apply_table_ops
  def corrupt(*args,**kwargs):
   result=original(*args,**kwargs);from dataclasses import replace;return replace(result,data=mutate(result.data,lambda root:list(root.iter(c.P+'tbl'))[0].set('lock','1')))
  with patch.object(h,'apply_table_ops',corrupt):self.reject()
if __name__=='__main__':unittest.main()
