"""Agent-authored content/structure decisions shared by new and existing HWPX.

This is a contract/compiler, not a natural-language model or universal form editor.
"""
from pathlib import Path
from collections import Counter
import argparse,copy,json,math,os,tempfile
import create_new_document as author
import form_adapt as forms
import safe_cell_layout as cells
import safe_edit as edits
import safe_table_columns as columns
import safe_row_heights as heights
from safe_cell_layout import P,require,sha,parts,xml
from safe_cell_spacing import snapshot,shape
from namespace_literal_guard import preserve_namespace_literals
SCHEMA='hwpx.content-structure.v1'
BINDING='hwpx.content-structure-binding.v1'

def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def dump(path,value):
 with open(path,'x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
def string(value):
 edits.single_line(value,search=True);require(bool(value.strip()) and len(value)<=3000,'nonblank bounded text required');return value
def validate(plan):
 required={'schema','request','title','purpose','audience','disclosure','facts','groups'}
 require(isinstance(plan,dict) and required<=set(plan) and set(plan)<=required|{'fact_uses','new_format'} and plan['schema']==SCHEMA,'invalid common plan keys/schema')
 if 'new_format' in plan:require(isinstance(plan['new_format'],dict),'new-format override must be an object')
 for k in ['request','title','purpose','audience','disclosure']:string(plan[k])
 facts=plan['facts'];require(isinstance(facts,dict) and 1<=len(facts)<=480,'bounded source facts required')
 for key,fact in facts.items():
  string(key);require(isinstance(fact,dict) and set(fact)=={'text','origin'} and fact['origin'] in ['user_provided','agent_authored_synthetic_fixture'],'exact text and source origin required');string(fact['text'])
 if any(f['origin']=='agent_authored_synthetic_fixture' for f in facts.values()):require('합성' in plan['disclosure'],'synthetic disclosure required')
 groups=plan['groups'];require(isinstance(groups,list) and 1<=len(groups)<=8,'1..8 chosen groups required');seen=set();used=[]
 for g in groups:
  require(isinstance(g,dict) and {'id','heading','relation','presentation','reason'}<=set(g),'group identity and decision required')
  for k in ['id','heading','relation','presentation','reason']:string(g[k])
  require(g['id'] not in seen,'duplicate group id');seen.add(g['id'])
  if g['presentation'] in ['paragraphs','items']:
   require(set(g)=={'id','heading','relation','presentation','reason','facts'},'invalid prose group keys');refs=g['facts'];require(isinstance(refs,list) and 1<=len(refs)<=40,'1..40 prose items required');used+=refs
  elif g['presentation']=='table':
   require(set(g)=={'id','heading','relation','presentation','reason','columns','rows','row_heights_mm'},'invalid table group keys');cols=g['columns'];require(isinstance(cols,list) and 1<=len(cols)<=12,'1..12 explicit columns required')
   for col in cols:
    require(isinstance(col,dict) and set(col)=={'label','weight'},'explicit label/weight required');string(col['label']);require(type(col['weight']) in [int,float] and math.isfinite(col['weight']) and col['weight']>0,'positive finite width weight')
   rows=g['rows'];require(isinstance(rows,list) and 1<=len(rows)<=40 and all(isinstance(row,list) and len(row)==len(cols) for row in rows),'bounded complete table rows');used += [ref for row in rows for ref in row]
   heights=g['row_heights_mm'];require(isinstance(heights,list) and len(heights)==len(rows)+1 and all(type(v) in [int,float] and math.isfinite(v) and 5<=v<=60 for v in heights),'explicit header/body heights 5..60mm')
  else:raise ValueError('unsupported representation; no silent replacement')
 require(all(isinstance(ref,str) and ref in facts for ref in used),'unknown source fact reference');expected=plan.get('fact_uses',{key:1 for key in facts});require(isinstance(expected,dict) and set(expected)==set(facts) and all(type(v) is int and 1<=v<=8 for v in expected.values()),'explicit source-use counts 1..8 required');require(Counter(used)==Counter(expected),'missing or undeclared repeated source facts')
 return dict(schema=SCHEMA,decisionMaker='authoring_agent',factUses=dict(Counter(used)),groups=[dict(id=g['id'],relation=g['relation'],presentation=g['presentation'],reason=g['reason']) for g in groups],native='pending')

def new_design(plan):
 validate(plan);blocks=[dict(id='disclosure',type='paragraph',text=plan['disclosure'])]
 for gi,g in enumerate(plan['groups']):
  bid='group'+str(gi);refs=g.get('facts',[ref for row in g.get('rows',[]) for ref in row]);values=lambda ref:plan['facts'][ref]['text']
  if g['presentation']=='table':
   blocks.append(dict(id=bid,type='table',caption=g['heading'],reason=g['reason'],evidence=refs,columns=[dict(key='c'+str(i),label=c['label'],widthWeight=c['weight']) for i,c in enumerate(g['columns'])],rows=[{'c'+str(i):values(ref) for i,ref in enumerate(row)} for row in g['rows']],row_heights_mm=g['row_heights_mm']))
  else:
   blocks.append(dict(id=bid,type='heading',level=1,text=g['heading']))
   for i,ref in enumerate(refs):
    b=dict(id=bid+'_'+str(i),type='paragraph',text=values(ref),evidence=[ref])
    if g['presentation']=='items':b['list']=dict(kind='bullet',level=2,group=bid)
    blocks.append(b)
 brief=dict(request=plan['request'],purpose=plan['purpose'],audience=plan['audience'],kind='업무 문서',allow_draft=True,unknowns=[],requirements=[dict(id='content',description='선택한 구조에 원자료 전부 반영',must_include=[plan['disclosure']])],facts={key:dict(text=f['text'],required=True,origin=f['origin'],not_user_provided=f['origin']!='user_provided') for key,f in plan['facts'].items()})
 if 'new_format' in plan:brief['format']=copy.deepcopy(plan['new_format'])
 design=dict(schema='hwpx.new_document.v1',plan=dict(schemaVersion='hwpx.document_plan.v1',title=plan['title'],blocks=blocks),coverage={'content':[b['id'] for b in blocks]},claims=[dict(text=f['text'],evidence=[key]) for key,f in plan['facts'].items()],review=dict(contentSource='Exact agent-declared source atoms retained; relationships/representation chosen by agent, not inferred by the CLI.',structureDecisions=validate(plan)['groups']),format=dict(body_pt=10.5,line_spacing=145,heading_numbering=None,table_header_align='center',table_line_spacing=135,table_paragraph_after_pt=0,table_outer_spacing_pt=dict(before=5,after=7),table_layout=dict(cell_margins_mm=dict(left=2,right=2,top=1.5,bottom=1.5),vertical_align='TOP',line_wrap='BREAK',page_break='TABLE',repeat_header=True,treat_as_char=False)))
 prepared=author.prepare_design(brief,design);result=author.validate(brief,prepared);require(result['ok'],'compiled new design failed authoring contract: '+str(result['mandatory_failures']))
 return brief,prepared

def validate_binding(data,plan,binding):
 validate(plan);require(isinstance(binding,dict) and set(binding)=={'schema','source_sha256','editable_reason','protected_tables','required_labels','groups'} and binding['schema']==BINDING,'invalid binding keys/schema');require(binding['source_sha256']==__import__('hashlib').sha256(data).hexdigest(),'stale existing source');string(binding['editable_reason']);ts=forms.tables(data);protected=binding['protected_tables'];require(isinstance(protected,list) and protected and all(type(x) is int and 1<=x<=len(ts) for x in protected) and len(protected)==len(set(protected)),'explicit unique protected tables required')
 require(isinstance(binding['required_labels'],list) and binding['required_labels'] and len(binding['required_labels'])==len(set(binding['required_labels'])),'explicit unique required labels');require(all(forms.labels(data,binding['required_labels']).values()),'required labels missing')
 bound=binding['groups'];require(isinstance(bound,dict) and set(bound)=={g['id'] for g in plan['groups']},'every group needs an existing region; no omitted or extra bindings');selected=[]
 for g in plan['groups']:
  b=bound[g['id']];require(isinstance(b,dict) and set(b)=={'table','expected_headers','template_row','caption','row_heights_mm'},'invalid region binding');t=b['table'];require(type(t) is int and 1<=t<=len(ts) and t not in protected and t not in selected,'unique editable unprotected table required');selected.append(t);string(b['caption'])
  cols=len(b['expected_headers']);require(cols>=1,'source headers required')
  if g['presentation']=='table':require(cols==len(g['columns']),'column reconstruction unsupported; bind a compatible region or use another explicit supported operation')
  count=len(g.get('facts',g.get('rows',[])));heights=b['row_heights_mm'];require(isinstance(heights,list) and len(heights)==count+1 and all(type(v) in [int,float] and math.isfinite(v) and 5<=v<=60 for v in heights),'explicit bound row heights required')
  values=[[plan['facts'][ref]['text'] for ref in row] for row in g['rows']] if g['presentation']=='table' else [[plan['facts'][ref]['text'],*['']*(cols-1)] for ref in g['facts']]
  forms.repeats.checked(data,dict(schema=forms.repeats.SCHEMA,source_sha256=binding['source_sha256'],editable_reason=binding['editable_reason'],table=t,expected_headers=b['expected_headers'],template_row=b['template_row'],values=values))
  # Bind the immediate caption by XML adjacency, not a global string occurrence.
  _,part,root,table=forms.repeats.locate(data,t);host=table.getparent().getparent();prior=host.getprevious();require(prior is not None and prior.tag==P+'p' and ''.join(prior.itertext())==b['caption'],'immediate source caption mismatch')
 return selected

def verify_existing(before,after,plan,binding):
 selected=validate_binding(before,plan,binding);bm=parts(before);am=parts(after);require(set(bm)==set(am),'package inventory changed');old=forms.tables(before);new=forms.tables(after);require(len(old)==len(new) and [t.get('id') for t in old]==[t.get('id') for t in new],'table inventory changed')
 captions={}
 for g in plan['groups']:
  b=binding['groups'][g['id']];_,part,root,t=forms.repeats.locate(before,b['table']);host=t.getparent().getparent();captions[(part,root.index(host.getprevious()))]=(b['caption'],g['heading'])
 def outside(root,part,is_new):
  root=copy.deepcopy(root)
  for t in list(root.iter(P+'tbl')):
   if t.get('id') in {old[i-1].get('id') for i in selected}:t.clear();t.set('selected-region','true')
  for (member,index),(expected,replacement) in captions.items():
   if member!=part:continue
   p=root[index]
   for cache in list(p.findall(P+'linesegarray')):p.remove(cache)
   runs=p.findall(P+'run');require(len(runs)==1 and len(runs[0])==1 and runs[0][0].tag==P+'t','plain caption required')
   require(runs[0][0].text==(replacement if is_new else expected),'caption text differs');runs[0][0].text='bound-caption'
  return snapshot(root)
 for member in bm:
  if member.startswith('Contents/section') and member.endswith('.xml'):require(outside(xml(bm[member]),member,False)==outside(xml(am[member]),member,True),'non-target section structure changed')
  elif not member.startswith('Preview/'):require(bm[member]==am[member],'non-target package member changed '+member)
 for i in binding['protected_tables']:require(snapshot(old[i-1])==snapshot(new[i-1]),'protected table changed')
 require(forms.labels(before,binding['required_labels'])==forms.labels(after,binding['required_labels']),'required labels changed')
 for g in plan['groups']:
  b=binding['groups'][g['id']];t=new[b['table']-1];cs,grid=shape(t);cols=int(t.get('colCnt'))
  if g['presentation']=='table':
   want=[[c['label'] for c in g['columns']],*[[plan['facts'][ref]['text'] for ref in row] for row in g['rows']]];require(len(t.findall(P+'tr'))==len(want) and len(cs)==len(want)*cols,'table shape mismatch')
   for y,row in enumerate(want):
    for x,value in enumerate(row):require(forms.repeats.text(cs[y,x])==value and cs[y,x].find(P+'cellSpan').get('colSpan')=='1','comparison value or span mismatch')
  else:
   want=[g['heading'],*[plan['facts'][ref]['text'] for ref in g['facts']]];require(len(t.findall(P+'tr'))==len(want) and len(cs)==len(want),'merged region row inventory mismatch')
   for y,value in enumerate(want):require(forms.repeats.text(cs[y,0])==value and cs[y,0].find(P+'cellSpan').get('colSpan')==str(cols),'merged row content/span mismatch')
 ids=[p.get('id') for member in am if member.startswith('Contents/section') and member.endswith('.xml') for p in xml(am[member]).iter(P+'p')];require(None not in ids and len(ids)==len(set(ids)),'paragraph ID collision')
 return dict(allFactValuesAndOrderExact=True,chosenRepresentationsExact=True,protectedTablesExact=True,nonTargetXmlAndPackageExact=True,requiredLabelsExact=True,paragraphIdsUnique=True)

@preserve_namespace_literals
def existing(source,output,plan,binding,dry_run=False):
 source=Path(source).resolve();output=Path(output).absolute();require(output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and not output.is_symlink() and source!=output.resolve(),'new output required');before=source.read_bytes();validate_binding(before,plan,binding);chain=[]
 with tempfile.TemporaryDirectory(prefix='content-structure-',dir=output.parent) as folder:
  current=source
  def step(kind,call):
   nonlocal current
   result=Path(folder)/f'{len(chain)+1:03d}.hwpx';prior=sha(current);receipt=call(current,result);require(sha(current)==prior and receipt.get('published') is True,'stage source changed/unpublished');chain.append(dict(kind=kind,input_sha256=prior,output_sha256=sha(result),receipt=receipt));current=result
  def replace(find,value,caption_table=None,**scope):
   if find==value:return
   inspection=edits.inspect_targets(current,find,**scope)
   if caption_table is not None:
    _,member,root,table=forms.repeats.locate(current.read_bytes(),caption_table);prior=table.getparent().getparent().getprevious();location=[root.index(prior)]
    inspection['targets']=[t for t in inspection['targets'] if t['part']==member and t['paragraph_path']==location]
   elif not scope:inspection['targets']=[t for t in inspection['targets'] if t['scope']['kind']=='body']
   require(len(inspection['targets'])==1 and inspection['targets'][0]['supported'],'unique supported replacement required');q=edits.make_plan(inspection,[inspection['targets'][0]['target_id']],value);step('bound_text',lambda s,o:edits.apply_plan(s,o,q))
  for g in plan['groups']:
   b=binding['groups'][g['id']];t=b['table'];cols=len(b['expected_headers']);values=[[plan['facts'][ref]['text'] for ref in row] for row in g['rows']] if g['presentation']=='table' else [[plan['facts'][ref]['text'],*['']*(cols-1)] for ref in g['facts']]
   q=dict(schema=forms.SCHEMA,source_sha256=sha(current),editable_reason=binding['editable_reason'],preserve_tables=binding['protected_tables'],required_labels=binding['required_labels'],fields=[],repeat=dict(table=t,expected_headers=b['expected_headers'],template_row=b['template_row'],values=values));step('repeat_rows_and_content',lambda s,o:forms.apply(s,o,q))
   headers=[c['label'] for c in g['columns']] if g['presentation']=='table' else [g['heading'],*['']*(cols-1)]
   for i,(old,value) in enumerate(zip(b['expected_headers'],headers),1):replace(old,value,table=t,row=1,column=i)
   replace(b['caption'],g['heading'],caption_table=t)
   _,_,_,table=forms.repeats.locate(current.read_bytes(),t);sourcewidths=[int(c.find(P+'cellSz').get('width')) for c in table.find(P+'tr').findall(P+'tc')];total=sum(sourcewidths)*25.4/7200
   weights=[c['weight'] for c in g['columns']] if g['presentation']=='table' else sourcewidths;widths=[total*w/sum(weights) for w in weights]
   if any(abs(widths[i]*7200/25.4-w)>.5 for i,w in enumerate(sourcewidths)):
    q=dict(schema=columns.SCHEMA,source_sha256=sha(current),table=t,widths_mm=widths);step('explicit_column_widths',lambda s,o:columns.apply(s,o,q))
   q=dict(schema=heights.SCHEMA,source_sha256=sha(current),table=t,heights_mm=b['row_heights_mm']);step('explicit_row_heights',lambda s,o:heights.apply(s,o,q))
   if g['presentation']!='table' and cols>1:
    for row in range(1,len(values)+2):
     q=dict(schema=cells.SCHEMA,source_sha256=sha(current),table=t,operation='merge',range=[row,1,row,cols]);step('horizontal_merge',lambda s,o:cells.apply(s,o,q))
  after=current.read_bytes();checks=verify_existing(before,after,plan,binding);require(sha(source)==binding['source_sha256'],'source changed during compilation');candidate=sha(current)
  if not dry_run:os.link(current,output)
 return dict(schema='hwpx.content-structure-receipt.v1',status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',native='pending',published=not dry_run,source_sha256=binding['source_sha256'],candidate_sha256=candidate,decisions=validate(plan),steps=chain,checks=checks)

if __name__=='__main__':
 parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True);v=sub.add_parser('validate');v.add_argument('--plan',required=True);v=sub.add_parser('new-design');v.add_argument('--plan',required=True);v.add_argument('--brief-output',required=True);v.add_argument('--design-output',required=True);v=sub.add_parser('existing');v.add_argument('source');v.add_argument('output');v.add_argument('--plan',required=True);v.add_argument('--binding',required=True);v.add_argument('--dry-run',action='store_true');args=parser.parse_args();plan=load(args.plan)
 if args.command=='validate':print(json.dumps(validate(plan),ensure_ascii=False,indent=2))
 elif args.command=='new-design':
  require(not Path(args.brief_output).exists() and not Path(args.design_output).exists() and Path(args.brief_output).resolve()!=Path(args.design_output).resolve(),'new distinct design/brief paths');brief,design=new_design(plan);dump(args.brief_output,brief);dump(args.design_output,design)
 else:print(json.dumps(existing(args.source,args.output,plan,load(args.binding),args.dry_run),ensure_ascii=False,indent=2))
