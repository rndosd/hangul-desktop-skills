"""Explicit existing root breaks and fixed tabbed TOC digit tails only.
Public wrappers write documents; independent full-package trees verify them.
Not an escape hatch for body/cell editing, native TOC, or general controls.
"""
from pathlib import Path
import copy,json,re,os
from importlib.metadata import version
from hwpx import HwpxDocument
from hwpx.oxml.paragraph import HwpxOxmlParagraph
from hwpx.tools.package_validator import validate_editor_open_safety
from namespace_literal_guard import preserve_namespace_literals
import safe_body_structure as body
from safe_native_story_text import shape,fingerprint,location,at
P=body.P;H=body.H
SCHEMA='hwpx.report-reflow.v1'
need=body.require
def flow_binding(source,index):
 m,roots,defs=body.package(Path(source).read_bytes());need(len(roots)==1,'one section required');part,root=next(iter(roots.items()));need(type(index) is int and 0<=index<len(root),'root index required');p=root[index]
 need(p.get('columnBreak')=='0' and p.get('pageBreak') in ['0','1'] and p.get('merged')=='0','ordinary root instance flags required')
 tables=list(p.iter(P+'tbl'));forbidden={P+x for x in ['ctrl','secPr','pic','fieldBegin','fieldEnd','footNote','endNote','header','footer','bookmark']}
 need(not any(n.tag in forbidden for n in p.iter()),'controlled/field/story paragraph unsupported')
 if tables:
  need(len(tables)==1 and tables[0].get('rowCnt')==tables[0].get('colCnt')=='1' and tables[0].find(P+'pos').get('treatAsChar')=='1','one inline single-cell heading table required')
  need(len(list(tables[0].iter(P+'tc')))==1 and all(n.tag!=P+'tbl' for c in tables[0] for n in c.iter()),'nested heading table unsupported')
  need(not any(len(t) for t in p.iter(P+'t')),'mixed heading text unsupported')
 else:need(all(n.tag in [P+'p',P+'run',P+'t',P+'linesegarray',P+'lineseg'] for n in p.iter()),'plain root paragraph required')
 text=''.join(n.text or '' for n in p.iter(P+'t'));need(text.strip() and len(text)<=1500,'bounded nonempty heading/body required')
 pr=defs[p.get('paraPrIDRef')];br=pr.find(H+'breakSetting');need(br is not None and body.heading(p,defs)['type']=='NONE','ordinary resolved flow definition required')
 return dict(part=part,index=index,id=p.get('id'),sha256=fingerprint(p),text=text,attrs=dict(p.attrib),breakAttrs=dict(br.attrib))
def toc_bindings(source):
 m,roots,defs=body.package(Path(source).read_bytes());out=[]
 for part,root in roots.items():
  for p in root.iter(P+'p'):
   tabs=list(p.iter(P+'tab'))
   if not tabs:continue
   text=''.join((x.text or '')+''.join(c.tail or '' for c in x) for r in p.findall(P+'run') for x in r.findall(P+'t'))
   if not re.match(r'^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.',text):continue
   need(len(tabs)==1,'ambiguous TOC tab');tab=tabs[0];t=tab.getparent();run=t.getparent();need(t.tag==P+'t' and run.tag==P+'run' and run.getparent() is p and len(t)==1 and not (t.text or ''),'single existing tab followed by digit tail required')
   need(not any(n.tag in {P+x for x in ['tbl','pic','ctrl','fieldBegin','fieldEnd']} for n in p.iter()),'controlled/native TOC unsupported')
   match=re.fullmatch(r'( *)([0-9]{1,4})( *)',tab.tail or '');need(match is not None,'fixed numeric TOC suffix required')
   out.append(dict(part=part,path=list(location(p)),sha256=fingerprint(p),text=text,run=p.findall(P+'run').index(run),tail=tab.tail,number=int(match[2]),prefix=match[1],suffix=match[3]))
 need(1<=len(out)<=20,'bounded existing fixed TOC required');return out
def checked(source,q):
 need(set(q)=={'schema','sourceSha256','editableReason','flow','toc'} and q['schema']==SCHEMA and q['sourceSha256']==body.sha(source),'invalid/stale request');need(isinstance(q['editableReason'],str) and len(q['editableReason'])>=8,'explicit reason required')
 need(isinstance(q['flow'],list) and len(q['flow'])<=6 and isinstance(q['toc'],list) and len(q['toc'])<=20 and q['flow']+q['toc'],'bounded explicit edits required')
 used=set()
 for e in q['flow']:
  need(set(e)=={'binding','changes'} and e['binding']==flow_binding(source,e['binding']['index']),'stale flow binding');b=e['binding'];need(b['index'] not in used,'duplicate flow');used.add(b['index']);c=e['changes']
  need(c and set(c)<={'pageBreak','page_break_before','keep_with_next'} and all(type(v) is bool for v in c.values()),'exact flow flags required')
  current={'pageBreak':b['attrs']['pageBreak'],'page_break_before':b['breakAttrs']['pageBreakBefore'],'keep_with_next':b['breakAttrs']['keepWithNext']};need(any(current[k]!=str(int(v)) for k,v in c.items()),'actual flow change required')
 if q['toc']:
  available=toc_bindings(source);used=set()
  for e in q['toc']:
   need(set(e)=={'binding','number'} and e['binding'] in available,'stale TOC binding');b=e['binding'];key=(b['part'],tuple(b['path']));need(key not in used,'duplicate TOC');used.add(key);need(type(e['number']) is int and 1<=e['number']<=9999 and e['number']!=b['number'],'actual bounded positive TOC number required')
 return body.package(Path(source).read_bytes())
def verify(source,output,q):
 bm,roots,defs=checked(source,q);am,ar,ad=body.package(Path(output).read_bytes());need(bm.keys()==am.keys() and list(roots)==list(ar),'inventory/spine changed');wanted=copy.deepcopy(roots);usedrefs=set()
 for e in q['flow']:
  b=e['binding'];p=wanted[b['part']][b['index']];actual=ar[b['part']][b['index']];c=e['changes']
  if 'pageBreak' in c:p.set('pageBreak',str(int(c['pageBreak'])))
  flags={k:v for k,v in c.items() if k!='pageBreak'}
  if flags:
   ref=actual.get('paraPrIDRef');need(ref in ad,'unresolved target flow style');usedrefs.add(ref);pr=copy.deepcopy(defs[p.get('paraPrIDRef')]);pr.set('id',ref)
   for k,v in flags.items():pr.find(H+'breakSetting').set({'page_break_before':'pageBreakBefore','keep_with_next':'keepWithNext'}[k],str(int(v)))
   need(shape(pr)==shape(ad[ref]),'style changes beyond declared flags');p.set('paraPrIDRef',ref)
 for e in q['toc']:
  b=e['binding'];p=at(wanted[b['part']],b['path']);tab=list(p.iter(P+'tab'))[0];tab.tail=b['prefix']+str(e['number'])+b['suffix']
  for cache in p.findall(P+'linesegarray'):p.remove(cache)
 for part in roots:need(shape(wanted[part])==shape(ar[part]),'non-target section/tab/text/style/geometry changed')
 hb=body.parse(bm['Contents/header.xml']);ha=body.parse(am['Contents/header.xml']);need(all(k in ad and shape(n)==shape(ad[k]) for k,n in defs.items()),'old/shared style changed');added=set(ad)-set(defs);need(added<=usedrefs,'unrelated style addition')
 bp=hb.find('.//'+H+'paraProperties');ap=ha.find('.//'+H+'paraProperties');need(int(ap.get('itemCnt'))==len(ad),'style count mismatch')
 for n in list(ap):
  if n.get('id') in added:ap.remove(n)
 ap.set('itemCnt',bp.get('itemCnt'));need(shape(hb)==shape(ha),'non-target header changed')
 for name in bm:
  if name not in roots and name!='Contents/header.xml':need(bm[name]==am[name],'non-target member changed:'+name)
 return dict(status='PASS_STRUCTURE_PRESERVATION',allNonTargetPackageAndFullSectionTreesExact=True,oldSharedStylesUntouched=True,onlyExplicitFlowFlagsAndTocDigitTailsChanged=True,tocTabsLeadersRunStylesUntouched=True,noGlobalMarginsFontOrLineSpacingChanges=True)
@preserve_namespace_literals
def apply(source,output,q,dry_run=False):
 source=Path(source).resolve(strict=True);output=Path(output).absolute();need(version('python-hwpx')=='6.3.0','qualified core required');need(output.suffix.lower()=='.hwpx' and not output.exists() and output.parent.is_dir() and output.resolve()!=source,'new output required');checked(source,q)
 with body.workspace_candidate(output.parent) as temp:
  with HwpxDocument.open(source) as doc:
   sections={s.part_name:s for s in doc.sections}
   for e in q['flow']:
    b=e['binding'];s=sections[b['part']];p=s.paragraphs[b['index']];need(fingerprint(p.element)==b['sha256'],'public flow subtree mismatch');c=e['changes']
    if 'pageBreak' in c:p.page_break=c['pageBreak']
    flags={k:v for k,v in c.items() if k!='pageBreak'}
    if flags:p.para_pr_id_ref=doc.parts.headers[0].ensure_paragraph_format(base_para_pr_id=p.para_pr_id_ref,break_setting=flags)
   for e in q['toc']:
    b=e['binding'];s=sections[b['part']];n=at(s.element,b['path']);need(fingerprint(n)==b['sha256'],'public TOC subtree mismatch');p=HwpxOxmlParagraph(n,s);run=p.runs[b['run']];need(run.replace_text(b['tail'],b['prefix']+str(e['number'])+b['suffix'],count=1)==1,'TOC run tail replacement failed')
   doc.save_to_path(temp)
  result=verify(source,temp,q);need(validate_editor_open_safety(temp).ok and body.sha(source)==q['sourceSha256'],'safety/source preservation');result.update(dryRun=dry_run,sourceSha256=body.sha(source),outputSha256=body.sha(temp),native='NOT_CHECKED')
  if not dry_run:os.link(temp,output)
  return result
