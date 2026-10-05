"""Existing native page counter, position and first-page visibility adapter."""
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
SCHEMA='hwpx.native-page-number.v1'
FLAGS={'hideFirstHeader':'hide_first_header','hideFirstFooter':'hide_first_footer','hideFirstPageNum':'hide_first_page_num'}

def require(v,m):
    if not v:raise ValueError(m)
def sha(path):return sha256(Path(path).read_bytes()).hexdigest()
def shape(n):return (n.tag,tuple(sorted(n.attrib.items())),n.text or '',n.tail or '',tuple(shape(c) for c in n))
def fingerprint(n):return sha256(json.dumps(shape(n),ensure_ascii=False).encode()).hexdigest()
def location(n):
    path=[]
    while n.getparent() is not None:p=n.getparent();path.append(list(p).index(n));n=p
    return tuple(reversed(path))
def at(n,path):
    for i in path:n=n[i]
    return n
def controlled(n,root):
    ctrl=n.getparent();run=ctrl.getparent() if ctrl is not None else None;host=run.getparent() if run is not None else None
    require(ctrl is not None and ctrl.tag==P+'ctrl' and len(ctrl)==1 and run is not None and run.tag==P+'run' and host is not None and host.tag==P+'p' and host.getparent() is root,'simple root body control required')
    return dict(path=list(location(n)),sha256=fingerprint(n),attrs=dict(n.attrib),hostPath=list(location(host)),hostId=host.get('id'))

def inspect(source):
    sections=oracle.sections(source);require(len(sections)==1,'one existing section required');part,root=sections[0];secs=list(root.iter(P+'secPr'));require(len(secs)==1,'one section properties node required');sec=secs[0];start=sec.findall(P+'startNum');visibility=sec.findall(P+'visibility');require(len(start)==len(visibility)==1,'existing startNum and visibility required');displays=list(root.iter(P+'pageNum'));require(len(displays)==1,'one native pageNum display required');display=displays[0];require(display.get('formatType')=='DIGIT' and display.get('sideChar')=='-' and display.get('pos') in ['BOTTOM_LEFT','BOTTOM_CENTER','BOTTOM_RIGHT'],'ordinary hyphenated numeric bottom display required');restarts=list(root.iter(P+'newNum'));require(len(restarts)<=1 and all(n.get('numType')=='PAGE' for n in restarts),'zero or one existing PAGE restart only')
    require(all(visibility[0].get(k) in ['0','1'] for k in FLAGS),'known native visibility encoding required')
    return dict(part=part,sectionSha256=fingerprint(root),secPrPath=list(location(sec)),startPath=list(location(start[0])),startAttrs=dict(start[0].attrib),visibilityPath=list(location(visibility[0])),visibilityAttrs=dict(visibility[0].attrib),display=controlled(display,root),restart=controlled(restarts[0],root) if restarts else None)

def checked(source,req):
    require(isinstance(req,dict) and set(req)=={'schema','sourceSha256','binding','changes','editableReason'} and req['schema']==SCHEMA,'exact page request schema required');require(sha(source)==req['sourceSha256'],'stale source');oracle.single_line(req['editableReason'],search=True);require(len(req['editableReason'])>=8,'specific reason required');b=inspect(source);require(b==req['binding'],'stale/mismatched page control binding');c=req['changes'];require(isinstance(c,dict) and c and set(c)<={'sectionStartNumber','restartNumber','position','visibility'},'explicit bounded page changes required');attrs={}
    if 'sectionStartNumber' in c:
        n=c['sectionStartNumber'];require(type(n) is int and 1<=n<=9999,'positive bounded section start required');attrs[b['part'],tuple(b['startPath'])]={'page':str(n)}
    if 'restartNumber' in c:
        n=c['restartNumber'];require(b['restart'] is not None and type(n) is int and 1<=n<=9999,'existing restart and positive bounded number required');attrs[b['part'],tuple(b['restart']['path'])]={'num':str(n)}
    if 'position' in c:
        require(c['position'] in ['BOTTOM_LEFT','BOTTOM_CENTER','BOTTOM_RIGHT'],'bounded bottom position required');attrs[b['part'],tuple(b['display']['path'])]={'pos':c['position']}
    if 'visibility' in c:
        v=c['visibility'];require(isinstance(v,dict) and v and set(v)<=set(FLAGS) and all(type(x) is bool for x in v.values()),'explicit first-page booleans required');attrs[b['part'],tuple(b['visibilityPath'])]={k:str(int(x)) for k,x in v.items()}
    require(oracle.snapshot(source,attribute_overrides=attrs)!=oracle.snapshot(source),'actual setting change required')
    return b,attrs

def verify(source,output,req):
    b,attrs=checked(source,req);require(oracle.snapshot(source,attribute_overrides=attrs)==oracle.snapshot(output),'non-target page/story/style/body/package changed');return dict(status='PASS_NATIVE_PAGE_SETTINGS_PRESERVATION',onlyDeclaredExistingAttributesChanged=True,allPageStoryTextStylesAndOtherControlsExact=True,noLayoutCacheException=True)

def apply(source,output,req,dry_run=False):
    require(version('python-hwpx')=='6.3.0','unverified page/control adapter version');source=Path(source).resolve(strict=True);output=Path(output).absolute();require(output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and output.resolve()!=source,'new workspace output required');b,attrs=checked(source,req)
    with workspace_candidate_directory(prefix='native-page-settings-',dir=output.parent) as directory:
        candidate=Path(directory)/'candidate.hwpx'
        with HwpxDocument.open(source) as doc:
            require(len(doc.sections)==1,'public section count mismatch');section=doc.sections[0];require(section.part_name==b['part'] and fingerprint(section.element)==b['sectionSha256'],'public section binding mismatch');c=req['changes']
            if 'sectionStartNumber' in c:section.properties.set_start_numbering(page=c['sectionStartNumber'])
            if 'visibility' in c:
                doc.page.set_visibility(**{FLAGS[k]:v for k,v in c['visibility'].items()})
                # Native source uses 0/1. Canonicalize only declared visibility
                # attributes on the existing public properties element.
                node=at(section.element,b['visibilityPath'])
                for k,v in c['visibility'].items():node.set(k,str(int(v)))
            for key,control,attribute in [('position',b['display'],'pos'),('restartNumber',b['restart'],'num')]:
                if key not in c:continue
                node=at(section.element,control['path']);require(fingerprint(node)==control['sha256'],'public control subtree mismatch');host=at(section.element,control['hostPath']);paragraphs=[p for p in section.paragraphs if p.element is host];require(len(paragraphs)==1,'public control host missing');InlineObject(node,paragraphs[0]).set_attribute(attribute,c[key])
            doc.save_to_path(candidate)
        checks=verify(source,candidate,req);require(validate_editor_open_safety(candidate).ok,'editor safety failed');require(sha(source)==req['sourceSha256'],'source changed');result=dict(status='PASS_STRUCTURE_DRY_RUN' if dry_run else 'PASS_STRUCTURE',sourceSha256=sha(source),candidateSha256=sha(candidate),checks=checks,native='NOT_CHECKED')
        if not dry_run:os.link(candidate,output)
    return result
