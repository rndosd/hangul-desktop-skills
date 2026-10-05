"""Opt-in small-overflow margin search for reports made by create_new_document.

Native Hancom measures every candidate. Selection stays pending until the
unchanged completion gate accepts a separate, performed visual review.
"""
from __future__ import annotations
import argparse,copy,hashlib,importlib.util,json,math,os,re,subprocess,sys
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import create_new_document as author

SCHEMA='hwpx.auto-margin-fit.v1'
DEFAULT_POLICY=dict(min_margins_mm=dict(top=15,bottom=15,left=15,right=15),step_mm=0.5,axes=['vertical','horizontal'],max_overflow_lines=3,max_tail_fraction=0.25,max_attempts=20)

def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
 with Path(path).open('x',encoding='utf8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
def reference(path):
 p=Path(path).resolve();return dict(path=str(p),sha256=sha(p))
def verify_reference(ref):
 if reference(ref['path'])!=ref:raise ValueError('bound file changed: '+ref['path'])
def policy(raw):
 p=copy.deepcopy(DEFAULT_POLICY);extra=set(raw)-set(p)
 if extra:raise ValueError('unknown policy fields: '+str(sorted(extra)))
 p.update(raw)
 if not isinstance(p['min_margins_mm'],dict) or set(p['min_margins_mm'])!={'top','bottom','left','right'}:raise ValueError('four minimum margins required')
 for v in p['min_margins_mm'].values():
  if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=60:raise ValueError('invalid minimum margin')
 v=p['step_mm']
 if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0.25<=v<=2:raise ValueError('step_mm must be 0.25..2')
 if not isinstance(p['axes'],list) or not p['axes'] or len(set(p['axes']))!=len(p['axes']) or set(p['axes'])-{'vertical','horizontal'}:raise ValueError('invalid axes')
 for key,upper in [('max_overflow_lines',8),('max_attempts',40)]:
  if type(p[key]) is not int or not 1<=p[key]<=upper:raise ValueError('invalid '+key)
 v=p['max_tail_fraction']
 if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<v<=0.4:raise ValueError('invalid max_tail_fraction')
 return p

def candidate_margins(base,p):
 limits={}
 for axis,sides in [('vertical',('top','bottom')),('horizontal',('left','right'))]:
  limits[axis]=max(0,math.floor(min(base[s]-p['min_margins_mm'][s] for s in sides)/p['step_mm']+1e-8)) if axis in p['axes'] else 0
 combinations=[(v+h,h,v) for v in range(limits['vertical']+1) for h in range(limits['horizontal']+1) if v+h]
 for total,h,v in sorted(combinations):
  m=dict(base)
  for side in ('top','bottom'):m[side]=round(base[side]-v*p['step_mm'],6)
  for side in ('left','right'):m[side]=round(base[side]-h*p['step_mm'],6)
  yield dict(margins_mm=m,total_reduction_mm=round(total*p['step_mm']*2,6),vertical_steps=v,horizontal_steps=h)

def normalize_text(text):return re.sub(r'\s+','',text)
def source_fragments(source):
 result=[]
 with ZipFile(source) as z:
  for name in sorted(z.namelist()):
   if re.fullmatch(r'Contents/section\d+\.xml',name):
    for t in ET.fromstring(z.read(name)).iter('{'+author.NS['hp']+'}t'):
     text=''.join(t.itertext())
     if normalize_text(text):result.append(text)
 return result

def inspect_pdf(pdf,source):
 import pymupdf
 with pymupdf.open(pdf) as doc:
  texts=[page.get_text(sort=True) for page in doc];page=doc[-1];lines=[];images=0
  for b in page.get_text('dict')['blocks']:
   if b.get('type')==1:images+=1
   if b.get('type')==0:
    for line in b.get('lines',[]):
     text=''.join(s['text'] for s in line.get('spans',[]))
     if text.strip():lines.append(dict(text=text,bbox=list(line['bbox'])))
  fraction=(max(x['bbox'][3] for x in lines)-min(x['bbox'][1] for x in lines))/page.rect.height if lines else 0
  combined=normalize_text(''.join(texts));missing=[x for x in source_fragments(source) if normalize_text(x) not in combined]
  return dict(page_count=len(doc),tail_line_count=len(lines),tail_fraction=fraction,tail_images=images,tail_lines=lines,missing_fragments=missing,pdf_content_checked=not missing)

def eligibility(measure,p,design):
 if any(b['type']=='page_break' for b in design['plan']['blocks']):return 'intentional_page_break'
 if measure['missing_fragments']:return 'pdf_content_inconclusive_or_missing'
 if measure['page_count']<2:return 'already_one_page'
 if measure['tail_images']:return 'tail_contains_image'
 if not measure['tail_line_count']:return 'blank_last_page'
 if measure['tail_line_count']>p['max_overflow_lines'] or measure['tail_fraction']>p['max_tail_fraction']:return 'tail_not_small_overflow'
 return None

def xml_snapshot(path,strip_geometry=False):
 with ZipFile(path) as z:
  out={}
  def node(e):
   attrs=dict(e.attrib);tag=e.tag.rsplit('}',1)[-1]
   if e.tag in ('{'+author.NS['hp']+'}p','{'+author.NS['hp']+'}tbl'):attrs.pop('id',None)
   if strip_geometry:
    if e.tag=='{'+author.NS['hp']+'}margin':
     for side in ('top','bottom','left','right'):attrs.pop(side,None)
    if e.tag in ('{'+author.NS['hp']+'}sz','{'+author.NS['hp']+'}cellSz'):attrs.pop('width',None)
   return (e.tag,tuple(sorted(attrs.items())),e.text or '',tuple(node(x) for x in e))
  for name in z.namelist():
   if name.startswith('Contents/') and name.endswith(('.xml','.hpf')):out[name]=node(ET.fromstring(z.read(name)))
  return out

def verify_declared_margins(path,margins):
 with ZipFile(path) as z:
  s=ET.fromstring(z.read('Contents/section0.xml'));m=s.find('.//hp:pagePr/hp:margin',author.NS)
  if m is None or any(abs(int(m.get(side,'-1'))-round(value*7200/25.4))>1 for side,value in margins.items()):raise ValueError('candidate margin values do not match selection')

def check_generation_change(source,candidate,brief,original_design,changed_design,gate):
 # Regeneration is allowed only for a generator-bound new report, not a template.
 a=copy.deepcopy(original_design);b=copy.deepcopy(changed_design)
 a.setdefault('format',{}).pop('margins_mm',None);b.setdefault('format',{}).pop('margins_mm',None)
 if a!=b:raise ValueError('non-margin design change')
 a=gate.read_package(source);b=gate.read_package(candidate)
 for key in ('texts','counts','sections','binaryPayloads','binaryReferences','controls'):
  if a[key]!=b[key]:raise ValueError('regeneration preservation failed: '+key)
 if xml_snapshot(source,True)!=xml_snapshot(candidate,True):raise ValueError('non-margin XML or format changed during regeneration')
 verify_declared_margins(candidate,author.formatting(brief,changed_design)['margins_mm'])
 with ZipFile(candidate) as z:
  tables=ET.fromstring(z.read('Contents/section0.xml')).findall('.//hp:tbl',author.NS)
 for table,block in zip(tables,[x for x in changed_design['plan']['blocks'] if x['type']=='table']):
  width=int(table.find('hp:sz',author.NS).get('width'));weights=[c.get('widthWeight',1) for c in block['columns']]
  for row in table.findall('hp:tr',author.NS):
   sizes=[int(c.find('hp:cellSz',author.NS).get('width')) for c in row.findall('hp:tc',author.NS)]
   if abs(sum(sizes)-width)>1 or any(abs(value-width*weight/sum(weights))>2 for value,weight in zip(sizes,weights)):raise ValueError('column proportions changed')
 result=author.audit_output(candidate,brief,changed_design)
 if result['status']!='PASS_STRUCTURE':raise ValueError('candidate source audit failed')
 return dict(status='pass',non_geometry_xml_preserved=True,only_design_margin_changed=True,invariants={k:True for k in ('texts','counts','sections','binaryPayloads','binaryReferences','controls')})

def get_gate(directory):
 spec=importlib.util.spec_from_file_location('auto_margin_completion_gate',Path(directory)/'hancom_completion_gate.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def render_native(candidate,folder,finalize,powershell,gate):
 saved=folder/'saved.hwpx';pdf=folder/'saved.pdf';run=folder/'native-run';bundle=folder/'native-bundle'
 gate.prepare(bundle,candidate,saved,pdf,run)
 cmd=[str(powershell),'-NoProfile','-File',str(Path(finalize)/'verify_hwpx_with_hancom.ps1'),'-CandidatePath',str(candidate.resolve()),'-Mode','SaveAs','-OutputPath',str(saved.resolve()),'-PdfPath',str(pdf.resolve()),'-RunDirectory',str(run.resolve()),'-TimeoutSeconds','120']
 # A Python child can inherit PS7's module lookup path into Windows PS5.
 # Reset lookup only for this subprocess; no machine/user setting is changed.
 child_env={k:v for k,v in os.environ.items() if k.casefold()!='psmodulepath'}
 r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=160,env=child_env)
 write(folder/'native-command.json',dict(argv=cmd,returncode=r.returncode))
 (folder/'launcher.stdout.txt').write_text(r.stdout,encoding='utf8');(folder/'launcher.stderr.txt').write_text(r.stderr,encoding='utf8')
 if r.returncode:raise ValueError('native verification failed; inspect '+str(run))
 state=gate.collect(bundle)
 if state['status']=='blocked':raise ValueError('native preservation gate blocked: '+str(state.get('failedInvariants')))
 return inspect_pdf(pdf,candidate)

def run(source,brief_path,design_path,output,p,finalize,powershell):
 source=Path(source).resolve();output=Path(output).resolve();brief=load(brief_path);design=load(design_path)
 original_refs=dict(source=reference(source),brief=reference(brief_path),design=reference(design_path))
 creation=load(source.with_suffix('.receipt.json'))
 if creation.get('audit',{}).get('sha256')!=sha(source) or creation.get('audit',{}).get('status')!='PASS_STRUCTURE':raise ValueError('source must match its create_new_document receipt')
 if author.audit_output(source,brief,design)['status']!='PASS_STRUCTURE':raise ValueError('source and brief/design do not match')
 # Import optional dependencies before opening any Hancom instance.
 import pymupdf
 gate=get_gate(finalize)
 if output.exists():raise FileExistsError('output directory must be new')
 output.mkdir(parents=True);write(output/'inputs.json',dict(schema=SCHEMA,inputs=original_refs,policy=p,generator=reference(author.__file__)))
 result=dict(schema=SCHEMA,status='pending',inputs=original_refs,policy=p,attempts=[],source_unchanged=True)
 try:
  if any(author.formatting(brief,design)['margins_mm'][side]<p['min_margins_mm'][side] for side in p['min_margins_mm']):result.update(status='skipped',reason='current_margin_below_minimum');return result
  if any(b['type']=='page_break' for b in design['plan']['blocks']):result.update(status='skipped',reason='intentional_page_break');return result
  baseline=output/'baseline';baseline.mkdir();measure=render_native(source,baseline,finalize,powershell,gate);write(baseline/'measurement.json',measure);result['baseline']=dict(measurement=measure,bundle=str((baseline/'native-bundle').resolve()),saved=reference(baseline/'saved.hwpx'),pdf=reference(baseline/'saved.pdf'))
  reason=eligibility(measure,p,design)
  if reason:result.update(status='skipped',reason=reason);return result
  base=author.formatting(brief,design)['margins_mm'];target=measure['page_count']-1
  result['target_pages']=target
  for i,item in enumerate(candidate_margins(base,p),1):
   if i>p['max_attempts']:result.update(status='pending',reason='search_budget_exhausted');return result
   folder=output/f'candidate-{i:03d}';folder.mkdir();d=copy.deepcopy(design);b=copy.deepcopy(brief)
   # User brief overrides design; apply the same approved margin values to both.
   d.setdefault('format',{})['margins_mm']=item['margins_mm'];b.setdefault('format',{})['margins_mm']=item['margins_mm']
   write(folder/'design.json',d);write(folder/'brief.json',b);candidate=folder/'candidate.hwpx';author.create(b,d,candidate)
   static=check_generation_change(source,candidate,b,design,d,gate);write(folder/'generation-preservation.json',static)
   observed=render_native(candidate,folder,finalize,powershell,gate);write(folder/'measurement.json',observed)
   entry=dict(item,artifact_refs={key:reference(path) for key,path in [('candidate',candidate),('saved',folder/'saved.hwpx'),('pdf',folder/'saved.pdf')]},case=str(folder.resolve()),page_count=observed['page_count'],pdf_content_checked=observed['pdf_content_checked']);result['attempts'].append(entry)
   print(json.dumps(dict(progress='candidate_checked',attempt=i,**item,page_count=observed['page_count']),ensure_ascii=False),file=sys.stderr,flush=True)
   if observed['page_count']==target and observed['pdf_content_checked']:
    result.update(status='pending_review',reason='minimal_candidate_requires_actual_visual_review',selected=dict(entry,candidate=reference(candidate),saved=reference(folder/'saved.hwpx'),pdf=reference(folder/'saved.pdf'),bundle=str((folder/'native-bundle').resolve()),measured_minimum_in_search_grid=True))
    return result
  result.update(status='no_fit',reason='no_candidate_within_minimum_margins');return result
 except Exception as ex:
  result.update(status='blocked',reason=str(ex),error_type=type(ex).__name__)
  raise
 finally:
  result['source_unchanged']=all(reference(x['path'])==x for x in original_refs.values())
  if not result['source_unchanged']:result.update(status='blocked',reason='bound_input_changed')
  write(output/'selection.json',result)

def accept(selection_path,review_path,output,finalize):
 s=load(selection_path)
 if s.get('status')!='pending_review':raise ValueError('selection does not await review')
 for ref in s['inputs'].values():verify_reference(ref)
 for key in ('candidate','saved','pdf'):verify_reference(s['selected'][key])
 info=load(Path(selection_path).parent/'inputs.json')
 if s['inputs']!=info['inputs'] or s['policy']!=info['policy']:raise ValueError('selection inputs or policy changed')
 p=policy(s['policy']);brief=load(s['inputs']['brief']['path']);design=load(s['inputs']['design']['path'])
 for key in ('saved','pdf'):verify_reference(s['baseline'][key])
 baseline=inspect_pdf(s['baseline']['pdf']['path'],s['inputs']['source']['path'])
 if baseline!=s['baseline']['measurement'] or eligibility(baseline,p,design):raise ValueError('baseline eligibility changed')
 expected=list(candidate_margins(author.formatting(brief,design)['margins_mm'],p))
 if not s['attempts'] or len(s['attempts'])>p['max_attempts']:raise ValueError('invalid attempts')
 for index,attempt in enumerate(s['attempts']):
  for key in ('margins_mm','total_reduction_mm','vertical_steps','horizontal_steps'):
   if attempt[key]!=expected[index][key]:raise ValueError('search order or margin selection changed')
  for ref in attempt['artifact_refs'].values():verify_reference(ref)
  observed=inspect_pdf(attempt['artifact_refs']['pdf']['path'],attempt['artifact_refs']['candidate']['path'])
  if observed['page_count']!=attempt['page_count'] or observed['pdf_content_checked']!=attempt['pdf_content_checked']:raise ValueError('candidate measurement changed')
  verify_declared_margins(attempt['artifact_refs']['candidate']['path'],attempt['margins_mm'])
  if index<len(s['attempts'])-1 and observed['page_count']==baseline['page_count']-1 and observed['pdf_content_checked']:raise ValueError('smaller valid candidate was skipped')
 if s['selected']['margins_mm']!=s['attempts'][-1]['margins_mm'] or s['selected']['artifact_refs']!=s['attempts'][-1]['artifact_refs']:raise ValueError('selected candidate changed')
 if s['selected']['page_count']!=baseline['page_count']-1 or not s['selected']['pdf_content_checked']:raise ValueError('invalid selected fit')
 case=Path(s['selected']['case'])
 if str(case)!=s['attempts'][-1]['case'] or Path(s['selected']['bundle']).resolve()!=(case/'native-bundle').resolve():raise ValueError('selected bundle changed')
 for key in ('candidate','saved','pdf'):
  if s['selected'][key]!=s['attempts'][-1]['artifact_refs'][key]:raise ValueError('selected artifact changed')
 evidence=load(case/'native-bundle/evidence.json')
 for name,key in [('source','candidate'),('final','saved'),('pdf','pdf')]:
  ref=evidence['artifacts'][name]
  if dict(path=ref['path'],sha256=ref['sha256'])!=s['selected'][key]:raise ValueError('selected artifact not bound to native evidence')
 verify_reference(load(Path(selection_path).parent/'inputs.json')['generator'])
 gate=get_gate(finalize);completion=gate.check(s['selected']['bundle'],review_path)
 result=dict(schema=SCHEMA,status='complete',selection=reference(selection_path),native_completion=completion,chosen_margins_mm=s['selected']['margins_mm'],total_reduction_mm=s['selected']['total_reduction_mm'],minimum_scope='configured opposing-margin-pair grid; all smaller costs tested before selection')
 write(output,result);return result

def main():
 ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
 r=sub.add_parser('run')
 for n in ['source','brief','design','output-dir']:r.add_argument('--'+n,required=True,type=Path)
 r.add_argument('--policy',type=Path)
 a=sub.add_parser('accept');a.add_argument('--selection',required=True,type=Path);a.add_argument('--review',required=True,type=Path);a.add_argument('--output',required=True,type=Path)
 default=Path(__file__).resolve().parents[2]/'hwpx-windows-finalize/scripts'
 for parser in [r,a]:
  parser.add_argument('--finalize-dir',type=Path,default=default);parser.add_argument('--pdf-module-path',type=Path)
 r.add_argument('--powershell',type=Path,default=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe')
 args=ap.parse_args()
 if args.pdf_module_path:sys.path.insert(0,str(args.pdf_module_path.resolve()))
 try:
  if args.command=='run':result=run(args.source,args.brief,args.design,args.output_dir,policy(load(args.policy) if args.policy else {}),args.finalize_dir,args.powershell)
  else:result=accept(args.selection,args.review,args.output,args.finalize_dir)
 except Exception as ex:
  result=dict(schema=SCHEMA,status=getattr(ex,'state','blocked'),reason=getattr(ex,'reason',str(ex)),error_type=type(ex).__name__)
  if args.command=='run' and args.output_dir.is_dir() and not (args.output_dir/'failure.json').exists():write(args.output_dir/'failure.json',result)
 print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['status'] in ('complete','skipped','no_fit') else 2 if result['status'] in ('pending','pending_review') else 3
if __name__=='__main__':raise SystemExit(main())
