"""Guards for margin-only regeneration and measured small-overflow selection."""
import copy,json,os,shutil,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from lxml import etree as E
import auto_margin_fit as f
from test_page_flow import fixture
FINALIZE=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'skills/hwpx-windows-finalize/scripts'

class MarginFitChecks(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.b,self.d=fixture();self.source=self.root/'source.hwpx';f.author.create(self.b,self.d,self.source)
  self.bp=self.root/'brief.json';self.dp=self.root/'design.json';f.write(self.bp,self.b);f.write(self.dp,self.d)
 def measurement(self,pages=2,lines=1):return dict(page_count=pages,tail_line_count=lines,tail_fraction=0.05,tail_images=0,tail_lines=[],missing_fragments=[],pdf_content_checked=True)
 def test_grid_sorted_and_deterministic(self):
  p=f.policy({});base=dict(top=20,bottom=20,left=20,right=20);items=list(f.candidate_margins(base,p));self.assertEqual(len(items),120)
  self.assertEqual(items[0]['margins_mm'],dict(top=19.5,bottom=19.5,left=20,right=20));self.assertEqual(items[1]['margins_mm'],dict(top=20,bottom=20,left=19.5,right=19.5))
  self.assertEqual([x['total_reduction_mm'] for x in items],sorted(x['total_reduction_mm'] for x in items));self.assertEqual(len({tuple(x['margins_mm'].values()) for x in items}),len(items));self.assertTrue(all(min(x['margins_mm'].values())>=15 for x in items))
 def test_asymmetric_base_and_vertical_only(self):
  p=f.policy({'axes':['vertical'],'min_margins_mm':dict(top=17,bottom=15,left=18,right=18)})
  items=list(f.candidate_margins(dict(top=18,bottom=20,left=20,right=20),p));self.assertEqual(len(items),2);self.assertEqual(items[-1]['margins_mm'],dict(top=17,bottom=19,left=20,right=20))
 def test_invalid_policy_rejected(self):
  for p in [{'step_mm':True},{'step_mm':0},{'axes':[]},{'axes':['vertical','vertical']},{'max_attempts':999},{'max_tail_fraction':0.9},{'min_margins_mm':{'top':15}},{'unknown':1}]:
   with self.assertRaises(ValueError):f.policy(p)
 def test_eligibility_excludes_intentional_break(self):
  d=copy.deepcopy(self.d);d['plan']['blocks'].append(dict(id='break',type='page_break',reason='separate appendix'));self.assertEqual(f.eligibility(self.measurement(),f.policy({}),d),'intentional_page_break')
 def test_not_small_tail_and_content_fail(self):
  self.assertEqual(f.eligibility(self.measurement(lines=4),f.policy({}),self.d),'tail_not_small_overflow')
  m=self.measurement();m['missing_fragments']=['missing'];self.assertEqual(f.eligibility(m,f.policy({}),self.d),'pdf_content_inconclusive_or_missing')
 def test_blank_and_one_page_are_not_spill(self):
  self.assertEqual(f.eligibility(self.measurement(pages=1),f.policy({}),self.d),'already_one_page');self.assertEqual(f.eligibility(self.measurement(lines=0),f.policy({}),self.d),'blank_last_page')
 def regenerate(self,margins):
  d=copy.deepcopy(self.d);d['format']['margins_mm']=margins;p=self.root/'candidate.hwpx';f.author.create(self.b,d,p);return d,p
 def test_vertical_regeneration_only_geometry_changes(self):
  d,p=self.regenerate(dict(top=19.5,bottom=19.5,left=20,right=20));g=f.get_gate(FINALIZE);result=f.check_generation_change(self.source,p,self.b,self.d,d,g);self.assertTrue(result['non_geometry_xml_preserved'])
 def test_horizontal_regeneration_preserves_column_proportions(self):
  d,p=self.regenerate(dict(top=20,bottom=20,left=19.5,right=19.5));g=f.get_gate(FINALIZE);result=f.check_generation_change(self.source,p,self.b,self.d,d,g);self.assertEqual(result['status'],'pass')
 def test_other_design_change_rejected(self):
  d,p=self.regenerate(dict(top=19.5,bottom=19.5,left=20,right=20));d['format']['body_pt']=8
  with self.assertRaisesRegex(ValueError,'non-margin design'):f.check_generation_change(self.source,p,self.b,self.d,d,f.get_gate(FINALIZE))
 def mutate(self,p,member,mutator):
  with zipfile.ZipFile(p) as z:data={n:z.read(n) for n in z.namelist()}
  root=E.fromstring(data[member]);mutator(root);data[member]=E.tostring(root,encoding='utf-8',xml_declaration=True);new=self.root/'mutated.hwpx'
  with zipfile.ZipFile(new,'x',zipfile.ZIP_DEFLATED) as z:
   for n,b in data.items():z.writestr(n,b)
  return new
 def test_unrequested_character_format_change_rejected(self):
  d,p=self.regenerate(dict(top=19.5,bottom=19.5,left=20,right=20));bad=self.mutate(p,'Contents/header.xml',lambda root:root.find('.//hh:charPr',f.author.NS).set('textColor','#FF0000'))
  with self.assertRaisesRegex(ValueError,'non-margin XML'):f.check_generation_change(self.source,bad,self.b,self.d,d,f.get_gate(FINALIZE))
 def test_column_ratio_tamper_rejected(self):
  d,p=self.regenerate(dict(top=19.5,bottom=19.5,left=20,right=20));
  def shift(root):
   cells=root.findall('.//hp:tr',f.author.NS)[0].findall('hp:tc/hp:cellSz',f.author.NS)
   cells[0].set('width',str(int(cells[0].get('width'))+100));cells[1].set('width',str(int(cells[1].get('width'))-100))
  bad=self.mutate(p,'Contents/section0.xml',shift)
  with self.assertRaisesRegex(ValueError,'column proportions'):f.check_generation_change(self.source,bad,self.b,self.d,d,f.get_gate(FINALIZE))
 def fake_render(self,observations):
  values=iter(observations)
  def render(source,folder,*args):
   shutil.copy2(source,folder/'saved.hwpx');(folder/'saved.pdf').write_bytes(b'unit test sentinel: not a rendered PDF');return next(values)
  return render
 def test_first_success_remains_pending_actual_review(self):
  original=f.sha(self.source)
  with patch.object(f,'render_native',side_effect=self.fake_render([self.measurement(),self.measurement(pages=2),self.measurement(pages=1)])):
   r=f.run(self.source,self.bp,self.dp,self.root/'run',f.policy({}),FINALIZE,Path('unused'))
  self.assertEqual(r['status'],'pending_review');self.assertEqual(len(r['attempts']),2);self.assertEqual(r['selected']['horizontal_steps'],1);self.assertEqual(original,f.sha(self.source))
 def test_search_budget_does_not_claim_fit(self):
  with patch.object(f,'render_native',side_effect=self.fake_render([self.measurement(),self.measurement(pages=2)])):
   r=f.run(self.source,self.bp,self.dp,self.root/'run',f.policy({'max_attempts':1}),FINALIZE,Path('unused'))
  self.assertEqual(r['status'],'pending');self.assertEqual(r['reason'],'search_budget_exhausted');self.assertNotIn('selected',r)
 def test_exhausted_allowed_margins_preserves_original(self):
  p=f.policy({'min_margins_mm':dict(top=20,bottom=20,left=20,right=20)})
  with patch.object(f,'render_native',side_effect=self.fake_render([self.measurement()])):
   r=f.run(self.source,self.bp,self.dp,self.root/'run',p,FINALIZE,Path('unused'))
  self.assertEqual(r['status'],'no_fit');self.assertTrue(r['source_unchanged']);self.assertNotIn('selected',r)
 def test_below_minimum_skips_without_native_call(self):
  p=f.policy({'min_margins_mm':dict(top=21,bottom=15,left=15,right=15)})
  with patch.object(f,'render_native') as renderer:r=f.run(self.source,self.bp,self.dp,self.root/'run',p,FINALIZE,Path('unused'))
  self.assertEqual(r['reason'],'current_margin_below_minimum');renderer.assert_not_called()
 def test_existing_output_refused_without_native_call(self):
  out=self.root/'exists';out.mkdir()
  with patch.object(f,'render_native') as renderer:
   with self.assertRaises(FileExistsError):f.run(self.source,self.bp,self.dp,out,f.policy({}),FINALIZE,Path('unused'))
  renderer.assert_not_called()
 def test_unbound_source_refused_before_native_call(self):
  receipt=self.source.with_suffix('.receipt.json');data=f.load(receipt);data['audit']['sha256']='wrong';receipt.write_text(json.dumps(data),encoding='utf8')
  with patch.object(f,'render_native') as renderer:
   with self.assertRaises(ValueError):f.run(self.source,self.bp,self.dp,self.root/'run',f.policy({}),FINALIZE,Path('unused'))
  renderer.assert_not_called()
 def test_native_error_retains_blocked_receipt(self):
  with patch.object(f,'render_native',side_effect=ValueError('native failed')):
   with self.assertRaises(ValueError):f.run(self.source,self.bp,self.dp,self.root/'run',f.policy({}),FINALIZE,Path('unused'))
  r=f.load(self.root/'run/selection.json');self.assertEqual(r['status'],'blocked');self.assertTrue(r['source_unchanged'])
 def test_accept_rejects_unreviewed_state(self):
  file=self.root/'selection.json';f.write(file,dict(status='no_fit'))
  with self.assertRaises(ValueError):f.accept(file,self.root/'review.json',self.root/'done.json',FINALIZE)
if __name__=='__main__':unittest.main()

