"""Source-bound existing bookmark rename through public InlineObject adapter.

No raw XML serialization or fallback authoring. Referenced targets are refused;
changing internal cross-references is a separate, unverified operation.
"""
from pathlib import Path
from hashlib import sha256
from importlib.metadata import version
import json,os
from hwpx import HwpxDocument
from hwpx.model import InlineObject
from hwpx.tools.package_validator import validate_editor_open_safety
import safe_edit as oracle
from workspace_candidate_directory import workspace_candidate_directory
P='{http://www.hancom.co.kr/hwpml/2011/paragraph}'
SCHEMA='hwpx.bookmark-rename.v1'

def require(v,m):
    if not v:raise ValueError(m)

def sha(path):return sha256(Path(path).read_bytes()).hexdigest()
def shape(n):return (n.tag,tuple(sorted(n.attrib.items())),n.text or '',n.tail or '',tuple(shape(c) for c in n))
def fingerprint(n):return sha256(json.dumps(shape(n),ensure_ascii=False).encode()).hexdigest()
def location(n):
    path=[]
    while n.getparent() is not None:p=n.getparent();path.append(list(p).index(n));n=p
    return tuple(reversed(path))
def at(node,path):
    for i in path:node=node[i]
    return node

def name(value):
    oracle.single_line(value,search=True)
    require(len(value)<=64 and value==value.strip() and not any(c in value for c in ';#\\/<>'), 'bounded plain bookmark name required')
    return value

def inspect(source,old):
    name(old);sections=oracle.sections(source);bookmarks=[(part,n) for part,root in sections for n in root.iter(P+'bookmark')];matches=[(part,n) for part,n in bookmarks if n.get('name')==old]
    require(len(matches)==1,'unique existing bookmark name required');part,node=matches[0]
    require(set(node.attrib)=={'name'} and not len(node) and not (node.text or '').strip(),'simple standalone bookmark required')
    ctrl=node.getparent();run=ctrl.getparent() if ctrl is not None else None;host=run.getparent() if run is not None else None
    require(ctrl is not None and ctrl.tag==P+'ctrl' and len(ctrl)==1 and run is not None and run.tag==P+'run' and host is not None and host.tag==P+'p' and host.getparent().tag.endswith('}sec'),'root body bookmark required')
    # Fail closed if the current name is present in field metadata/commands.
    refs=[]
    for item,root in sections:
        for field in root.iter(P+'fieldBegin'):
            if any(old in str(v) for child in field.iter() for v in [*child.attrib.values(),child.text or '']):refs.append(dict(part=item,path=list(location(field))))
    require(not refs,'referenced bookmark requires a separate cross-reference update; rename refused')
    return dict(part=part,bookmarkPath=list(location(node)),bookmarkSha256=fingerprint(node),name=old,hostPath=list(location(host)),hostId=host.get('id'),hostSha256=fingerprint(host),hostText=''.join(t.text or '' for t in host.iter(P+'t')),allBookmarkNames=[n.get('name') for _,n in bookmarks])

def checked(source,req):
    require(isinstance(req,dict) and set(req)=={'schema','sourceSha256','bookmark','replacement','editableReason'} and req['schema']==SCHEMA,'exact bookmark request schema required')
    require(sha(source)==req['sourceSha256'],'stale source');oracle.single_line(req['editableReason'],search=True);require(len(req['editableReason'])>=8,'specific reason required')
    bound=inspect(source,req['bookmark']['name']);require(bound==req['bookmark'],'stale bookmark/host binding');new=name(req['replacement']);require(new!=bound['name'] and new not in bound['allBookmarkNames'],'new unused bookmark name required')
    return bound,{(bound['part'],tuple(bound['bookmarkPath'])):{'name':new}}

def verify(source,output,req):
    bound,attrs=checked(source,req)
    require(oracle.snapshot(source,attribute_overrides=attrs)==oracle.snapshot(output),'non-target structure/style/content/member changed')
    actual=inspect(output,req['replacement']);require(actual['hostPath']==bound['hostPath'] and actual['hostId']==bound['hostId'] and actual['hostText']==bound['hostText'],'bookmark moved or host changed')
    wanted=[req['replacement'] if x==bound['name'] else x for x in bound['allBookmarkNames']];require(actual['allBookmarkNames']==wanted,'other bookmark name/order changed')
    return dict(status='PASS_BOOKMARK_RENAME_PRESERVATION',onlySelectedNameChanged=True,wholeNonTargetPackageExact=True,noLayoutCacheException=True,unreferencedBookmarkOnly=True)

def apply(source,output,req,dry_run=False):
    require(version('python-hwpx')=='6.3.0','unverified public adapter version');source=Path(source).resolve(strict=True);output=Path(output).absolute();require(output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and output.resolve()!=source,'new workspace output required');bound,_=checked(source,req)
    with workspace_candidate_directory(prefix='bookmark-rename-',dir=output.parent) as directory:
        candidate=Path(directory)/'candidate.hwpx'
        with HwpxDocument.open(source) as doc:
            sections={s.part_name:s for s in doc.sections};section=sections.get(bound['part']);require(section is not None,'public section binding missing');node=at(section.element,bound['bookmarkPath']);host=at(section.element,bound['hostPath']);require(fingerprint(node)==bound['bookmarkSha256'] and fingerprint(host)==bound['hostSha256'],'public adapter subtree mismatch')
            paragraphs=[p for p in section.paragraphs if p.element is host];require(len(paragraphs)==1,'public root body paragraph missing');adapter=InlineObject(node,paragraphs[0]);require(adapter.get_attribute('name')==bound['name'],'public bookmark name mismatch');adapter.set_attribute('name',req['replacement']);require(req['replacement'] in paragraphs[0].bookmarks and bound['name'] not in paragraphs[0].bookmarks,'public bookmark readback mismatch');doc.save_to_path(candidate)
        checks=verify(source,candidate,req);require(validate_editor_open_safety(candidate).ok,'editor safety failed');require(sha(source)==req['sourceSha256'],'source changed')
        result=dict(status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',sourceSha256=sha(source),candidateSha256=sha(candidate),checks=checks,native='NOT_CHECKED')
        if not dry_run:os.link(candidate,output)
    return result
