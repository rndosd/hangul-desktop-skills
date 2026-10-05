"""Bounded existing single-paragraph foot/endnote text edits via public run API.

Only exact declared run text changes. Note anchors, numbering, styles and the
entire non-target package are independently checked before publication.
"""
from pathlib import Path
from hashlib import sha256
import json,io,os
from importlib.metadata import version
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
import safe_edit as oracle
from workspace_candidate_directory import workspace_candidate_directory
P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'
SCHEMA='hwpx.note-run-text.v1'

def require(v,m):
 if not v:raise ValueError(m)
def sha(path):return sha256(Path(path).read_bytes()).hexdigest()
def shape(node):return (node.tag,tuple(sorted(node.attrib.items())),node.text or '',node.tail or '',tuple(shape(c) for c in node))
def fingerprint(n):return sha256(json.dumps(shape(n),ensure_ascii=False).encode()).hexdigest()
def node_at(root,path):
 for i in path:root=root[i]
 return root
def location(n):
 result=[]
 while n.getparent() is not None:parent=n.getparent();result.append(list(parent).index(n));n=parent
 return tuple(reversed(result))

def inspect(source,kind,ordinal):
 require(kind in ['footNote','endNote'] and type(ordinal) is int and 1<=ordinal<=20,'bounded note kind and ordinal required')
 notes=[(part,node) for part,root in oracle.sections(source) for node in root.iter(P+kind)];require(ordinal<=len(notes),'note outside inventory');part,note=notes[ordinal-1]
 paras=note.findall('./'+P+'subList/'+P+'p');require(len(paras)==1,'one existing note-body paragraph required');body=paras[0]
 require(all(c.tag in [P+'run',P+'linesegarray'] for c in body),'unsupported note-body child')
 runs=body.findall(P+'run');require(1<=len(runs)<=8,'1..8 note runs required');numbers=[];values=[]
 for run in runs:
  ts=run.findall(P+'t');require(len(ts)==1 and not len(ts[0]),'one plain t per run required')
  require(all(c.tag in [P+'ctrl',P+'t'] for c in run),'unsupported note run element')
  for ctrl in run.findall(P+'ctrl'):
   require(len(ctrl)==1 and ctrl[0].tag==P+'autoNum' and ctrl[0].get('numType')==('FOOTNOTE' if kind=='footNote' else 'ENDNOTE'),'only note auto-number control allowed');numbers.append(ctrl[0])
  values.append(dict(text=ts[0].text or '',charPrIDRef=run.get('charPrIDRef'),textPath=list(location(ts[0]))))
 require(len(numbers)==1,'one immutable auto-number control required')
 identity=note.get('instId') or note.get('instid');require(identity and sum((n.get('instId') or n.get('instid'))==identity for _,n in notes)==1,'unique explicit note identity required')
 return dict(kind=kind,ordinal=ordinal,part=part,notePath=list(location(note)),instId=identity,noteSha256=fingerprint(note),bodyPath=list(location(body)),bodyId=body.get('id'),number=note.get('number'),runs=values)

def checked(source,req):
 require(isinstance(req,dict) and set(req)=={'schema','sourceSha256','note','edits','editableReason'} and req['schema']==SCHEMA,'exact request schema required')
 require(sha(source)==req['sourceSha256'],'stale source');oracle.single_line(req['editableReason'],search=True);require(len(req['editableReason'])>=8,'specific reason required')
 selected=inspect(source,req['note']['kind'],req['note']['ordinal']);require(selected==req['note'],'stale/mismatched full note binding')
 require(isinstance(req['edits'],list) and 1<=len(req['edits'])<=8,'bounded run edits required');used=set();overrides={}
 for e in req['edits']:
  require(isinstance(e,dict) and set(e)=={'run','expected','replacement'},'exact run edit required');i=e['run'];require(type(i) is int and 1<=i<=len(selected['runs']) and i not in used,'unique existing run required');used.add(i)
  old=selected['runs'][i-1];require(e['expected']==old['text'],'stale run text');oracle.single_line(e['replacement']);require(e['replacement']!=old['text'],'actual text change required')
  overrides[selected['part'],tuple(old['textPath'])]=e['replacement']
 return selected,overrides

def verify(source,output,req):
 selected,overrides=checked(source,req);changed={(selected['part'],tuple(selected['bodyPath']))}
 require(oracle.snapshot(source,overrides,changed)==oracle.snapshot(output,changed_paragraphs=changed),'non-target structure/style/numbering/member changed')
 actual=inspect(output,selected['kind'],selected['ordinal']);wanted=[r['text'] for r in selected['runs']]
 for e in req['edits']:wanted[e['run']-1]=e['replacement']
 require([r['text'] for r in actual['runs']]==wanted and actual['instId']==selected['instId'] and actual['bodyId']==selected['bodyId'] and actual['number']==selected['number'],'requested note text/identity mismatch')
 return dict(status='PASS_NOTE_TEXT_PRESERVATION',wholeNonTargetPackageExact=True,allNoteAnchorsNumbersStylesExact=True,onlySelectedBodyLayoutCacheMayChange=True)

def apply(source,output,req,dry_run=False):
 require(version('python-hwpx')=='6.3.0','unverified public API version');source=Path(source).resolve(strict=True);output=Path(output).absolute();require(output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and output.resolve()!=source,'new workspace output required')
 selected,_=checked(source,req)
 with workspace_candidate_directory(prefix='note-text-',dir=output.parent) as folder:
  candidate=Path(folder)/'candidate.hwpx'
  with HwpxDocument.open(source) as doc:
   matches=[n for host in doc.paragraphs for n in [*host.footnotes,*host.endnotes] if n.kind==selected['kind'] and n.inst_id==selected['instId']]
   require(len(matches)==1 and fingerprint(matches[0].element)==selected['noteSha256'],'exact public note identity/structure required')
   runs=matches[0].body_paragraph.runs
   for e in req['edits']:require(runs[e['run']-1].text==e['expected'],'API run text mismatch');runs[e['run']-1].text=e['replacement']
   doc.save_to_path(candidate)
  checks=verify(source,candidate,req);require(validate_editor_open_safety(candidate).ok,'editor safety failed');require(sha(source)==req['sourceSha256'],'source changed')
  result=dict(status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',sourceSha256=sha(source),candidateSha256=sha(candidate),checks=checks,native='NOT_CHECKED')
  if not dry_run:os.link(candidate,output)
 return result
