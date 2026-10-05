"""Exact plain existing root explanation indent; no text/label rewriting."""
from pathlib import Path
import copy,os
from importlib.metadata import version
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
from namespace_literal_guard import preserve_namespace_literals
import safe_body_structure as body
from safe_native_story_text import shape,fingerprint
P=body.P;H=body.H;K='{http://www.hancom.co.kr/hwpml/2011/core}';need=body.require
SCHEMA='hwpx.hanging-explanation.v1'
def binding(source,part,index,prefix):
 m,roots,defs=body.package(Path(source).read_bytes());need(part in roots and type(index)is int and 0<=index<len(roots[part]),'exact root section/index required');p=roots[part][index]
 need(body.eligible(p,defs,rich=True) and body.heading(p,defs)['type']=='NONE' and p.get('merged')=='0','plain non-controlled root explanation required');text=body.text(p)
 need(isinstance(prefix,str) and 1<=len(prefix)<=80 and prefix.endswith(' ') and text.startswith(prefix) and len(text)>len(prefix),'exact label prefix and remaining explanation required')
 pr=defs[p.get('paraPrIDRef')];sw=pr.find(P+'switch');need(sw is not None and len(sw)==2,'native modern/fallback required');values=[]
 for name in ['case','default']:
  br=sw.find(P+name);need(br is not None,'both margin branches required');margin=br.find(H+'margin');need(margin is not None,'existing margins required');i=margin.find(K+'intent');left=margin.find(K+'left');need(i is not None and left is not None and i.get('unit')==left.get('unit')=='HWPUNIT' and int(left.get('value'))==0,'zero-left HWPUNIT explanation required');values.append(int(i.get('value')))
 need(values[0]<=0 and values[1]==2*values[0],'qualified intent branch relation required')
 return dict(part=part,index=index,id=p.get('id'),sha256=fingerprint(p),text=text,prefix=prefix,paraPrIDRef=p.get('paraPrIDRef'),modernIntent=values[0],fallbackIntent=values[1])
def checked(source,q):
 need(set(q)=={'schema','sourceSha256','editableReason','targets'} and q['schema']==SCHEMA and q['sourceSha256']==body.sha(source),'invalid/stale hanging request');need(isinstance(q['editableReason'],str) and len(q['editableReason'])>=8,'explicit reason required');need(isinstance(q['targets'],list) and 1<=len(q['targets'])<=12,'1..12 explicit explanation targets required');seen=set()
 for e in q['targets']:
  need(set(e)=={'binding','hangingHwpunit'},'exact target keys');b=e['binding'];need(b==binding(source,b['part'],b['index'],b['prefix']),'stale explanation binding');key=(b['part'],b['index']);need(key not in seen,'duplicate target');seen.add(key);v=e['hangingHwpunit'];need(type(v)is int and 200<=v<=20000 and -v!=b['modernIntent'],'actual bounded hanging change required')
 return body.package(Path(source).read_bytes())
def verify(source,output,q):
 bm,roots,defs=checked(source,q);am,actual,ad=body.package(Path(output).read_bytes());need(list(bm)==list(am) and list(roots)==list(actual),'package/spine changed');want=copy.deepcopy(roots);used=set()
 for e in q['targets']:
  b=e['binding'];p=want[b['part']][b['index']];a=actual[b['part']][b['index']];identity=a.get('paraPrIDRef');need(identity in ad,'unresolved hanging style');used.add(identity);style=copy.deepcopy(defs[b['paraPrIDRef']]);style.set('id',identity)
  for name,factor in [('case',1),('default',2)]:style.find(P+'switch/'+P+name+'/'+H+'margin/'+K+'intent').set('value',str(-factor*e['hangingHwpunit']))
  need(shape(style)==shape(ad[identity]),'non-indent style change');p.set('paraPrIDRef',identity)
  for cache in p.findall(P+'linesegarray'):p.remove(cache)
 for name,root in want.items():need(shape(root)==shape(actual[name]),'non-target text/run/section/geometry changed')
 need(all(k in ad and shape(n)==shape(ad[k]) for k,n in defs.items()),'old/shared style changed');added=set(ad)-set(defs);need(added<=used,'unrelated style additions');hb=body.parse(bm['Contents/header.xml']);ha=body.parse(am['Contents/header.xml']);bp=hb.find('.//'+H+'paraProperties');ap=ha.find('.//'+H+'paraProperties');need(int(ap.get('itemCnt'))==len(ad),'style count mismatch')
 for n in list(ap):
  if n.get('id') in added:ap.remove(n)
 ap.set('itemCnt',bp.get('itemCnt'));need(shape(hb)==shape(ha),'other header changed')
 for name in bm:
  if name not in roots and name!='Contents/header.xml':need(bm[name]==am[name],'non-target package member changed:'+name)
 return dict(status='PASS_HANGING_PRESERVATION',allTextRunsObjectsAndOldSharedDefinitionsExact=True,onlyTargetIntentAndMatchingReferenceChanged=True,modernFallbackFactors=[1,2],noGlobalMarginsFontSizeSpacingChanges=True)
@preserve_namespace_literals
def apply(source,output,q,dry_run=False):
 source=Path(source).resolve(strict=True);output=Path(output).absolute();need(version('python-hwpx')=='6.3.0','qualified core6.3.0 required');need(output.parent.is_dir() and output.suffix.lower()=='.hwpx' and not output.exists() and output.resolve()!=source,'new output required');checked(source,q)
 with body.workspace_candidate(output.parent) as tmp:
  with HwpxDocument.open(source) as doc:
   need(len(doc.parts.headers)==1,'one public header required');sections={s.part_name:s for s in doc.sections}
   for e in q['targets']:
    b=e['binding'];s=sections[b['part']];p=s.paragraphs[b['index']];need(fingerprint(p.element)==b['sha256'],'public paragraph mismatch');p.para_pr_id_ref=doc.parts.headers[0].ensure_hanging_paragraph_format(base_para_pr_id=b['paraPrIDRef'],hanging_hwpunit=e['hangingHwpunit'])
    for cache in p.element.findall(P+'linesegarray'):p.element.remove(cache)
    s.mark_dirty()
   doc.save_to_path(tmp)
  result=verify(source,tmp,q);need(validate_editor_open_safety(tmp).ok and body.sha(source)==q['sourceSha256'],'safety/source preservation');result.update(dryRun=dry_run,native='NOT_CHECKED',outputSha256=body.sha(tmp))
  if not dry_run:os.link(tmp,output)
 return result
