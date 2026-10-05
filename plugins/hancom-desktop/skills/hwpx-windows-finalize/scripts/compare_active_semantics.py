"""Read-only active-content comparison, separate from the unchanged strict gate.

Resolve referenced fonts/styles/assets; coalesce only adjacent equally styled
plain text. Never joins across paragraphs or controls. Layout caches, unused
definitions, previews and format-version conversion remain explicit limitations.
"""
import argparse,hashlib,json,posixpath
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as E
from zipfile import ZipFile
import hancom_completion_gate as g
P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'
H='{http://www.hancom.co.kr/hwpml/2011/head}'
REFS={'charPrIDRef':'charPr','paraPrIDRef':'paraPr','styleIDRef':'style','borderFillIDRef':'borderFill','tabPrIDRef':'tabPr'}
def local(tag):return tag.rsplit('}',1)[-1]
def parse(data):
 if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('DTD/entity unsupported')
 return E.fromstring(data)
def hash_value(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
class Package:
 def __init__(self,path):
  self.ref=g.ref(path);self.validated=g.read_package(path)
  with ZipFile(path) as z:self.members={n:z.read(n) for n in z.namelist()}
  self.header=parse(self.members['Contents/header.xml']);self.defs={};self.fonts={};self.cache={};self.resolving=set()
  for node in self.header.iter():
   kind=local(node.tag)
   if kind in set(REFS.values())|{'numbering','bullet'}:
    key=(kind,node.get('id'));g.require(key[1] is not None and key not in self.defs,'invalid_style_identity');self.defs[key]=node
   if node.tag==H+'fontface':
    for font in node.findall(H+'font'):
     key=(node.get('lang','').lower(),font.get('id'));g.require(key not in self.fonts,'duplicate_font_identity');self.fonts[key]=font
  manifest=parse(self.members['Contents/content.hpf']);self.assets={}
  for n in manifest.findall('{*}manifest/{*}item'):
   href=n.get('href','');resolved=href if href in self.members else posixpath.normpath(posixpath.join('Contents',href))
   if resolved.startswith('BinData/'):
    g.require(resolved in self.members,'missing_asset');self.assets[n.get('id')]=hashlib.sha256(self.members[resolved]).hexdigest()
 def style(self,kind,identity):
  key=(kind,identity)
  if key in self.cache:return self.cache[key]
  g.require(key in self.defs,'unresolved_style:'+str(key));g.require(key not in self.resolving,'unsupported_style_cycle:'+str(key))
  self.resolving.add(key)
  result=self.node(self.defs[key],definition=True)
  self.resolving.remove(key);self.cache[key]=hash_value(result);return self.cache[key]
 def attrs(self,n,definition=False):
  values={}
  for key,value in n.attrib.items():
   k=local(key)
   if definition and k=='id':continue
   if k in REFS:
    # Preserve the exact known unsigned-unset token at the observed numbering
    # paraHead location. It is not mapped to style 0, omitted, or treated as an
    # arbitrary dangling reference. A change to/from a real style still differs.
    if k=='charPrIDRef' and value=='4294967295' and n.tag==H+'paraHead':
     value=['numbering-charPr-unset-literal',value]
    else:value=self.style(REFS[k],value)
   elif k=='binaryItemIDRef':
    if value:g.require(value in self.assets,'unresolved_asset');value=self.assets[value]
    else:value=None
   elif k=='nextStyleIDRef':
    # Bound one-hop successor content; avoid the normal self-referencing style cycle.
    g.require(('style',value) in self.defs,'unresolved_next_style')
    successor=self.defs['style',value]
    value=hash_value({a:(self.style(REFS[a],v) if a in REFS else v) for a,v in successor.attrib.items() if a not in ['id','nextStyleIDRef']})
   elif n.tag==H+'fontRef':
    font=self.fonts.get((k.lower(),value));g.require(font is not None,'unresolved_font:'+k+':'+value);value=hash_value(self.node(font,definition=True))
   elif n.tag==H+'heading' and k=='idRef' and n.get('type') in ['NUMBER','BULLET']:
    value=self.style('numbering' if n.get('type')=='NUMBER' else 'bullet',value)
   values[key]=value
  return values
 def node(self,n,definition=False):
  if n.tag==P+'linesegarray':return None
  attrs=self.attrs(n,definition);children=[]
  if n.tag==P+'t':
   # Text after an inline control is XML tail text, and is visible content.
   if n.text:children.append(['TEXT',n.text])
   for c in n:
    value=self.node(c)
    if value is not None:children.append(value)
    if c.tail:children.append(['TEXT',c.tail])
   return [n.tag,attrs,None,children]
  if n.tag==P+'run':
   # Empty t vs childless run preserves the run's own formatting and controls.
   for c in n:
    if c.tag==P+'t' and not len(c):
     value=c.text or ''
     if value:
      if children and children[-1][0]=='TEXT':children[-1][1]+=value
      else:children.append(['TEXT',value])
    else:
     value=self.node(c)
     if value is not None:children.append(value)
   return [n.tag,attrs,None,children]
  for c in n:
   value=self.node(c)
   if value is None:continue
   # Only pure adjacent runs with identical resolved formatting may coalesce.
   if n.tag==P+'p' and c.tag==P+'run' and children and children[-1][0]==P+'run':
    prev=children[-1]
    plain=lambda x:len(x[3])<=1 and (not x[3] or x[3][0][0]=='TEXT')
    if prev[1]==value[1] and plain(prev) and plain(value):
     merged=(prev[3][0][1] if prev[3] else '')+(value[3][0][1] if value[3] else '')
     prev[3]=[['TEXT',merged]] if merged else [];continue
   children.append(value)
  text=n.text if n.text and n.text.strip() else None
  return [n.tag,attrs,text,children]
 def active(self):
  sections=[self.node(parse(self.members[n])) for n in self.validated['sections']]
  # Other header properties are preserved; definition inventories are diagnosed separately.
  aux=[self.node(n) for n in self.header if n.tag!=H+'refList']
  auxattrs=dict(self.header.attrib)
  return dict(sections=sections,headerProperties=[auxattrs,aux])
 def paragraph_texts(self):
  result=[]
  for name in self.validated['sections']:
   for p in parse(self.members[name]).iter(P+'p'):
    # Exclude nested paragraph text belonging to another paragraph owner.
    def visit(n):
     if n is not p and n.tag==P+'p':return ''
     if n.tag==P+'t':return (n.text or '')+''.join(visit(c)+(c.tail or '') for c in n)
     return ''.join(visit(c) for c in n)
    result.append(visit(p))
  return result
def first_differences(a,b,path='root',limit=30):
 result=[]
 def walk(x,y,p):
  if len(result)>=limit or x==y:return
  if isinstance(x,dict) and isinstance(y,dict):
   for k in sorted(x.keys()|y.keys()):walk(x.get(k),y.get(k),p+'/'+str(k))
  elif isinstance(x,list) and isinstance(y,list) and len(x)==len(y):
   for i,(l,r) in enumerate(zip(x,y)):walk(l,r,p+'/'+str(i))
  else:result.append(dict(path=p,before=str(x)[:500],after=str(y)[:500]))
 walk(a,b,path);return result
def compare(source,final):
 a,b=Package(source),Package(final);av,bv=a.active(),b.active()
 checks=dict(paragraphTextExact=a.paragraph_texts()==b.paragraph_texts(),countsExact=a.validated['counts']==b.validated['counts'],sectionSpineExact=a.validated['sections']==b.validated['sections'],binaryPayloadsExact=a.validated['binaryPayloads']==b.validated['binaryPayloads'],activeContentStylesAndObjectBindingsExact=av==bv)
 g.verify_ref(a.ref);g.verify_ref(b.ref)
 unknown=[]
 permitted=set(a.validated['sections'])|{'Contents/header.xml','Contents/content.hpf','version.xml'}
 for name in sorted(a.members.keys()|b.members.keys()):
  if name in permitted or name.startswith(('BinData/','Preview/')):continue
  if a.members.get(name)!=b.members.get(name):unknown.append(name)
 active_pass=all(checks.values()) and not unknown
 def fonts(p):return [dict(language=lang,id=identity,face=n.get('face'),type=n.get('type'),substitutes=[dict(x.attrib) for x in n.findall(H+'substFont')]) for (lang,identity),n in sorted(p.fonts.items())]
 inventories=dict(before=fonts(a),after=fonts(b));versions=dict(before=a.header.get('version'),after=b.header.get('version'))
 loss=not all(checks[k] for k in ['paragraphTextExact','countsExact','sectionSpineExact','binaryPayloadsExact'])
 same_format=versions['before']==versions['after'] and inventories['before']==inventories['after']
 state='PASS_ACTIVE_SEMANTICS' if active_pass else 'FAIL_PRESERVATION' if loss or (same_format and not checks['activeContentStylesAndObjectBindingsExact']) else 'UNVERIFIED_NORMALIZATION'
 return dict(schema='hwpx.active-semantics.v1',status=state,source=a.ref,final=b.ref,checks=checks,unknownChangedMembers=unknown,activeDifferences=first_differences(av,bv),fontInventories=inventories,headerVersions=versions,strictGateUnchanged=True,fullPackagePreservation='UNVERIFIED',nativeAndVisual='NOT_CHECKED',limitations=['Line-segment caches require native output validation','Unused style definitions, preview and metadata/version conversion are not certified','Does not grant strict completion, native readiness or future-edit/old-version compatibility'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('final');p.add_argument('--output',required=True);v=p.parse_args()
 try:r=compare(v.source,v.final)
 except (ValueError,KeyError,g.GateError) as e:r=dict(status='UNVERIFIED_INVALID_INPUT',error=str(e))
 g.write_new(v.output,r);print(json.dumps({k:r[k] for k in ['status','checks','activeDifferences'] if k in r},ensure_ascii=False));raise SystemExit(0 if r['status']=='PASS_ACTIVE_SEMANTICS' else 3 if r['status']=='FAIL_PRESERVATION' else 2)
