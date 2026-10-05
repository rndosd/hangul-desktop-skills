"""Exact selected-paragraph Korean word/Latin word wrapping, pinned core 6.3.0."""
import argparse,copy,hashlib,json,os,tempfile
from pathlib import Path
from zipfile import ZipFile
from importlib.metadata import version
from lxml import etree as E
from hwpx import HwpxDocument
from hwpx.oxml import HwpxOxmlParagraph
from hwpx.tools.package_validator import validate_editor_open_safety
from safe_edit import candidates,digest,parse,local,snapshot,source_path
from namespace_literal_guard import preserve_namespace_literals
SCHEMA='hwpx.word-wrap.v1'
H='{http://www.hancom.co.kr/hwpml/2011/head}'
def require(ok,why):
 if not ok:raise ValueError(why)
def shape(n):return n.tag,tuple(sorted(n.attrib.items())),n.text or '',n.tail or '',tuple(shape(c) for c in n)
def selections(source,req):
 require(isinstance(req,dict) and set(req)=={'schema','source_sha256','targets'} and req['schema']==SCHEMA and req['source_sha256']==digest(source),'invalid/stale word-wrap plan')
 require(isinstance(req['targets'],list) and 1<=len(req['targets'])<=20,'1..20 explicit paragraphs required');seen=set();out=[]
 for item in req['targets']:
  require(isinstance(item,dict) and set(item)=={'part','paragraph_path','expected_text','korean','latin','reason'},'exact target keys required')
  require(item['korean']=='WORD' and item['latin']=='WORD' and isinstance(item['reason'],str) and item['reason'].strip(),'explicit WORD/WORD and reason required')
  require(isinstance(item['paragraph_path'],list) and item['paragraph_path'] and all(type(v)is int and v>=0 for v in item['paragraph_path']),'exact nonnegative integer path required')
  require(isinstance(item['expected_text'],str) and item['expected_text'].strip() and isinstance(item['part'],str),'nonempty expected paragraph required');key=item['part'],tuple(item['paragraph_path']);require(key not in seen,'duplicate paragraph');seen.add(key)
  found=[c for c in candidates(source,item['expected_text'],req['source_sha256']) if c['part']==key[0] and tuple(c['paragraph_path'])==key[1]]
  require(len(found)==1 and found[0]['supported'] and found[0]['_paragraph_text']==item['expected_text'],'plain exact paragraph missing/unsupported');out.append((key,item))
 return out
@preserve_namespace_literals
def apply(source,output,req,dry_run=False):
 source=source_path(source);output=Path(output).absolute();require(version('python-hwpx')=='6.3.0' and validate_editor_open_safety(source).ok,'invalid source/unverified runtime');require(source!=output.resolve() and not output.exists() and not output.is_symlink() and output.suffix.lower()=='.hwpx' and output.parent.is_dir(),'new hwpx output required');targets=selections(source,req)
 with ZipFile(source) as z:header=parse(z.read('Contents/header.xml'))
 expected=copy.deepcopy(header);styles=expected.find('.//'+H+'paraProperties');old={p.get('id'):p for p in styles};require(len(old)==len(styles),'duplicate paragraph style IDs');overrides={};changed=set();details=[]
 with HwpxDocument.open(source) as doc:
  sections={s.part_name:s for s in doc.sections};hh=doc.parts.headers[0];container=hh.element.find('.//'+H+'paraProperties');require(container is not None,'paragraph definitions missing')
  for key,item in targets:
   section=sections[key[0]];node=section.element
   for i in key[1]:node=node[i]
   require(all(parent.get('protect','0')=='0' for parent in node.iterancestors() if local(parent)=='tc'),'protected cell unsupported')
   for parent in node.iterancestors():
    if local(parent)=='tbl':require(parent.get('lock','0')=='0' and parent.get('noAdjust','0')=='0' and parent.find('{http://www.hancom.co.kr/hwpml/2011/paragraph}sz').get('protect','0')=='0','protected/fixed table unsupported')
   para=HwpxOxmlParagraph(node,section);base=str(para.para_pr_id_ref);require(base in old,'unbound paragraph style');clone=copy.deepcopy(old[base]);bs=clone.find(H+'breakSetting');require(bs is not None and bs.get('breakNonLatinWord') in ['KEEP_WORD','BREAK_WORD'] and bs.get('breakLatinWord') in ['KEEP_WORD','BREAK_WORD','HYPHENATION'],'unknown original wrap mode')
   # Already requested: preserve its exact ID, even if an earlier duplicate
   # definition has equal content. No style allocation or cache invalidation.
   if bs.get('breakNonLatinWord')=='BREAK_WORD' and bs.get('breakLatinWord')=='KEEP_WORD':continue
   # Dedicated version-pinned clone adapter: only two tested enum attributes.
   # There is no 6.3.0 public setter for these enums; old definitions never mutate.
   bs.set('breakNonLatinWord','BREAK_WORD');bs.set('breakLatinWord','KEEP_WORD');new=None
   for p in container:
    a=copy.deepcopy(p);b=copy.deepcopy(clone);a.attrib.pop('id');b.attrib.pop('id')
    if shape(a)==shape(b):new=p.get('id');break
   if new is None:
    new=str(max(int(p.get('id')) for p in container)+1);clone.set('id',new);container.append(copy.deepcopy(clone));container.set('itemCnt',str(len(container)));hh.mark_dirty();styles.append(copy.deepcopy(clone));styles.set('itemCnt',str(len(styles)))
   if new==base:continue
   para.para_pr_id_ref=new
   for cache in list(node):
    if local(cache).lower()=='linesegarray':node.remove(cache)
   overrides[(key[0],key[1])]={'paraPrIDRef':new};changed.add(key);details.append(dict(part=key[0],paragraph_path=list(key[1]),before=base,after=new,expected_text=item['expected_text']))
  if details:after=doc.to_bytes()
  else:
   require(not overrides and not changed and shape(expected)==shape(header),'no-op changed header or paragraph state');after=source.read_bytes()
 with tempfile.TemporaryDirectory(prefix='word-wrap-',dir=output.parent) as tmp:
  p=Path(tmp)/'candidate.hwpx';p.write_bytes(after);want=snapshot(source,changed_paragraphs=changed,attribute_overrides=overrides,xml_roots={'Contents/header.xml':expected});got=snapshot(p,changed_paragraphs=changed);require(want==got,'non-target/style/text preservation mismatch');require(validate_editor_open_safety(p).ok,'open safety failed');require(digest(source)==req['source_sha256'],'source changed during edit')
  if not dry_run:os.link(p,output)
 return dict(schema='hwpx.word-wrap-receipt.v1',status=('PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE') if details else ('PASS_STRUCTURE_NO_CHANGE_DRY_RUN' if dry_run else 'PASS_STRUCTURE_NO_CHANGE_BYTE_COPY'),published=not dry_run,source_sha256=req['source_sha256'],candidate_sha256=hashlib.sha256(after).hexdigest(),changes=details,noChange=not details,allUnrequestedTextStylesGeometryControlsPreserved=True,oldSharedStylesUnchanged=True,native='pending',enumMapping=dict(koreanWord='BREAK_WORD',latinWord='KEEP_WORD'))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output');p.add_argument('--request',required=True);p.add_argument('--dry-run',action='store_true');args=p.parse_args();print(json.dumps(apply(args.source,args.output,json.loads(Path(args.request).read_text(encoding='utf-8-sig')),args.dry_run),ensure_ascii=False,indent=2))
