"""Bounded root-body editing using public python-hwpx 6.3.0 APIs.

Existing styles/numbering stay intact. v2 supports explicitly mapped run text
and derived paragraph flow flags, with all non-target content verified.
Not a fallback for cell/field/section or unsupported edits. Native review follows.
"""
from pathlib import Path
import argparse,copy,hashlib,json,io,zipfile,os,posixpath,uuid
from contextlib import contextmanager
from importlib.metadata import version
from lxml import etree as E
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
from namespace_literal_guard import preserve_namespace_literals
from safe_edit import parse,single_line

P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'
H='{http://www.hancom.co.kr/hwpml/2011/head}'
SCHEMA='hwpx.body-structure.v1'
RICH_SCHEMA='hwpx.body-structure.v2'
def require(v,m):
 if not v:raise ValueError(m)
def digest(data):return hashlib.sha256(data).hexdigest()
def sha(path):return digest(Path(path).read_bytes())

@contextmanager
def workspace_candidate(parent):
 # Python's Windows TemporaryDirectory uses an owner-only DACL which
 # can exclude the Codex restricted token. A fresh ordinary workspace folder
 # inherits its authorized parent's ACL. Never chmod an existing path, and
 # remove only this exact generated file/directory, without recursive cleanup.
 directory=Path(parent).resolve(strict=True)/('.body-structure-'+uuid.uuid4().hex)
 directory.mkdir()
 candidate=directory/'candidate.hwpx'
 try:yield candidate
 finally:
  candidate.unlink(missing_ok=True)
  directory.rmdir()
def tree(node,*,new_id=False,new_text=None,no_cache=False):
 if no_cache and node.tag==P+'linesegarray':return None
 attrs=dict(node.attrib)
 if new_id and node.tag==P+'p':attrs.pop('id',None)
 value=node.text or ''
 if node.tag==P+'t' and new_text is not None:value=new_text
 elif node.tag!=P+'t' and not value.strip():value=''
 return [node.tag,sorted(attrs.items()),value,[r for child in node for r in [tree(child,new_id=new_id,new_text=new_text,no_cache=no_cache)] if r is not None]]
def node_sha(n):return digest(json.dumps(tree(n),ensure_ascii=False,sort_keys=True).encode('utf8'))
def text(n):return ''.join((t.text or '')+''.join(('\n' if c.tag==P+'lineBreak' else '\t')+(c.tail or '') for c in t) for r in n.findall(P+'run') for t in r.findall(P+'t'))
def package(raw):
 require(len(raw)<=100000000,'package too large')
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  require(len(z.namelist())==len(set(z.namelist())) and len(z.namelist())<=2000,'invalid member inventory')
  require(sum(i.file_size for i in z.infolist())<=200000000,'expanded package too large')
  require(z.testzip() is None,'invalid ZIP')
  parts={n:z.read(n) for n in z.namelist()}
 manifest=parse(parts['Contents/content.hpf']);items={n.get('id'):n.get('href') for n in manifest.findall('{*}manifest/{*}item')}
 require(len(items)==len(manifest.findall('{*}manifest/{*}item')),'duplicate manifest identities')
 order=[]
 for n in manifest.findall('{*}spine/{*}itemref'):
  href=items.get(n.get('idref'));require(href,'unresolved spine')
  path=href if href in parts else posixpath.normpath(posixpath.join('Contents',href))
  if path.startswith('Contents/section') and path.endswith('.xml'):order.append(path)
 inventory={n for n in parts if n.startswith('Contents/section') and n.endswith('.xml')}
 require(order and len(order)==len(inventory) and set(order)==inventory,'section spine mismatch')
 roots={n:parse(parts[n]) for n in order}
 require(all(all(c.tag==P+'p' for c in r) for r in roots.values()),'root-body paragraph sections required')
 require(sum(len(r) for r in roots.values())<=1200,'too many root paragraphs')
 header=parse(parts['Contents/header.xml']);defs={n.get('id'):n for n in header.iter(H+'paraPr')}
 return parts,roots,defs
def heading(p,defs):
 shape=defs.get(p.get('paraPrIDRef'));require(shape is not None,'unresolved paragraph style')
 h=shape.find(H+'heading')
 return dict(type=h.get('type','NONE'),idRef=h.get('idRef'),level=int(h.get('level','0'))) if h is not None else dict(type='NONE',idRef=None,level=0)
def eligible(p,defs,template=False,rich=False):
 if p.get('pageBreak','0')!='0' or p.get('columnBreak','0')!='0':return False
 if any(n.tag not in (P+'run',P+'linesegarray') for n in p):return False
 runs=p.findall(P+'run')
 if not runs or any(set(r.attrib)!={'charPrIDRef'} or any(t.tag!=P+'t' or len(t) for t in r) for r in runs):return False
 if any(len(r.findall(P+'t'))!=len(r) for r in runs):return False
 if heading(p,defs)['type'] not in ['NONE','NUMBER','BULLET']:return False
 br=defs[p.get('paraPrIDRef')].find(H+'breakSetting')
 if br is not None and br.get('pageBreakBefore','0')!='0':return False
 if template and (not text(p).strip() or any(len(r)!=1 for r in runs) or (not rich and len(runs)!=1) or len(runs)>20):return False
 return True

def checked_runs(p,values):
 require(isinstance(values,list) and len(values)==len(p.findall(P+'run')),'explicit text for every existing run required')
 for value in values:single_line(value)
 require(''.join(values).strip() and sum(map(len,values))<=3000,'nonempty bounded run text')
 return values

def run_tree(p,values,*,new_id=False):
 # Read-only expected tree. No source XML is modified or serialized here.
 value=tree(p,new_id=new_id,no_cache=True);runs=[n for n in value[3] if n[0]==P+'run']
 require(len(runs)==len(values),'expected run count')
 for run,content in zip(runs,values):
  require(len(run[3])==1 and run[3][0][0]==P+'t','expected plain text run')
  run[3][0][2]=content
 return value
def binding(part,index,p):return dict(part=part,index=index,id=p.get('id'),sha256=node_sha(p),text=text(p))
def inspect(source):
 raw=Path(source).read_bytes();parts,roots,defs=package(raw)
 records=[]
 for name,root in roots.items():
  for idx,p in enumerate(root):
   records.append(dict(binding=binding(name,idx,p),plain=eligible(p,defs),template=eligible(p,defs,True),richTemplate=eligible(p,defs,True,True),runs=[dict(text=r.find(P+'t').text or '',charPrIDRef=r.get('charPrIDRef')) for r in p.findall(P+'run')] if eligible(p,defs,True,True) else None,heading=heading(p,defs),controls=[n.tag.rsplit('}',1)[-1] for n in p.iter() if n.tag in [P+x for x in ['tbl','pic','ctrl','footNote','endNote','fieldBegin','bookmark']]]))
 return dict(schema=SCHEMA,sourceSha256=digest(raw),paragraphs=records,native='NOT_CHECKED')
def locate(b,roots):
 require(isinstance(b,dict) and set(b)=={'part','index','id','sha256','text'},'complete bound paragraph selector required')
 require(b['part'] in roots and type(b['index']) is int and 0<=b['index']<len(roots[b['part']]),'paragraph outside root body')
 p=roots[b['part']][b['index']]
 require(binding(b['part'],b['index'],p)==b,'stale/mismatched paragraph binding')
 return p
def checked(raw,request):
 require(version('python-hwpx')=='6.3.0','unverified core')
 require(isinstance(request,dict) and set(request)=={'schema','sourceSha256','editableReason','protectedSpans','operations'},'invalid request keys')
 require(request['schema'] in [SCHEMA,RICH_SCHEMA] and request['sourceSha256']==digest(raw),'stale source/schema')
 rich=request['schema']==RICH_SCHEMA
 single_line(request['editableReason'],search=True);require(len(request['editableReason'].strip())>=8,'describe authorized change scope')
 parts,roots,defs=package(raw)
 require(isinstance(request['protectedSpans'],list) and len(request['protectedSpans'])<=30,'invalid protected spans')
 protected=[]
 for span in request['protectedSpans']:
  require(isinstance(span,dict) and set(span)=={'start','end'},'protected start/end required')
  start,end=span['start'],span['end'];locate(start,roots);locate(end,roots)
  require(start['part']==end['part'] and start['index']<=end['index'],'protected range invalid')
  protected.append((start['part'],start['index'],end['index']))
 ops=request['operations'];require(isinstance(ops,list) and 1<=len(ops)<=40,'1..40 operations required')
 deletions=set();inserts={};templates=set();anchors=set();replacements={};flows={}
 for op in ops:
  require(isinstance(op,dict) and op.get('op') in (['delete','insert_before','insert_after','replace_runs','paragraph_flow'] if rich else ['delete','insert_before','insert_after']),'unsupported operation')
  if op['op']=='delete':
   require(set(op)=={'op','target'},'delete target only');b=op['target'];p=locate(b,roots);key=(b['part'],b['index'])
   require(key not in deletions and eligible(p,defs),'duplicate or controlled/break/outline target')
   require(not any(name==key[0] and lo<=key[1]<=hi for name,lo,hi in protected),'protected deletion')
   deletions.add(key)
  elif op['op']=='paragraph_flow':
   require({'op','target'}<set(op) and set(op)<={'op','target','keep_with_next','page_break_before'},'bounded paragraph flow flags required')
   b=op['target'];p=locate(b,roots);key=(b['part'],b['index']);flags={k:v for k,v in op.items() if k not in ['op','target']}
   require(key not in flows and eligible(p,defs) and text(p).strip(),'duplicate or unsupported flow target')
   require(not any(name==key[0] and lo<=key[1]<=hi for name,lo,hi in protected),'protected flow target')
   require(all(type(v) is bool for v in flags.values()),'flow flags must be boolean')
   br=defs[p.get('paraPrIDRef')].find(H+'breakSetting');require(br is not None,'flow base definition missing')
   names={'keep_with_next':'keepWithNext','page_break_before':'pageBreakBefore'}
   require(any(br.get(names[k])!=str(int(v)) for k,v in flags.items()),'flow must change a setting')
   flows[key]=flags
  elif op['op']=='replace_runs':
   require(set(op)=={'op','target','runs'},'replace target/runs only')
   b=op['target'];p=locate(b,roots);key=(b['part'],b['index'])
   require(key not in replacements and eligible(p,defs,True,True),'duplicate or unsupported run target')
   require(not any(name==key[0] and lo<=key[1]<=hi for name,lo,hi in protected),'protected run replacement')
   values=checked_runs(p,op['runs'])
   require(values!=[(r.find(P+'t').text or '') for r in p.findall(P+'run')],'replacement must change text')
   replacements[key]=values
  else:
   segmented='paragraphs' in op
   require(set(op)=={'op','anchor','template','paragraphs' if segmented else 'texts'} and (not segmented or rich),'insert anchor/template/texts or v2 paragraphs required')
   b,t=op['anchor'],op['template'];p=locate(b,roots);template=locate(t,roots)
   require(b['part']==t['part'] and eligible(p,defs) and eligible(template,defs,True,segmented),'plain root anchor and supported template in same section required')
   point=b['index']+(op['op']=='insert_after');key=(b['part'],point)
   require(key not in inserts,'ambiguous shared insertion boundary')
   require(not any(name==key[0] and lo<point<=hi for name,lo,hi in protected),'insertion inside protected range')
   values=op['paragraphs' if segmented else 'texts'];require(isinstance(values,list) and 1<=len(values)<=20,'1..20 new paragraphs')
   if segmented:
    require(all(isinstance(v,dict) and set(v)=={'runs'} for v in values),'explicit runs object required')
    values=[checked_runs(template,v['runs']) for v in values]
   else:
    for value in values:
     single_line(value,search=True);require(value.strip() and len(value)<=3000,'nonempty bounded new text')
   inserts[key]=[(t['index'],value) for value in values];templates.add((t['part'],t['index']));anchors.add((b['part'],b['index']))
 require(len(deletions)+len(set(replacements)|set(flows))+sum(len(v) for v in inserts.values())<=100,'too many changed paragraphs')
 require(not deletions.intersection(replacements),'deleted run replacement target')
 require(not deletions.intersection(flows),'deleted flow target')
 require(not(deletions&anchors) and not(deletions&templates),'deleted insertion anchor/template')
 # Deleting a numbered parent while preserving its deeper same-group items
 # would silently change their ownership. They must be explicitly selected.
 for name,index in deletions:
  h=heading(roots[name][index],defs)
  if h['type']=='NUMBER':
   for later in range(index+1,len(roots[name])):
    other=heading(roots[name][later],defs)
    if other['type']=='NUMBER' and other['idRef']==h['idRef']:
     if other['level']<=h['level']:break
     require((name,later) in deletions,'numbered parent has preserved descendants')
 model={}
 for name,root in roots.items():
  seq=[]
  for idx,p in enumerate(root):
   seq.extend(dict(template=t,text=v) for t,v in inserts.get((name,idx),[]))
   if (name,idx) not in deletions:
    item=dict(original=idx)
    if (name,idx) in replacements:item['runs']=replacements[name,idx]
    if (name,idx) in flows:item['flow']=flows[name,idx]
    seq.append(item)
  seq.extend(dict(template=t,text=v) for t,v in inserts.get((name,len(root)),[]))
  require(seq,'cannot empty section')
  baseline={}
  for p in root:
   h=heading(p,defs)
   if h['type']=='NUMBER':baseline[h['idRef']]=min(baseline.get(h['idRef'],h['level']),h['level'])
  original_owners={};original_stack={}
  for idx,p in enumerate(root):
   h=heading(p,defs)
   if h['type']=='NUMBER':
    stack=original_stack.setdefault(h['idRef'],{})
    if h['level']>baseline[h['idRef']]:
     require(h['level']-1 in stack,'source numbering parent missing')
     original_owners[idx]=stack[h['level']-1]
    original_stack[h['idRef']]={k:v for k,v in stack.items() if k<h['level']}|{h['level']:('original',idx)}
  parents={}
  for serial,item in enumerate(seq):
   h=heading(root[item.get('original',item.get('template'))],defs)
   if h['type']=='NUMBER':
    prior=parents.get(h['idRef'],{});level=h['level'];base=baseline[h['idRef']]
    require(level==base or level-1 in prior,'numbered item has no remaining parent')
    if 'original' in item and item['original'] in original_owners:
     require(prior[level-1]==original_owners[item['original']],'insertion reassigns existing numbered descendants')
    identity=('original',item['original']) if 'original' in item else ('new',serial)
    parents[h['idRef']]={n:identity_old for n,identity_old in prior.items() if n<level}|{level:identity}
  model[name]=seq
 return parts,roots,defs,deletions,inserts,model
def verify(before,after,request):
 bm,roots,defs,deletions,inserts,model=checked(before,request)
 am,ar,ad=package(after);changed={name for name,index in deletions}|{name for name,index in inserts}|{name for name,seq in model.items() if any('runs' in item or 'flow' in item for item in seq)}
 flow_items=[(name,item) for name,seq in model.items() for item in seq if 'flow' in item]
 require(set(bm)==set(am) and list(roots)==list(ar),'package inventory/order changed')
 for name in bm:
  if name not in changed and not(name=='Contents/header.xml' and flow_items):require(bm[name]==am[name],'non-target member changed '+name)
 existing_ids={p.get('id') for r in roots.values() for p in r.iter(P+'p')};new_ids=[];flow_refs=set()
 for name in changed:
  require(dict(roots[name].attrib)==dict(ar[name].attrib) and len(ar[name])==len(model[name]),'root shape/count changed')
  for actual,item in zip(ar[name],model[name]):
   if 'original' in item:
    original=roots[name][item['original']]
    expected=run_tree(original,item['runs']) if 'runs' in item else tree(original)
    if 'flow' in item:
     ref=actual.get('paraPrIDRef');require(ref in ad,'unresolved flow paragraph definition');flow_refs.add(ref)
     want=copy.deepcopy(defs[original.get('paraPrIDRef')]);want.set('id',ref)
     names={'keep_with_next':'keepWithNext','page_break_before':'pageBreakBefore'}
     for k,v in item['flow'].items():want.find(H+'breakSetting').set(names[k],str(int(v)))
     require(tree(want)==tree(ad[ref]),'paragraph style changed beyond exact flow flags')
     expected[1]=sorted((k,ref if k=='paraPrIDRef' else v) for k,v in expected[1])
    require(tree(actual)==expected,'selected run/flow or non-target paragraph changed')
   else:
    template=roots[name][item['template']]
    expected=run_tree(template,item['text'],new_id=True) if isinstance(item['text'],list) else tree(template,new_id=True,new_text=item['text'],no_cache=True)
    require(tree(actual,new_id=True,no_cache=True)==expected,'new text/template formatting mismatch')
    require(actual.find(P+'linesegarray') is None and actual.get('id') not in existing_ids,'new paragraph cache/id reused')
    new_ids.append(actual.get('id'))
 require(None not in new_ids and len(set(new_ids))==len(new_ids),'new paragraph ID collision')
 if flow_items:
  hb=parse(bm['Contents/header.xml']);ha=parse(am['Contents/header.xml'])
  require(all(k in ad and tree(n)==tree(ad[k]) for k,n in defs.items()),'old shared paragraph definition changed')
  added=set(ad)-set(defs);require(added<=flow_refs,'unrelated paragraph definition added')
  ba=hb.find('.//'+H+'paraProperties');aa=ha.find('.//'+H+'paraProperties')
  require(aa is not None and ba is not None and int(aa.get('itemCnt'))==len(ad),'paragraph definition count mismatch')
  for n in list(aa):
   if n.get('id') in added:aa.remove(n)
  aa.set('itemCnt',ba.get('itemCnt'));require(tree(hb)==tree(ha),'non-target header changed')
 checks=dict(nonTargetPackageMembersByteExact=True,allUneditedParagraphSubtreesEqual=True,allSelectedRunTextAndStylesExactlyVerified=True,requestedOrderTextAndDeletionExact=True,existingNativeNumberingAndStylesByteExact=True,newIdsUnique=True,noGlobalBlankCleanup=True,changedSections=sorted(changed),deletedParagraphs=len(deletions),insertedParagraphs=len(new_ids),runEditedParagraphs=sum('runs' in i for seq in model.values() for i in seq))
 checks['flowEditedParagraphs']=len(flow_items)
 if flow_items:
  checks.pop('existingNativeNumberingAndStylesByteExact');checks['oldSharedStylesAndNumberingStructurallyEqual']=True;checks['exactFlowStylesAndAllOtherHeaderContentVerified']=True
 if not checks['runEditedParagraphs'] and not flow_items:checks['allRetainedParagraphSubtreesEqual']=True
 return checks
@preserve_namespace_literals
def apply(source,output,request,dry_run=False):
 source=Path(source).resolve(strict=True);output=Path(output).absolute();receipt=output.with_suffix('.body-receipt.json')
 require(source.suffix.lower()==output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and not output.is_symlink() and not receipt.exists() and output.resolve()!=source,'new HWPX/receipt paths required')
 require(validate_editor_open_safety(source).ok,'source editor safety')
 before=source.read_bytes();bm,roots,defs,deletions,inserts,model=checked(before,request)
 with HwpxDocument.open(source) as doc:
  sections={s.part_name:s for s in doc.sections}
  originals={name:list(sections[name].paragraphs) for name in roots}
  for name,index in sorted(deletions,reverse=True):originals[name][index].remove()
  for name,point in sorted(inserts,reverse=True):
   section=sections[name]
   # Original anchor is retained; find its current wrapper identity.
   if point==len(originals[name]):index=len(section.paragraphs)
   else:
    anchor=originals[name][point]
    if (name,point) in deletions:
     anchor=next((originals[name][j] for j in range(point,len(originals[name])) if (name,j) not in deletions),None)
     index=len(section.paragraphs) if anchor is None else next(i for i,p in enumerate(section.paragraphs) if p.element is anchor.element)
    else:index=next(i for i,p in enumerate(section.paragraphs) if p.element is anchor.element)
   for offset,(template,value) in enumerate(inserts[name,point]):
    new=section.insert_paragraphs(index+offset,[originals[name][template]])[0]
    values=value if isinstance(value,list) else [value]
    require(len(new.runs)==len(values),'unexpected cloned template')
    for run,content in zip(new.runs,values):run.text=content
  for name,seq in model.items():
   for item in seq:
    if 'runs' in item:
     paragraph=originals[name][item['original']]
     require(len(paragraph.runs)==len(item['runs']),'unexpected selected runs')
     for run,content in zip(paragraph.runs,item['runs']):run.text=content
    if 'flow' in item:
     paragraph=originals[name][item['original']]
     paragraph.para_pr_id_ref=doc.parts.headers[0].ensure_paragraph_format(base_para_pr_id=paragraph.para_pr_id_ref,break_setting=item['flow'])
  after=doc.to_bytes()
 checks=verify(before,after,request)
 with workspace_candidate(output.parent) as candidate:
  candidate.write_bytes(after)
  require(validate_editor_open_safety(candidate).ok,'candidate editor safety');require(sha(source)==request['sourceSha256'],'source changed during edit')
  if not dry_run:os.link(candidate,output)
 result=dict(schema=request['schema'],status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',native='PENDING',sourceSha256=request['sourceSha256'],candidateSha256=digest(after),request=request,checks=checks)
 if not dry_run:
  with receipt.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
 return result
def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
 i=sub.add_parser('inspect');i.add_argument('source');i.add_argument('--output',required=True)
 a=sub.add_parser('apply');a.add_argument('source');a.add_argument('output');a.add_argument('--request',required=True);a.add_argument('--dry-run',action='store_true')
 args=p.parse_args()
 if args.command=='inspect':
  value=inspect(args.source)
  with Path(args.output).open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
 else:value=apply(args.source,args.output,json.loads(Path(args.request).read_text(encoding='utf-8-sig')),args.dry_run)
 print(json.dumps(value,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
